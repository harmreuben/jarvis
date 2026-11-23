"""Contacts, WhatsApp and email. Every message is shown in a Yes/No box before it is sent."""
import email
import email.header
import email.utils
import imaplib
import json
import os
import re
import smtplib
import ssl
import sys
import time
import urllib.parse
import webbrowser
from email.message import EmailMessage

from backend.core import actions, config

CONTACTS_PATH = os.path.join(config.ROOT_DIR, "config", "contacts.json")

MAIL_SERVERS = {  # domain -> (IMAP host, SMTP host, SMTP SSL port)
    "gmail.com": ("imap.gmail.com", "smtp.gmail.com", 465),
    "googlemail.com": ("imap.gmail.com", "smtp.gmail.com", 465),
    "yahoo.com": ("imap.mail.yahoo.com", "smtp.mail.yahoo.com", 465),
    "icloud.com": ("imap.mail.me.com", "smtp.mail.me.com", 587),
    "me.com": ("imap.mail.me.com", "smtp.mail.me.com", 587),
    "zoho.com": ("imap.zoho.com", "smtp.zoho.com", 465),
}


# ---------------- contacts ----------------
def load_contacts() -> dict:
    try:
        with open(CONTACTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_contacts(data: dict) -> None:
    os.makedirs(os.path.dirname(CONTACTS_PATH), exist_ok=True)
    with open(CONTACTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_contact(name: str, phone: str = "", email_addr: str = "") -> str:
    name = name.strip()
    if not name:
        return "What's the contact's name?"
    data = load_contacts()
    entry = data.get(name, {})
    if phone:
        entry["phone"] = re.sub(r"[^\d+]", "", phone)
    if email_addr:
        entry["email"] = email_addr.strip()
    data[name] = entry
    _save_contacts(data)
    return f"Saved {name}: " + ", ".join(f"{k} {v}" for k, v in entry.items())


def remove_contact(name: str) -> str:
    data = load_contacts()
    key = _match_contact(name, data)
    if not key:
        return f"There's no contact called {name}."
    del data[key]
    _save_contacts(data)
    return f"Removed {key} from your contacts."


def list_contacts() -> str:
    data = load_contacts()
    if not data:
        return "No contacts saved yet. Say for example: 'save John's number as +254712345678'."
    return "\n".join(f"{n}: " + ", ".join(f"{k} {v}" for k, v in d.items()) for n, d in sorted(data.items()))


def _match_contact(name: str, data: dict):
    n = name.strip().lower()
    for key in data:
        if key.lower() == n:
            return key
    matches = [k for k in data if n in k.lower() or k.lower() in n]
    return matches[0] if len(matches) == 1 else None


# ---------------- WhatsApp ----------------
def _international(number: str) -> str:
    digits = re.sub(r"[^\d+]", "", number)
    if digits.startswith("+"):
        return digits[1:]
    if digits.startswith("00"):
        return digits[2:]
    code = re.sub(r"\D", "", str(config.load().get("COUNTRY_CODE") or ""))
    if digits.startswith("0"):
        if not code:
            raise ValueError("I need the country code for that number. Save it with the code (like +254...) "
                             "or set your phone country code in Settings.")
        return code + digits[1:]
    return digits


def send_whatsapp(to: str, message: str) -> str:
    contacts = load_contacts()
    key = _match_contact(to, contacts)
    if key and contacts[key].get("phone"):
        number, label = contacts[key]["phone"], key
    elif re.sub(r"[^\d]", "", to) and len(re.sub(r"[^\d]", "", to)) >= 7:
        number, label = to, to
    else:
        return f"I don't have a phone number for {to}. Say 'save {to}'s number as ...' first."
    phone = _international(number)
    if not actions.confirm("send WhatsApp", f"Send this WhatsApp message to {label} (+{phone})?\n\n{message}"):
        return "Okay, I didn't send it."
    text = urllib.parse.quote(message)
    delay = float(config.load().get("WHATSAPP_SEND_DELAY", 6))
    try:
        if sys.platform != "win32":
            raise OSError("no WhatsApp Desktop")
        os.startfile(f"whatsapp://send?phone={phone}&text={text}")  # WhatsApp Desktop app
    except OSError:
        webbrowser.open(f"https://web.whatsapp.com/send?phone={phone}&text={text}")  # WhatsApp Web (must be logged in)
        delay += 10
    import pyautogui
    time.sleep(delay)  # wait for the chat to open with the text filled in
    pyautogui.press("enter")
    return f"Sent your WhatsApp message to {label}."


# ---------------- email ----------------
def _mail_settings():
    cfg = config.load()
    addr = (cfg.get("EMAIL_ADDRESS") or "").strip()
    password = (cfg.get("EMAIL_APP_PASSWORD") or "").replace(" ", "")
    domain = addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""
    servers = MAIL_SERVERS.get(domain)
    if cfg.get("EMAIL_IMAP_HOST"):
        servers = (cfg["EMAIL_IMAP_HOST"], cfg.get("EMAIL_SMTP_HOST", ""), int(cfg.get("EMAIL_SMTP_PORT", 465)))
    return addr, password, servers


def _resolve_email(to: str) -> str:
    if "@" in to:
        return to.strip()
    contacts = load_contacts()
    key = _match_contact(to, contacts)
    if key and contacts[key].get("email"):
        return contacts[key]["email"]
    raise ValueError(f"I don't have an email address for {to}. Say 'save {to}'s email as ...' first.")


def send_email(to: str, subject: str, body: str) -> str:
    address = _resolve_email(to)
    addr, password, servers = _mail_settings()
    if not (addr and password and servers):
        # No mailbox set up: open a ready-to-send draft in the default mail app instead.
        if not actions.confirm("email draft", f"Open an email draft to {address}?\n\nSubject: {subject}\n\n{body}"):
            return "Okay, cancelled."
        webbrowser.open("mailto:" + address + "?" + urllib.parse.urlencode({"subject": subject, "body": body}, quote_via=urllib.parse.quote))
        return f"I opened a draft to {address} in your mail app. (Set up email in Settings and I can send directly.)"
    if not actions.confirm("send email", f"Send this email from {addr}?\n\nTo: {address}\nSubject: {subject}\n\n{body}"):
        return "Okay, I didn't send it."
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = addr, address, subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg.set_content(body)
    _, smtp_host, port = servers
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(smtp_host, port, context=ctx, timeout=30) as s:
            s.login(addr, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, port, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(addr, password)
            s.send_message(msg)
    return f"Email sent to {address}."


def _decode(value) -> str:
    if not value:
        return ""
    parts = []
    for text, enc in email.header.decode_header(value):
        parts.append(text.decode(enc or "utf-8", errors="replace") if isinstance(text, bytes) else text)
    return "".join(parts)


def _body_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                from bs4 import BeautifulSoup
                html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                return BeautifulSoup(html, "html.parser").get_text(" ")
        return ""
    payload = msg.get_payload(decode=True) or b""
    text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    if msg.get_content_type() == "text/html":
        from bs4 import BeautifulSoup
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    return text


def check_email(count: int = 5, unread_only: bool = True) -> str:
    addr, password, servers = _mail_settings()
    if not (addr and password and servers):
        return ("Email isn't set up yet. Open Settings and enter your email address and an app password "
                "(for Gmail: myaccount.google.com/apppasswords).")
    count = max(1, min(int(count or 5), 15))
    imap = imaplib.IMAP4_SSL(servers[0], timeout=30)
    try:
        imap.login(addr, password)
        imap.select("INBOX", readonly=True)  # read-only: checking mail doesn't mark it as read
        status, data = imap.search(None, "UNSEEN" if unread_only else "ALL")
        ids = data[0].split() if status == "OK" and data and data[0] else []
        if not ids:
            return "No unread emails." if unread_only else "Your inbox is empty."
        out = [f"{len(ids)} {'unread ' if unread_only else ''}email(s). Latest {min(count, len(ids))}:"]
        for num in reversed(ids[-count:]):
            status, msg_data = imap.fetch(num, "(BODY.PEEK[])")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            body = re.sub(r"\s+", " ", _body_text(msg)).strip()[:400]
            out.append(f"- From {_decode(msg.get('From'))} | {_decode(msg.get('Date'))} | Subject: {_decode(msg.get('Subject'))}\n  {body}")
        return "\n".join(out)
    finally:
        try:
            imap.logout()
        except Exception:
            pass
