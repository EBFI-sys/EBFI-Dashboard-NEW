from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pyotp
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .db import current_user_id, get_db
from .models import User

COOKIE = "ebfi_session"

# What each role may do. Managers see margins and may record payments (decision of 18 Nov 2026).
ROLE_RIGHTS = {
    "admin": {"read", "write", "settings", "close_month", "users", "delete"},
    "accountant": {"read", "write", "settings", "close_month"},
    "manager": {"read", "write"},
}


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str | None) -> bool:
    return bool(hashed) and bcrypt.checkpw(pw.encode(), hashed.encode())


def make_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)
    return jwt.encode({"sub": str(user.id), "exp": exp}, settings.secret_key, algorithm="HS256")


def _fernet() -> Fernet | None:
    return Fernet(settings.encryption_key.encode()) if settings.encryption_key else None


def encrypt(text: str | None) -> str | None:
    if not text:
        return None
    f = _fernet()
    return f.encrypt(text.encode()).decode() if f else text


def decrypt(token: str | None) -> str | None:
    if not token:
        return None
    f = _fernet()
    if not f:
        return token
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        return token


def totp_ok(user: User, code: str | None) -> bool:
    return bool(user.totp_secret and code and pyotp.TOTP(user.totp_secret).verify(code.strip(), valid_window=1))


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Нужно войти")
    try:
        uid = int(jwt.decode(token, settings.secret_key, algorithms=["HS256"])["sub"])
    except Exception:
        raise HTTPException(401, "Сессия истекла, войдите снова")
    user = db.get(User, uid)
    if not user or not user.active:
        raise HTTPException(401, "Учётная запись отключена")
    current_user_id.set(user.id)
    db.info["user_id"] = user.id  # read by the audit listener (contextvars do not cross FastAPI's threadpool)
    return user


def need(right: str):
    """Dependency: the current user must have `right`; admins must have 2FA turned on."""

    def dep(user: User = Depends(current_user)) -> User:
        if right not in ROLE_RIGHTS.get(user.role, set()):
            raise HTTPException(403, "Недостаточно прав")
        if user.role in ("admin", "accountant") and not user.totp_enabled and right != "read":
            raise HTTPException(403, "Включите двухфакторную аутентификацию в профиле")
        return user

    return dep
