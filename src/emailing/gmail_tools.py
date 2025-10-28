"""
Gmail email fetcher using the Gmail API.
Authenticates with OAuth2 and retrieves unread emails from the user's inbox.
Stores credentials in `../cred/token.json` for persistent access.
"""

from email.message import EmailMessage
from pathlib import Path
from typing import Any
from bs4 import BeautifulSoup  # For HTML parsing
import base64  # For decoding email body content

from google.auth.transport.requests import Request  # For refreshing tokens
from google.oauth2.credentials import Credentials  # OAuth2 credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # For OAuth2 flow
from googleapiclient.discovery import build  # building the Gmail API service

# Read, modify, and send access to Gmail
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


def _authenticate_gmail() -> Any:
    """
    Authenticate with Gmail API using OAuth2.

    Returns:
        authenticated Gmail service instance.

    Raises:
        Exception: If authentication fails.
    """
    # Load saved credentials
    creds = Credentials.from_authorized_user_file(
        Path("./cred/token.json"),
        SCOPES,
    ) if Path("./cred/token.json").exists() else None

    if not creds or not creds.valid:  # Check if credentials are valid
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())  # Refresh expired credentials
        else:  # Perform initial OAuth2 flow
            creds = InstalledAppFlow.from_client_secrets_file(
                Path("./cred/credentials.json"), SCOPES).run_local_server(port=0)
        # Save credentials for future use
        open(Path("./cred/token.json"), "w").write(creds.to_json())

    # Build and return Gmail API service
    return build("gmail", "v1", credentials=creds)


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
    original = service.users().messages().get(
        userId="me",
        id=message_id,
        format="full",
    ).execute()

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

    result = service.users().messages().send(
        userId="me",
        body={"raw": encoded_message, "threadId": thread_id},
    ).execute()

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


def fetch_unread_emails(gmail_service: Any | None = None) -> list[dict]:
    """
    Fetch unread emails with full content from Gmail inbox
    Automatically authenticates when no Gmail service instance is supplied
    Returns list of email dictionaries with id, subject, sender, snippet & body
    """
    gmail_service = _authenticate_gmail()

    # Ensure Gmail connection is established
    if gmail_service is None:
        raise ValueError(
            "Gmail service instance is required. Cannot authenticate."
        )

    # Query for unread emails
    messages = gmail_service.users().messages().list(
        userId="me",  # 'me' refers to the authenticated user
        q="is:unread",  # Gmail search query for unread emails
        maxResults=1,  # Limit to last 1 unread email
    ).execute().get("messages", [],)  # Get list of messages from the response

    emails = []
    for msg in messages:
        # Fetch full message details
        full_message = gmail_service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="full"
        ).execute()
        # Parse email headers
        headers = {h["name"]: h["value"]
                   for h in full_message["payload"]["headers"]}

        # Extract all body content
        body = _extract_body(full_message["payload"])

        # Strip HTML and get clean text
        soup = BeautifulSoup(body, "html.parser")
        body = soup.get_text(separator="\n", strip=True)  # Extract clean text

        emails.append(
            {
                "id": full_message["id"],
                "subject": headers.get("Subject", ""),  # Extract subject line
                "sender": headers.get("From", ""),  # Extract sender email
                # Extract preview text
                "snippet": full_message.get("snippet", ""),
                "body": body,  # Full email body (cleaned)
            }
        )

    return emails


def mark_email_as_read(message_id: str) -> dict[str, str]:
    """Remove the UNREAD label from the given Gmail message."""
    service = _authenticate_gmail()

    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()

    return {"id": message_id, "status": "marked_as_read"}


def respond_confirmation_email(
    message_id: str,
    pdf_url: str | None = None,
) -> dict[str, str]:
    """Send the standard confirmation reply for a fulfilled order.

    Args:
        message_id: The Gmail message ID to reply to.
        pdf_url: Optional URL to the invoice PDF.
    Returns:
        A dictionary with the sent message ID and status.
    """
    service, headers, thread_id = _load_reply_context(message_id)

    customer = headers.get("From", "Valued Customer")
    invoice_line = (
        f"You can find the invoice from your order here: {pdf_url}"
        if pdf_url
        else "We will send the invoice link as soon as it is ready."
    )

    reply_body = (
        f"Hello {customer},\n\n"
        "Your purchase order has been confirmed.\n"
        "We're processing your items and will notify you once they ship.\n"
        f"{invoice_line}\n\n"
        "Thank you for choosing PaperCo!\n\n"
        "Best regards,\n"
        "PaperCo Operations"
    )

    return _send_reply(service, headers, thread_id, reply_body)


def respond_unfulfillable_email(
    message_id: str,
    reason: str | None = None,
) -> dict[str, str]:
    """Send an unfulfillable order reply that includes a rejection reason.

    Args:
        message_id: The Gmail message ID to reply to.
        reason: Optional reason for rejecting the order.
    Returns:
        A dictionary with the sent message ID and status.
    """
    service, headers, thread_id = _load_reply_context(message_id)

    customer = headers.get("From", "Valued Customer")
    reason_text = reason or "<add rejection reason here>"

    reply_body = (
        f"Hello {customer},\n\n"
        "Thanks for your purchase order. Unfortunately, we cannot fulfill it at this time.\n"
        f"Reason: {reason_text}\n\n"
        "If you have any questions or can offer alternatives, just reply to this email.\n\n"
        "Best regards,\n"
        "PaperCo Operations"
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
