"""Gmail API sender using OAuth 2.0 (no Gmail App Password required)."""
from __future__ import annotations

import base64
import json
from email.message import EmailMessage
from pathlib import Path

from django.conf import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _credentials_paths() -> tuple[Path, Path]:
    credentials_path = Path(settings.GMAIL_CREDENTIALS_FILE)
    token_path = Path(settings.GMAIL_TOKEN_FILE)
    return credentials_path, token_path


def _load_credentials():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise RuntimeError(
            "Gmail API paketlari o‘rnatilmagan. requirements.txt dan pip install -r requirements.txt qiling."
        ) from exc

    credentials_path, token_path = _credentials_paths()
    creds = None

    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "Gmail token.json buzilgan. `python manage.py gmail_auth` ni qayta ishga tushiring."
            ) from exc

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            raise RuntimeError(
                "Gmail OAuth tokenini yangilab bo‘lmadi. `python manage.py gmail_auth` ni qayta ishga tushiring."
            ) from exc
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if not credentials_path.exists():
        raise RuntimeError(
            "Gmail OAuth credentials.json topilmadi. Google Cloud'dan Desktop app OAuth JSON faylini "
            "yuklab, StartApp/credentials.json nomi bilan saqlang. Keyin `python manage.py gmail_auth` ni ishga tushiring."
        )

    raise RuntimeError(
        "Gmail hali avtorizatsiya qilinmagan. Avval `python manage.py gmail_auth` ni ishga tushiring."
    )


def gmail_is_configured() -> bool:
    credentials_path, token_path = _credentials_paths()
    return credentials_path.exists() and token_path.exists()


def authorize_gmail() -> None:
    """Run one-time local OAuth consent and save a refresh token."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError(
            "Gmail API paketlari o‘rnatilmagan. `pip install -r requirements.txt` qiling."
        ) from exc

    credentials_path, token_path = _credentials_paths()
    if not credentials_path.exists():
        raise RuntimeError(
            f"OAuth credentials fayli topilmadi: {credentials_path}. "
            "Google Cloud'dan Desktop app OAuth JSON faylini yuklab, shu nom bilan saqlang."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")


def send_gmail_message(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> str:
    """Send one message through Gmail API and return its Gmail message id."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError as exc:
        raise RuntimeError(
            "Gmail API paketlari o‘rnatilmagan. `pip install -r requirements.txt` qiling."
        ) from exc

    creds = _load_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    message = EmailMessage()
    sender = settings.GMAIL_SENDER_EMAIL.strip()
    if not sender:
        raise RuntimeError("GMAIL_SENDER_EMAIL sozlanmagan.")

    message["To"] = to_email
    message["From"] = sender
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    try:
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
    except HttpError as exc:
        detail = getattr(exc, "content", b"")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        raise RuntimeError(f"Gmail API xatosi: {detail or exc}") from exc

    return result.get("id", "")
