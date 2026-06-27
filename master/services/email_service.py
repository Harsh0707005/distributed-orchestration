import smtplib
from email.message import EmailMessage
from typing import List

EMAIL_USER = "devops@arrivalhaul.com"
EMAIL_PASS = "tjpc mxcz yrru lhzx"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def send_email(recipients: List[str], subject: str, body: str) -> bool:
    if not recipients:
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = ", ".join(recipients)
        msg.set_content(body)

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)

        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


