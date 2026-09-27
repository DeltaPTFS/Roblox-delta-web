import base64, hashlib, secrets
from fastapi import HTTPException, Request
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from .config import Settings
from .models import Status, User


def oauth_values(request: Request, provider: str) -> tuple[str, str]:
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    request.session[f"{provider}_state"] = state
    request.session[f"{provider}_verifier"] = verifier
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return state, challenge


def consume_oauth(request: Request, provider: str, state: str) -> str:
    expected = request.session.pop(f"{provider}_state", None)
    verifier = request.session.pop(f"{provider}_verifier", None)
    if not expected or not verifier or not secrets.compare_digest(expected, state):
        raise HTTPException(400, "OAuth state validation failed")
    return verifier


def csrf_token(request: Request) -> str:
    return request.session.setdefault("csrf", secrets.token_urlsafe(24))


def check_csrf(request: Request, supplied: str):
    expected = request.session.get("csrf", "")
    if not expected or not secrets.compare_digest(expected, supplied):
        raise HTTPException(403, "Invalid CSRF token")


def permission(user: User, settings: Settings) -> str:
    roles = set(user.discord_role_ids or [])
    if user.roblox_user_id in settings.ids(settings.owner_roblox_user_ids) or roles & settings.ids(settings.owner_discord_role_ids): return "OWNER"
    if roles & settings.ids(settings.admin_discord_role_ids): return "ADMIN"
    if roles & settings.ids(settings.staff_discord_role_ids): return "STAFF"
    return "MEMBER"


def current_user(request: Request, db: Session) -> User:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    if not user: raise HTTPException(401, "Session expired")
    if user.account_status.value != "ACTIVE" and not user.permanent_ban and user.restricted_until and user.restricted_until <= datetime.now(timezone.utc):
        user.account_status=Status.ACTIVE; user.restricted_until=None; user.restriction_reason=None; db.commit()
    if user.account_status.value != "ACTIVE": raise HTTPException(403, "Account suspended")
    return user
