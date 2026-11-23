"""Telegram bot: sends the morning digest. A user links their chat from «Профиль» with a one-time /start code."""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from .config import settings

log = logging.getLogger("ebfi.telegram")


def enabled() -> bool:
    return bool(settings.telegram_token)


def _call(method: str, data: dict | None = None, timeout: int = 30) -> dict:
    url = f"https://api.telegram.org/bot{settings.telegram_token}/{method}"
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            out = json.loads(e.read())
        except Exception:  # noqa: BLE001
            out = {"ok": False, "description": str(e)}
    except urllib.error.URLError as e:
        raise RuntimeError(f"нет связи с Telegram: {e.reason}") from None
    if not out.get("ok"):
        raise RuntimeError(out.get("description") or "ошибка Telegram")
    return out["result"]


_me: dict | None = None


def bot_name() -> str | None:
    global _me
    if not enabled():
        return None
    if _me is None:
        _me = _call("getMe")
    return _me.get("username")


def send(chat_id: str, text: str) -> None:
    """HTML text; long digests are split into Telegram-sized parts."""
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) > 3800:
            parts.append(cur)
            cur = ""
        cur += line + "\n"
    parts.append(cur)
    for p in parts:
        if p.strip():
            _call("sendMessage", {"chat_id": chat_id, "text": p, "parse_mode": "HTML", "disable_web_page_preview": True})


def updates(offset: int, timeout: int = 0) -> list[dict]:
    return _call("getUpdates", {"offset": offset, "timeout": timeout, "allowed_updates": ["message"]}, timeout=timeout + 15)
