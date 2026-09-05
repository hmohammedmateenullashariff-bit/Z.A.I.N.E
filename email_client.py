"""
Z.A.I.N.E Agent — Email Client (IMAP / SMTP)
Enables Zaine to check unread emails, summarize them, and send emails via his dedicated Gmail.
"""

import os
import imaplib
import smtplib
from email.message import EmailMessage
from email.header import decode_header
import email

def _get_credentials():
    email_addr = os.getenv("GMAIL_ADDRESS", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    return email_addr, app_password


def check_emails(unread_only: bool = True, limit: int = 5) -> str:
    """
    Checks Zaine's Gmail inbox for recent emails.
    If unread_only is True, fetches only unread messages.
    """
    email_addr, app_password = _get_credentials()
    if not email_addr or not app_password:
        return "Gmail is not configured yet. Please provide GMAIL_ADDRESS and GMAIL_APP_PASSWORD in the .env file."

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(email_addr, app_password)
        mail.select("INBOX")

        search_criteria = "UNSEEN" if unread_only else "ALL"
        status, response = mail.search(None, search_criteria)
        if status != "OK":
            mail.logout()
            return "Failed to search emails."

        mail_ids = response[0].split()
        if not mail_ids:
            mail.logout()
            return "You have no unread emails." if unread_only else "Inbox is empty."

        # Fetch the most recent 'limit' emails
        recent_ids = mail_ids[-limit:][::-1]
        summaries = []

        for m_id in recent_ids:
            status, data = mail.fetch(m_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Decode Subject
            subject, encoding = decode_header(msg.get("Subject", "No Subject"))[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding or "utf-8", errors="replace")

            sender = msg.get("From", "Unknown Sender")

            # Extract snippet of body
            body_snippet = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    cdispo = str(part.get("Content-Disposition"))
                    if ctype == "text/plain" and "attachment" not in cdispo:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body_snippet = payload.decode(errors="replace")[:200]
                        break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body_snippet = payload.decode(errors="replace")[:200]

            clean_snippet = " ".join(body_snippet.split())
            summaries.append(
                f"- From: {sender}\n  Subject: {subject}\n  Preview: {clean_snippet}"
            )

        mail.logout()
        prefix = f"Found {len(mail_ids)} unread email(s)" if unread_only else f"Found {len(mail_ids)} email(s)"
        return f"{prefix}. Showing latest:\n\n" + "\n\n".join(summaries)

    except Exception as e:
        return f"Error checking emails: {e}"


def send_email(to_email: str, subject: str, body: str) -> str:
    """
    Sends an email from Zaine's Gmail address to the specified recipient.
    """
    email_addr, app_password = _get_credentials()
    if not email_addr or not app_password:
        return "Gmail is not configured yet. Please provide GMAIL_ADDRESS and GMAIL_APP_PASSWORD in the .env file."

    to_email = to_email.strip()
    if not to_email:
        # Fallback to user personal email if configured
        to_email = os.getenv("USER_PERSONAL_EMAIL", "").strip()
        if not to_email:
            return "Error: recipient email address is required."

    try:
        msg = EmailMessage()
        msg["From"] = f"Z.A.I.N.E <{email_addr}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(email_addr, app_password)
            smtp.send_message(msg)

        return f"Email successfully sent to {to_email} with subject: '{subject}'."
    except Exception as e:
        return f"Error sending email: {e}"
