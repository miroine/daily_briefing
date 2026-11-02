"""Email (SMTP) and Telegram delivery. Credentials come from environment variables or
Streamlit secrets: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_FROM, MAIL_TO,
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_API_KEY."""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests


def get_secret(name: str) -> Optional[str]:
    v = os.environ.get(name)
    if v:
        return v
    try:
        import streamlit as st
        return st.secrets.get(name)  # may raise if no secrets file
    except Exception:
        return None


def email_configured() -> bool:
    return all(get_secret(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_TO"))


def telegram_configured() -> bool:
    return all(get_secret(k) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"))


def send_email(subject: str, html_body: str, text_body: str) -> None:
    host, user, pw = get_secret("SMTP_HOST"), get_secret("SMTP_USER"), get_secret("SMTP_PASS")
    to = get_secret("MAIL_TO")
    port = int(get_secret("SMTP_PORT") or 587)
    sender = get_secret("MAIL_FROM") or user
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, sender, to
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    recipients = [a.strip() for a in to.split(",") if a.strip()]
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as s:
            s.login(user, pw)
            s.sendmail(sender, recipients, msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(user, pw)
            s.sendmail(sender, recipients, msg.as_string())


def send_telegram(text: str, html_doc: Optional[str] = None, filename: str = "brief.html") -> None:
    token, chat = get_secret("TELEGRAM_BOT_TOKEN"), get_secret("TELEGRAM_CHAT_ID")
    base = f"https://api.telegram.org/bot{token}"
    r = requests.post(f"{base}/sendMessage", timeout=20,
                      data={"chat_id": chat, "text": text, "disable_web_page_preview": "true"})
    r.raise_for_status()
    if html_doc:
        r = requests.post(f"{base}/sendDocument", timeout=30, data={"chat_id": chat},
                          files={"document": (filename, html_doc.encode("utf-8"), "text/html")})
        r.raise_for_status()
