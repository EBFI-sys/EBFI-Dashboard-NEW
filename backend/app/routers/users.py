import re
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditLog, User
from ..security import hash_password, need
from .crud import to_dict

r = APIRouter()
HIDE = {"password_hash", "totp_secret", "telegram_chat_id"}
ROLES = {"admin", "accountant", "manager", "archived"}


@r.get("/users")
def list_users(db: Session = Depends(get_db), _=Depends(need("read"))):
    # everybody needs the list to show «Чья» and to pick a coordinator
    return [{k: v for k, v in to_dict(u, HIDE).items()} for u in db.scalars(select(User).order_by(User.name))]


class UserIn(BaseModel):
    name: str
    email: str
    initials: str
    role: str = "manager"
    legacy_letters: str | None = None
    color: str | None = None


def _temp_password() -> str:
    return secrets.token_urlsafe(9)


@r.post("/users")
def create_user(data: UserIn, db: Session = Depends(get_db), _=Depends(need("users"))):
    if data.role not in ROLES:
        raise HTTPException(422, "Неизвестная роль")
    pw = _temp_password()
    u = User(name=data.name, email=data.email.strip().lower(), initials=data.initials.strip().upper(),
             role=data.role, legacy_letters=data.legacy_letters, color=data.color or None, password_hash=hash_password(pw))
    db.add(u)
    db.commit()
    return {**to_dict(u, HIDE), "temp_password": pw}


@r.patch("/users/{uid}")
def update_user(uid: int, data: dict, db: Session = Depends(get_db), _=Depends(need("users"))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Не найдено")
    if "color" in data and data["color"] and not re.match(r"^#[0-9a-fA-F]{6}$", data["color"]):
        raise HTTPException(422, "Цвет в формате #rrggbb")
    for k in ("name", "email", "initials", "role", "active", "legacy_letters", "color"):
        if k in data:
            if k == "role" and data[k] not in ROLES:
                raise HTTPException(422, "Неизвестная роль")
            setattr(u, k, data[k])
    db.commit()
    return to_dict(u, HIDE)


@r.post("/users/{uid}/reset-password")
def reset_password(uid: int, db: Session = Depends(get_db), _=Depends(need("users"))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Не найдено")
    pw = _temp_password()
    u.password_hash = hash_password(pw)
    u.failed_logins, u.locked_until = 0, None
    db.commit()
    return {"temp_password": pw}


@r.post("/users/{uid}/reset-totp")
def reset_totp(uid: int, db: Session = Depends(get_db), _=Depends(need("users"))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Не найдено")
    u.totp_enabled, u.totp_secret = False, None
    db.commit()
    return {"ok": True}


@r.get("/audit")
def audit(table: str | None = None, record_id: int | None = None, limit: int = 300,
          db: Session = Depends(get_db), _=Depends(need("read"))):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 2000))
    if table:
        stmt = stmt.where(AuditLog.table_name == table)
    if record_id:
        stmt = stmt.where(AuditLog.record_id == record_id)
    names = {u.id: u.initials for u in db.scalars(select(User))}
    return [{**to_dict(a), "user": names.get(a.user_id)} for a in db.scalars(stmt)]
