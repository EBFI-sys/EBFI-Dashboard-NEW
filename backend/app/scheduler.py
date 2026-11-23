"""Background jobs of the API process: Telegram linking and the 09:00 digest."""
import datetime as dt
import logging
import os
import threading
import time

from sqlalchemy import select

from . import clock, digest, telegram
from .config import settings
from .db import SessionLocal
from .models import Setting, User

log = logging.getLogger("ebfi.scheduler")
_started = False


def _get(db, key: str) -> str | None:
    row = db.get(Setting, key)
    return row.value if row else None


def _set(db, key: str, value: str) -> None:
    row = db.get(Setting, key) or Setting(key=key, value=value)
    row.value = value
    db.add(row)
    db.commit()


def base_url() -> str:
    site = os.getenv("SITE_ADDRESS", "").strip()
    if not site or site.startswith(":"):
        return ""
    return site if site.startswith("http") else f"https://{site}"


def link_code(db, user: User) -> str:
    """One-time code for «/start CODE» in the bot chat, valid for an hour."""
    import secrets
    code = secrets.token_hex(4)
    _set(db, f"tglink:{code}", f"{user.id}|{clock.now().isoformat()}")
    return code


def poll_telegram() -> None:
    with SessionLocal() as db:
        offset = int(_get(db, "tg:offset") or 0)
        for u in telegram.updates(offset):
            offset = max(offset, u["update_id"] + 1)
            msg = u.get("message") or {}
            chat, txt = str((msg.get("chat") or {}).get("id", "")), (msg.get("text") or "").strip()
            if not chat:
                continue
            if txt.startswith("/start"):
                code = txt.split(maxsplit=1)[1].strip() if " " in txt else ""
                row = db.get(Setting, f"tglink:{code}") if code else None
                if not row:
                    telegram.send(chat, "Откройте EBFI Ops → Профиль → «Подключить Telegram» и нажмите ссылку оттуда.")
                    continue
                uid, at = row.value.split("|")
                db.delete(row)
                user = db.get(User, int(uid))
                if not user or clock.now() - dt.datetime.fromisoformat(at) > dt.timedelta(hours=1):
                    db.commit()
                    telegram.send(chat, "Ссылка устарела. Нажмите «Подключить Telegram» в профиле ещё раз.")
                    continue
                user.telegram_chat_id, user.digest = chat, True
                db.commit()
                telegram.send(chat, f"Готово, {user.name.split()[0]}! Каждый день в {settings.digest_time} (время Индии) "
                                    "сюда будет приходить сводка: отчёты за вчера, работы, которые пора завершить, "
                                    "заявки в процессе. /stop — отключить.")
            elif txt.startswith("/stop"):
                for user in db.scalars(select(User).where(User.telegram_chat_id == chat)):
                    user.digest = False
                db.commit()
                telegram.send(chat, "Сводка отключена. Включить снова — в профиле EBFI Ops.")
        _set(db, "tg:offset", str(offset))


def send_digests(force_user: int | None = None) -> int:
    n = 0
    with SessionLocal() as db:
        q = select(User).where(User.telegram_chat_id.is_not(None), User.active.is_(True), User.role != "archived")
        for user in db.scalars(q):
            if force_user and user.id != force_user:
                continue
            if not force_user and not user.digest:
                continue
            msg = digest.text(db, user, base_url())
            if msg is None and force_user:
                msg = "EBFI Ops: на сегодня нет отчётов к сдаче, работ к завершению и заявок в процессе."
            if msg:
                try:
                    telegram.send(user.telegram_chat_id, msg)
                    n += 1
                except Exception as e:  # noqa: BLE001 - one blocked chat must not stop the others
                    log.warning("digest to %s: %s", user.initials, e)
    return n


def _due(db, key: str, at: str) -> bool:
    now = clock.now()
    hh, mm = (int(x) for x in at.split(":"))
    return now.time() >= dt.time(hh, mm) and _get(db, key) != now.date().isoformat()


def tick() -> None:
    if telegram.enabled():
        try:
            poll_telegram()
        except Exception as e:  # noqa: BLE001
            log.warning("telegram poll: %s", e)
    with SessionLocal() as db:
        if telegram.enabled() and _due(db, "digest:last", settings.digest_time):
            _set(db, "digest:last", clock.today().isoformat())
            log.warning("morning digest sent to %s users", send_digests())


def start() -> None:
    global _started
    if _started or os.getenv("EBFI_NO_SCHEDULER"):
        return
    _started = True

    def loop():
        time.sleep(5)
        while True:
            try:
                tick()
            except Exception:  # noqa: BLE001
                log.exception("scheduler tick")
            time.sleep(20)

    threading.Thread(target=loop, name="ebfi-scheduler", daemon=True).start()
