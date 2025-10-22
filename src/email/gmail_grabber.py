"""
Gmail email fetcher using the Gmail API.
Authenticates with OAuth2 and retrieves unread emails from the user's inbox.
Stores credentials in `../cred/token.json` for persistent access.
"""

import os
from pathlib import Path
from bs4 import BeautifulSoup # For HTML parsing
from google.auth.transport.requests import Request # For refreshing tokens
from google.oauth2.credentials import Credentials # For handling OAuth2 credentials
from google_auth_oauthlib.flow import InstalledAppFlow # For OAuth2 flow
from googleapiclient.discovery import build # For building the Gmail API service

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]  # Read-only access to Gmail


def authenticate_gmail() -> any:
    """
    Authenticate with Gmail API using OAuth2.
    Returns authenticated Gmail service instance.
    """
    # Load saved credentials
    creds = Credentials.from_authorized_user_file(Path("./cred/token.json"), SCOPES) if Path("./cred/token.json").exists() else None

    if not creds or not creds.valid:  # Check if credentials need refresh or initial auth
        if creds and creds.expired and creds.refresh_token:  # Refresh expired token
            creds.refresh(Request())
        else:  # Perform initial OAuth2 flow
            creds = InstalledAppFlow.from_client_secrets_file(Path("./cred/credentials.json"), SCOPES).run_local_server(port=0)
        open(Path("./cred/token.json"), "w").write(creds.to_json())  # Save credentials for future use
    
    return build("gmail", "v1", credentials=creds)  # Build and return Gmail API service


def _extract_body(part: dict) -> str:
    """
    Recursively extract all body content from email parts.
    Returns decoded body string.
    """
    import base64
    
    # If this part has body data, decode and return it
    if "data" in part.get("body", {}):
        return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
    
    # If this part has nested parts, recurse through them
    if "parts" in part:
        return "\n".join(_extract_body(p) for p in part["parts"] if _extract_body(p))
    
    return ""


def fetch_unread_emails(gmail_service: any) -> list[dict]:
    """
    Fetch unread emails with full content from Gmail inbox.
    Returns list of email dictionaries with id, subject, sender, snippet, and body.
    """
    # Query for unread emails
    messages = gmail_service.users().messages().list(
        userId="me", # 'me' refers to the authenticated user
        q="is:unread", # Gmail search query for unread emails
        maxResults=100, # Limit to last 100 unread emails
    ).execute().get(
        "messages", # Get the list of messages from the response
        [],
    )
    
    emails = []
    for msg in messages:
        # Fetch full message details
        full_message = gmail_service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
        # Parse email headers
        headers = {h["name"]: h["value"] for h in full_message["payload"]["headers"]}
        
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
                "snippet": full_message.get("snippet", ""),  # Extract preview text
                "body": body  # Full email body (cleaned)
            }
        )
    
    return emails





#---------------------------------------#
#------------ Main function ------------#
#---------------------------------------#

def main() -> None:
    """
    Main function to authenticate and display unread emails.
    Prints count and details of unread messages.
    """
    gmail = authenticate_gmail()  # Authenticate with Gmail API
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
    main()  # Run the main function
