import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, Tuple, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()


def send_email_via_smtp(
    to_email: str,
    subject: str,
    body: str,
    recipient_name: Optional[str] = None,
    is_html: bool = False,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, str]:
    """
    Sends an email using Python's built-in smtplib, with optional attachments.

    Reads configuration from environment variables:
      - SMTP_SERVER (default: 'smtp.gmail.com')
      - SMTP_PORT (default: 587)
      - SMTP_EMAIL or SENDER_EMAIL
      - SMTP_PASSWORD or EMAIL_PASSWORD

    Args:
        to_email: Recipient email address
        subject: Subject line
        body: Body text
        recipient_name: Optional recipient display name
        is_html: If True, sends body as HTML; otherwise plain text
        attachments: Optional list of dicts with keys 'filename', 'content' (bytes or path), 'mime_type'

    Returns:
        (success: bool, message: str)
    """
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    sender_email = os.environ.get("SMTP_EMAIL") or os.environ.get("SENDER_EMAIL")
    sender_password = os.environ.get("SMTP_PASSWORD") or os.environ.get("EMAIL_PASSWORD")

    # Sanity checks
    if not sender_email or not sender_password:
        msg = (
            "SMTP credentials missing. Please set 'SMTP_EMAIL' and 'SMTP_PASSWORD' "
            "(e.g. Gmail App Password) in your .env file."
        )
        print(f"\n[SMTP WARNING] {msg}")
        return False, msg

    if not to_email:
        msg = "Recipient email address is missing."
        print(f"\n[SMTP ERROR] {msg}")
        return False, msg

    # STRICT GUARDRAIL: Sanitize and verify email body for unpopulated placeholders
    try:
        from app.core.guardrails import enforce_email_guardrails
        body, guardrail_actions = enforce_email_guardrails(
            body=body,
            recipient_name=recipient_name,
            auto_heal=True,
            strict_raise=True
        )
        if guardrail_actions:
            print(f"[GUARDRAILS APPLIED] {', '.join(guardrail_actions)}")
    except ValueError as ve:
        err_msg = str(ve)
        print(f"[GUARDRAILS BLOCKED] {err_msg}")
        return False, err_msg
    except Exception as ge:
        import re
        body = re.sub(r"\[\s*(?:applicant|candidate|your|my)?\s*name\s*\]", "Aman Mulla", body, flags=re.I)
        body = re.sub(r"\[\s*(?:your\s+)?phone(?:\s*number)?\s*\]", "+91 9730971586", body, flags=re.I)
        body = re.sub(r"\[\s*linkedin(?:\s*profile)?\s*\]", "LinkedIn: https://www.linkedin.com/in/aman-mulla", body, flags=re.I)
        remaining = [m for m in re.findall(r"\[(?!\s*\])[A-Za-z][A-Za-z0-9\s/_\-]{1,50}\](?!\s*\()", body) if any(c.isalpha() for c in m)]
        if remaining:
            err_msg = f"GUARDRAIL BLOCKED: Unresolved placeholders in body: {', '.join(set(remaining))}"
            print(f"[GUARDRAILS BLOCKED] {err_msg}")
            return False, err_msg

    # Build MIME message (mixed if attachments present, otherwise alternative)
    if attachments:
        msg = MIMEMultipart("mixed")
        msg["From"] = sender_email
        msg["To"] = f"{recipient_name} <{to_email}>" if recipient_name else to_email
        msg["Subject"] = subject

        # Attach body text
        body_part = MIMEText(body, "html" if is_html else "plain", "utf-8")
        msg.attach(body_part)

        # Attach each file safely with base64 encoding
        for att in attachments:
            filename = att.get("filename", "attachment.pdf")
            content = att.get("content")
            mime_type = att.get("mime_type") or ("application/pdf" if filename.lower().endswith(".pdf") else "application/octet-stream")

            # Fallback: If content bytes are missing, load from file_path or default resume location
            if not content:
                file_path = att.get("file_path")
                if file_path and os.path.isfile(file_path):
                    try:
                        with open(file_path, "rb") as f:
                            content = f.read()
                    except Exception as err:
                        print(f"[SMTP ATTACHMENT ERROR] Failed reading file_path {file_path}: {err}")
                elif filename == "Aman_Mulla_Resume.pdf":
                    default_path = os.environ.get("DEFAULT_ATTACHMENT_PATH", "storage/default_attachments/Aman_Mulla_Resume.pdf")
                    if os.path.isfile(default_path):
                        try:
                            with open(default_path, "rb") as f:
                                content = f.read()
                        except Exception as err:
                            print(f"[SMTP ATTACHMENT ERROR] Failed reading default resume {default_path}: {err}")

            if isinstance(content, str) and os.path.isfile(content):
                with open(content, "rb") as f:
                    content = f.read()
            elif isinstance(content, str):
                content = content.encode("utf-8")

            if not content:
                print(f"[SMTP ATTACHMENT WARNING] Skipping '{filename}': empty or unreadable content.")
                continue

            main_type, sub_type = mime_type.split("/", 1) if "/" in mime_type else ("application", "octet-stream")
            part = MIMEBase(main_type, sub_type)
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)
            print(f"[SMTP ATTACHMENT SUCCESS] Attached '{filename}' ({len(content)} bytes, {mime_type}) to email message.")
    else:
        msg = MIMEMultipart("alternative")
        msg["From"] = sender_email
        msg["To"] = f"{recipient_name} <{to_email}>" if recipient_name else to_email
        msg["Subject"] = subject

        mime_type = "html" if is_html else "plain"
        msg.attach(MIMEText(body, mime_type, "utf-8"))

    # Connect and send
    try:
        print(f"\n[SMTP] Connecting to {smtp_server}:{smtp_port}...")
        if smtp_port == 465:
            # SSL connection
            with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30) as server:
                server.login(sender_email, sender_password)
                server.send_message(msg)
        else:
            # STARTTLS connection (standard for port 587)
            with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(sender_email, sender_password)
                server.send_message(msg)

        success_msg = f"Email successfully sent to {to_email} via {smtp_server}:{smtp_port}"
        print(f"[SMTP SUCCESS] {success_msg}")
        return True, success_msg

    except smtplib.SMTPAuthenticationError as e:
        err_msg = (
            f"SMTP Authentication Error: {e.smtp_error.decode() if hasattr(e.smtp_error, 'decode') else e}. "
            "For Gmail, make sure you are using an App Password, NOT your regular account password."
        )
        print(f"[SMTP ERROR] {err_msg}")
        return False, err_msg

    except smtplib.SMTPConnectError as e:
        err_msg = f"Failed to connect to SMTP server {smtp_server}:{smtp_port}: {e}"
        print(f"[SMTP ERROR] {err_msg}")
        return False, err_msg

    except smtplib.SMTPRecipientsRefused as e:
        err_msg = f"Recipient refused ({to_email}): {e}"
        print(f"[SMTP ERROR] {err_msg}")
        return False, err_msg

    except Exception as e:
        err_msg = f"Unexpected SMTP error: {str(e)}"
        print(f"[SMTP ERROR] {err_msg}")
        return False, err_msg


if __name__ == "__main__":
    import sys

    print("--- Test SMTP Email Sender ---")
    recipient = input("Enter recipient email: ").strip() if len(sys.argv) < 2 else sys.argv[1]
    if recipient:
        send_email_via_smtp(
            to_email=recipient,
            subject="Test Email from Agentic AI",
            body="Hello! This is a test email sent using smtplib from the Email Agent.",
            recipient_name="Tester",
        )
    else:
        print("No recipient provided. Exiting.")
