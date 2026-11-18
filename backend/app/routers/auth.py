import io
from datetime import datetime, timedelta, timezone

import pyotp
import segno
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import User
from ..security import COOKIE, ROLE_RIGHTS, current_user, hash_password, make_token, totp_ok, verify_password

r = APIRouter(prefix="/auth")


class LoginIn(BaseModel):
    email: str
    password: str
    code: str | None = None


def me_dict(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "initials": u.initials, "role": u.role,
            "totp_enabled": u.totp_enabled, "rights": sorted(ROLE_RIGHTS.get(u.role, [])),
            "totp_required": u.role in ("admin", "accountant")}


@r.post("/login")
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.strip().lower()))
    now = datetime.now(timezone.utc)
    if not user or not user.active or user.role == "archived":
        raise HTTPException(401, "Неверный email или пароль")
    if user.locked_until and user.locked_until > now:
        raise HTTPException(429, "Слишком много попыток. Попробуйте через 15 минут")
    if not verify_password(data.password, user.password_hash):
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_logins = 0
        db.commit()
        raise HTTPException(401, "Неверный email или пароль")
    if user.totp_enabled and not totp_ok(user, data.code):
        raise HTTPException(401, "Нужен код из приложения-аутентификатора" if not data.code else "Неверный код")
    user.failed_logins = 0
    user.locked_until = None
    db.commit()
    response.set_cookie(COOKIE, make_token(user), httponly=True, secure=settings.cookie_secure,
                        samesite="lax", max_age=settings.session_hours * 3600)
    return me_dict(user)


@r.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@r.get("/me")
def me(user: User = Depends(current_user)):
    return me_dict(user)


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


@r.post("/password")
def change_password(data: PasswordIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(400, "Текущий пароль неверный")
    if len(data.new_password) < 10:
        raise HTTPException(400, "Пароль должен быть не короче 10 символов")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"ok": True}


@r.post("/totp/setup")
def totp_setup(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.totp_enabled:
        raise HTTPException(400, "Двухфакторная аутентификация уже включена")
    user.totp_secret = pyotp.random_base32()
    db.commit()
    uri = pyotp.TOTP(user.totp_secret).provisioning_uri(name=user.email, issuer_name="EBFI Ops")
    return {"secret": user.totp_secret, "uri": uri}


@r.get("/totp/qr.svg")
def totp_qr(user: User = Depends(current_user)):
    if not user.totp_secret or user.totp_enabled:
        raise HTTPException(400, "Сначала начните настройку")
    uri = pyotp.TOTP(user.totp_secret).provisioning_uri(name=user.email, issuer_name="EBFI Ops")
    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="svg", scale=6, border=2)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/svg+xml")


class CodeIn(BaseModel):
    code: str


@r.post("/totp/enable")
def totp_enable(data: CodeIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not totp_ok(user, data.code):
        raise HTTPException(400, "Код не подошёл. Проверьте время на телефоне и попробуйте ещё раз")
    user.totp_enabled = True
    db.commit()
    return me_dict(user)
