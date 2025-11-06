"""
Gmail email fetcher using the Gmail API.
Authenticates with OAuth2 and retrieves unread emails from the user's inbox.
Stores credentials in `../cred/token.json` for persistent access.
"""

from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any, cast

from bs4 import BeautifulSoup  # For HTML parsing
import base64  # For decoding email body content

from agent_framework import ai_function

from google.auth.exceptions import RefreshError  # Raised when refresh fails
from google.auth.transport.requests import Request  # For refreshing tokens
from google.oauth2.credentials import Credentials as OAuthCredentials  # OAuth2 credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # For OAuth2 flow
from googleapiclient.discovery import build  # building the Gmail API service

# Read, modify, and send access to Gmail
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

# Resolve credential paths relative to the project root so execution works
# no matter which directory the process is started from.

# This translates to 'src/' cuz we're in 'src/emailing/' & parents[2] goes up
# two levels which is the same as parent.parent
BASE_DIR = Path(__file__).resolve().parents[2]

# This translates to 'src/emailing/cred' for the credentials directory
CREDENTIALS_DIR = BASE_DIR / "cred"

# This translates to 'src/emailing/cred/token.json' for the token file
TOKEN_PATH = CREDENTIALS_DIR / "token.json"

# This translates to 'src/emailing/cred/credentials.json' for client secrets file
CLIENT_SECRETS_PATH = CREDENTIALS_DIR / "credentials.json"

# Cached authenticated Gmail address
_ACCOUNT_EMAIL: str | None = None


def _authenticate_gmail() -> Any:
    """Return an authenticated Gmail API client, refreshing tokens as needed."""

    creds: OAuthCredentials | None = None

    if TOKEN_PATH.exists():
        # Reload cached credentials so we can reuse the stored refresh token.
        loaded = OAuthCredentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if isinstance(loaded, OAuthCredentials):
            creds = loaded

    if creds and creds.valid:
        return build("gmail", "v1", credentials=creds)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())  # Try to breathe new life into the token.
        except RefreshError:
            creds = None  # Revoked token: fall through to a clean login.

    if not creds or not creds.valid:
        # Clear the stale token file before we ask the user to sign in again.
        if TOKEN_PATH.exists():
            TOKEN_PATH.unlink()

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRETS_PATH),
            SCOPES,
        )
        creds = cast(OAuthCredentials, flow.run_local_server(port=0))

    assert creds is not None  # At this point we must have fresh credentials.

    # Persist the token so the next run can skip the browser hop.
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())

    # Build and return the Gmail service client instance
    return build("gmail", "v1", credentials=creds)


def _get_account_email(service: Any) -> str:
    """Return the authenticated Gmail address (cached after first lookup)."""
    global _ACCOUNT_EMAIL
    if _ACCOUNT_EMAIL:
        return _ACCOUNT_EMAIL

    profile = service.users().getProfile(userId="me").execute()
    email_address = profile.get("emailAddress")
    if not isinstance(email_address, str):
        email_address = ""
    _ACCOUNT_EMAIL = email_address.lower()
    return _ACCOUNT_EMAIL


def _load_reply_context(message_id: str) -> tuple[Any, dict[str, str], str]:
    """Fetch the Gmail message headers and thread metadata needed for replies.

    Args:
        message_id: The Gmail message ID to load context from.
    Returns:
        A tuple containing Gmail service instance, message headers & thread ID.
    Raises:
        ValueError: If message_id is not provided."""

    if not message_id:
        raise ValueError("A Gmail message_id is required to send a reply.")

    service = _authenticate_gmail()
    original = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="full",
        )
        .execute()
    )

    headers = {h["name"]: h["value"] for h in original["payload"]["headers"]}

    return service, headers, original["threadId"]


def _send_reply(
    service: Any,
    headers: dict[str, str],
    thread_id: str,
    reply_body: str,
) -> dict[str, str]:
    """Create and send the Gmail reply using shared context.

    Args:
        service: Authenticated Gmail service instance.
        headers: Original message headers for reply context.
        thread_id: Thread ID to associate the reply with.
        reply_body: The plain text body of the reply email.
    Returns:
        A dictionary with the sent message ID and status.
    """

    msg = EmailMessage()
    msg["To"] = headers.get("From", "")
    msg["Subject"] = "Re: " + headers.get("Subject", "")
    msg["In-Reply-To"] = headers.get("Message-ID", "")
    msg["References"] = headers.get("Message-ID", "")
    msg.set_content(reply_body)

    encoded_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    result = (
        service.users()
        .messages()
        .send(
            userId="me",
            body={"raw": encoded_message, "threadId": thread_id},
        )
        .execute()
    )

    return {"id": result["id"], "status": "sent"}


# NOT SURE IF WE NEED THIS FUNCTION LATER!!!!
def _extract_body(part: dict) -> str:
    """
    Recursively extract all body content from email parts.
    Args:
        part: A part of the email payload.
    Returns:
        Decoded body string.
    """

    # If this part has body data, decode and return it
    if "data" in part.get("body", {}):
        return base64.urlsafe_b64decode(part["body"]["data"]).decode(
            "utf-8",
            errors="ignore",
        )

    # If this part has nested parts, recurse through them
    if "parts" in part:
        return "\n".join(_extract_body(p) for p in part["parts"] if _extract_body(p))

    return ""


# This is the "standard" non-agent function version (not exposed to the agent framework)
def fetch_unread_emails(gmail_service: Any | None = None) -> list[dict]:
    """
    Fetch unread emails with full content from Gmail inbox
    Automatically authenticates when no Gmail service instance is supplied
    Returns list of email dictionaries with id, subject, sender, snippet & body
    """
    gmail_service = _authenticate_gmail()

    # Ensure Gmail connection is established
    if gmail_service is None:
        raise ValueError("Gmail service instance is required. Cannot authenticate.")

    # Query for unread emails
    messages = (
        gmail_service.users()
        .messages()
        .list(
            userId="me",  # 'me' refers to the authenticated user
            q="is:unread",  # Gmail search query for unread emails
            maxResults=1,  # Limit to last 1 unread email
        )
        .execute()
        .get(
            "messages",
            [],
        )
    )  # Get list of messages from the response

    account_email = _get_account_email(gmail_service)
    emails = []
    for msg in messages:
        full_message = (
            gmail_service.users().messages().get(
                userId="me", id=msg["id"], format="full"
            ).execute()
        )
        headers = {h["name"]: h["value"] for h in full_message["payload"]["headers"]}
        sender_email = parseaddr(headers.get("From", ""))[1].lower()

        if sender_email == account_email:
            # Ignore the emails we just sent (auto-confirmations, etc.).
            gmail_service.users().messages().modify(
                userId="me", id=full_message["id"], body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            continue

        body = _extract_body(full_message["payload"])
        soup = BeautifulSoup(body, "html.parser")
        body = soup.get_text(separator="\n", strip=True)

        emails.append(
            {
                "id": full_message["id"],
                "subject": headers.get("Subject", ""),
                "sender": headers.get("From", ""),
                "snippet": full_message.get("snippet", ""),
                "body": body,
            }
        )

    return emails


# This is an AI FUNCTION!
@ai_function
def get_unread_emails() -> list[dict]:
    """Fetch unread emails from Gmail inbox.

    Returns:
        A list of dictionaries representing unread emails with id, subject,
        sender, snippet, and body.
    """
    return fetch_unread_emails()


def mark_email_as_read(message_id: str) -> dict[str, str]:
    service = _authenticate_gmail()

    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()

    return {"id": message_id, "status": "marked_as_read"}


def _format_reply(customer: str, lines: list[str]) -> str:
    """Return a friendly reply body given the customer name and body lines."""
    return "\n".join(
        [
            f"Hello {customer},",
            "",
            *lines,
            "",
            "Best regards,",
            "PaperCo Operations",
        ]
    )


@ai_function()
def respond_confirmation_email(
    message_id: str,
    pdf_url: str | None = None,
    retrieved_po: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Send a confirmation email for an approved order.

    Args:
        message_id: Gmail message ID to reply to.
        pdf_url: Optional invoice link for the customer.
        retrieved_po: Included so approval prompts can show the order details.
    """
    service, headers, thread_id = _load_reply_context(message_id)

    customer = headers.get("From", "Valued Customer")
    reply_body = _format_reply(
        customer,
        [
            "Your purchase order has been confirmed.",
            "We're processing your items and will notify you once they ship.",
            (
                f"You can download the invoice here: {pdf_url}"
                if pdf_url
                else "We will email the invoice link as soon as it is ready."
            ),
            "",
            "Thank you for choosing PaperCo!",
        ],
    )

    return _send_reply(service, headers, thread_id, reply_body)


@ai_function()
def respond_unfulfillable_email(
    message_id: str,
    reason: str,
    retrieved_po: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Send a graceful rejection email when we cannot fulfill an order.

    Args:
        message_id: Gmail message ID to reply to.
        reason: Human-readable explanation for the rejection.
        retrieved_po: Included so approval prompts can show the order details.
    """
    service, headers, thread_id = _load_reply_context(message_id)

    customer = headers.get("From", "Valued Customer")
    reply_body = _format_reply(
        customer,
        [
            "Thanks for your purchase order. Unfortunately, we cannot fulfill it at this time.",
            f"Reason: {reason or '<provide rejection reason>'}",
            "",
            "If you have any questions or alternatives, reply to this email.",
        ],
    )

    return _send_reply(service, headers, thread_id, reply_body)




# ---------------------------------------#
# ------------ Main function ------------#
# ---------------------------------------#

def main() -> None:
    """
    Main function to authenticate and display unread emails.
    Prints count and details of unread messages.
    """
    gmail = _authenticate_gmail()  # Authenticate with Gmail API
    emails = fetch_unread_emails(gmail)  # Retrieve unread emails

    if not emails:
        raise ValueError("No unread emails found.")

    print(f"\n{len(emails)} unread email(s)")  # Display count
    for email in emails:
        print(
            f"""
========= EMAIL SENDER =========
{email['sender']}

========= EMAIL SUBJECT =========
{email['subject']}


========= EMAIL SNIPPET =========
{email['snippet']}

========= EMAIL BODY =========
{email['body']}

"""
        )


if __name__ == "__main__":
    main()
