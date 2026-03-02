"""Passwordless auth: email OTP via SendGrid SMTP. Session stored in cookie."""
import os
import random
import smtplib
import string
from email.mime.text import MIMEText
from functools import wraps
from typing import Optional

from flask import session

from config import ALLOWED_EMAILS, EMAIL_FROM, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

# In-memory OTP store: email_lower -> { code, expires_at } (production: use Redis or short TTL store)
_otp_store: dict = {}
OTP_TTL_SECONDS = 600  # 10 min
OTP_LENGTH = 6


def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=OTP_LENGTH))


def is_allowed_email(email: str) -> bool:
    return (email or "").strip().lower() in ALLOWED_EMAILS


def send_otp(email: str) -> Optional[str]:
    """Send OTP to email. Returns None on success, error message on failure."""
    email = (email or "").strip().lower()
    if not is_allowed_email(email):
        return "This email is not allowed to sign in."
    if not SMTP_USER or not SMTP_PASSWORD or not EMAIL_FROM:
        return "Email is not configured. Contact an administrator."
    code = _generate_code()
    import time
    _otp_store[email] = {"code": code, "expires_at": time.time() + OTP_TTL_SECONDS}
    msg = MIMEText(f"Your Kinly Lead Distribution sign-in code is: {code}\n\nIt expires in 10 minutes.")
    msg["Subject"] = "Your sign-in code"
    msg["From"] = EMAIL_FROM
    msg["To"] = email
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, [email], msg.as_string())
    except Exception as e:
        return str(e)
    return None


def verify_otp(email: str, code: str) -> bool:
    """Verify OTP and return True if valid."""
    email = (email or "").strip().lower()
    entry = _otp_store.get(email)
    if not entry:
        return False
    import time
    if time.time() > entry["expires_at"]:
        del _otp_store[email]
        return False
    if entry["code"] != (code or "").strip():
        return False
    del _otp_store[email]
    return True


def login_user(email: str) -> None:
    session["email"] = email.strip().lower()
    session.permanent = True


def logout_user() -> None:
    session.pop("email", None)


def current_user() -> Optional[str]:
    return session.get("email")


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user():
            from flask import jsonify
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapped
