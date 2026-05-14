import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587


def send(subject: str, body: str, to: str, *, _smtp_cls=smtplib.SMTP) -> None:
    gmail_from = os.environ["GMAIL_FROM"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = gmail_from
    msg["To"] = to

    with _smtp_cls(_SMTP_HOST, _SMTP_PORT) as server:
        server.starttls()
        server.login(gmail_from, app_password)
        server.sendmail(gmail_from, [to], msg.as_string())

    logger.info("Digest email sent to %s", to)
