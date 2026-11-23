"""The morning digest (09:00 India time, Telegram) and the «Мой день» screen share these lists."""
import datetime as dt
import html

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clock
from .dates import format_dates, parse_dates
from .models import Client, Inspector, Job, Request, User


def _clients(db: Session) -> dict[int, str]:
    return {c.id: c.name for c in db.scalars(select(Client))}


def _job_row(j: Job, dates: list[dt.date], clients: dict, insp: dict) -> dict:
    ids = list(dict.fromkeys(l.inspector_id for l in j.lines if not l.deleted and l.inspector_id))
    return {"id": j.id, "job_number": j.job_number, "client": clients.get(j.client_id), "status": j.status,
            "owner_id": j.owner_id, "country": j.country, "vendor": j.vendor,
            "inspector": ", ".join(insp.get(i, "") for i in ids if insp.get(i)) or None,
            "dates": format_dates(dates) if dates else None, "last_date": max(dates).isoformat() if dates else None}


def my_day(db: Session, owner_id: int | None) -> dict:
    """owner_id None = everybody (admin view)."""
    today = clock.today()
    yesterday, tomorrow = today - dt.timedelta(days=1), today + dt.timedelta(days=1)
    clients = _clients(db)
    insp = {i.id: i.name for i in db.scalars(select(Inspector))}
    q = select(Job).where(Job.deleted.is_(False))
    if owner_id:
        q = q.where(Job.owner_id == owner_id)
    reports, to_close, today_tomorrow = [], [], []
    for j in db.scalars(q.order_by(Job.job_number)):
        ds = sorted({d for l in j.lines if not l.deleted for d in parse_dates(l.dates_text, l.month)})
        if not ds:
            continue
        row = _job_row(j, ds, clients, insp)
        if yesterday in ds:
            reports.append(row)
        if j.status != "Завершен" and ds[-1] < today:
            to_close.append(row)
        if today in ds or tomorrow in ds:
            row2 = dict(row, when=", ".join(w for w, d in (("сегодня", today), ("завтра", tomorrow)) if d in ds))
            today_tomorrow.append(row2)
    rq = select(Request).where(Request.deleted.is_(False), Request.status == "В процессе")
    if owner_id:
        rq = rq.where(Request.owner_id == owner_id)
    requests = [{"id": r.id, "client": clients.get(r.client_id), "country": r.country, "factory": r.factory,
                 "dates": r.dates_text, "received": r.received_date.isoformat() if r.received_date else None,
                 "owner_id": r.owner_id,
                 "days": (today - r.received_date).days if r.received_date else None}
                for r in db.scalars(rq.order_by(Request.received_date.nulls_last(), Request.id))]
    return {"date": today.isoformat(), "yesterday": yesterday.isoformat(), "today_tomorrow": today_tomorrow,
            "reports": reports, "to_close": to_close, "requests": requests}


def _e(s) -> str:
    return html.escape(str(s or "—"))


def text(db: Session, user: User, base_url: str = "") -> str | None:
    """The message for one user; managers get their own jobs, the admin gets everyone's. None = nothing to report."""
    everyone = user.role == "admin"
    d = my_day(db, None if everyone else user.id)
    owners = {u.id: u.initials for u in db.scalars(select(User))}
    tag = (lambda o: f" · {owners.get(o, '—')}") if everyone else (lambda o: "")
    y = dt.date.fromisoformat(d["yesterday"]).strftime("%d.%m")
    out = [f"<b>EBFI Ops · {dt.date.fromisoformat(d['date']).strftime('%d.%m.%Y')}</b>"]
    if d["reports"]:
        out.append(f"\n📝 <b>Отчёты за вчера ({y}) — сдать клиенту</b> ({len(d['reports'])})")
        out += [f"• {_e(r['job_number'])} {_e(r['client'])} — {_e(r['inspector'])}{tag(r['owner_id'])}" for r in d["reports"]]
    if d["to_close"]:
        out.append(f"\n✅ <b>Пора завершить</b> ({len(d['to_close'])})")
        out += [f"• {_e(r['job_number'])} {_e(r['client'])} — последняя дата "
                f"{dt.date.fromisoformat(r['last_date']).strftime('%d.%m')}{tag(r['owner_id'])}" for r in d["to_close"]]
    if d["requests"]:
        out.append(f"\n📨 <b>Заявки в процессе — CV/предложение не отправлены</b> ({len(d['requests'])})")
        for r in d["requests"]:
            waits = f" — ждёт {r['days']} дн." if r["days"] else ""
            when = f", {_e(r['dates'])}" if r["dates"] else ""
            out.append(f"• {_e(r['client'])}, {_e(r['country'])}{when}{waits}{tag(r['owner_id'])}")
    if len(out) == 1:
        return None
    if base_url:
        out.append(f'\n<a href="{base_url}/my">Открыть «Мой день»</a>')
    return "\n".join(out)
