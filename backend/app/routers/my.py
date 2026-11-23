"""«Мой день» and the Telegram digest settings in the profile."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import digest, scheduler, telegram
from ..config import settings
from ..db import get_db
from ..models import User
from ..security import current_user, need

r = APIRouter()


@r.get("/my-day")
def my_day(scope: str = "me", db: Session = Depends(get_db), user: User = Depends(need("read"))):
    """scope=me: the user's own work («Чья»); scope=all: everybody's."""
    return digest.my_day(db, None if scope == "all" else user.id)


@r.get("/me/telegram")
def tg_status(user: User = Depends(current_user)):
    bot = None
    if telegram.enabled():
        try:
            bot = telegram.bot_name()
        except Exception:  # noqa: BLE001
            bot = None
    return {"enabled": telegram.enabled(), "bot": bot, "linked": bool(user.telegram_chat_id), "digest": user.digest,
            "time": settings.digest_time}


@r.post("/me/telegram/link")
def tg_link(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not telegram.enabled():
        raise HTTPException(400, "Telegram-бот не настроен на сервере (TELEGRAM_BOT_TOKEN)")
    try:
        bot = telegram.bot_name()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Telegram: {e}")
    code = scheduler.link_code(db, db.get(User, user.id))
    return {"url": f"https://t.me/{bot}?start={code}"}


@r.patch("/me/telegram")
def tg_digest(data: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    u = db.get(User, user.id)
    if "digest" in data:
        u.digest = bool(data["digest"])
    db.commit()
    return {"digest": u.digest}


@r.delete("/me/telegram")
def tg_unlink(db: Session = Depends(get_db), user: User = Depends(current_user)):
    u = db.get(User, user.id)
    u.telegram_chat_id = None
    db.commit()
    return {"ok": True}


@r.post("/me/telegram/test")
def tg_test(user: User = Depends(current_user)):
    if not user.telegram_chat_id:
        raise HTTPException(400, "Сначала подключите Telegram")
    try:
        scheduler.send_digests(force_user=user.id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Telegram: {e}")
    return {"ok": True}
