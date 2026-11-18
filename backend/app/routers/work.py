import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..calc import Context, compute_line
from ..dates import format_dates, parse_dates
from ..db import get_db
from ..models import (Client, InspectorInvoice, Inspector, Job, JobLine, MonthClose, Request, SalesInvoice, User,
                      inspector_invoice_jobs)
from ..security import need
from .crud import _commit, apply, make_crud, to_dict

r = APIRouter()
JOB_RE = re.compile(r"^\d{2}\.\d{2}-\d{1,4}$")
REQ_STATUSES = ["В процессе", "CV отправлены", "Принято в работу", "Выполнено", "Перенос", "Отмена"]


# ---------------------------------------------------------------- requests
def _req_save(o: Request, data, db, user, created):
    if created and not o.owner_id:
        o.owner_id = user.id
    if o.status not in REQ_STATUSES:
        raise HTTPException(422, f"Статус должен быть одним из: {', '.join(REQ_STATUSES)}")
    if o.status in ("Отмена", "Перенос") and not o.cancel_reason:
        raise HTTPException(422, "Укажите причину отмены или переноса")


r.include_router(make_crud(Request, "/requests", order_by=[Request.received_date.desc().nulls_last(), Request.id.desc()],
                           search=["factory", "country", "final_client", "notes"], before_save=_req_save))


@r.get("/request-statuses")
def request_statuses(_=Depends(need("read"))):
    return REQ_STATUSES


@r.post("/requests/{rid}/create-job")
def create_job_from_request(rid: int, data: dict, db: Session = Depends(get_db), user: User = Depends(need("write"))):
    req = db.get(Request, rid)
    if not req or req.deleted:
        raise HTTPException(404, "Заявка не найдена")
    if req.job_id:
        raise HTTPException(400, "По этой заявке уже есть работа")
    number = (data.get("job_number") or "").strip()
    if not JOB_RE.match(number):
        raise HTTPException(422, "Job number должен быть в формате ГГ.КК-ННН, например 26.19-478")
    if not req.client_id:
        raise HTTPException(422, "В заявке не указан клиент")
    job = Job(job_number=number, client_id=req.client_id, country=req.country, vendor=req.factory,
              owner_id=req.owner_id or user.id, status="В работе")
    db.add(job)
    db.flush()
    req.job_id = job.id
    req.status = "Принято в работу"
    _commit(db)
    return job_dict(job, db, Context(db))


# ---------------------------------------------------------------- jobs
def job_dict(job: Job, db: Session, ctx: Context, with_lines: bool = False) -> dict:
    d = to_dict(job)
    client = ctx.client(job.client_id)
    d["client_name"] = client.name if client else None
    owner = db.get(User, job.owner_id) if job.owner_id else None
    d["owner"] = owner.initials if owner else None
    lines = [l for l in job.lines if not l.deleted]
    totals = {"base_inr": 0.0, "net_inr": 0.0, "man_days": 0.0}
    out_lines = []
    for l in lines:
        c = compute_line(l, job, ctx)
        for k in totals:
            totals[k] += c[k] or 0
        if with_lines:
            ld = to_dict(l)
            insp = db.get(Inspector, l.inspector_id) if l.inspector_id else None
            ld["inspector_name"] = insp.name if insp else None
            ld["calc"] = c
            out_lines.append(ld)
    d["totals"] = {k: round(v, 2) for k, v in totals.items()}
    d["months"] = sorted({l.month for l in lines})
    if with_lines:
        d["lines"] = out_lines
        d["sales_invoices"] = [to_dict(s) for s in db.scalars(
            select(SalesInvoice).where(SalesInvoice.id.in_({l.sales_invoice_id for l in lines if l.sales_invoice_id})))]
        d["inspector_invoices"] = [to_dict(i) for i in db.scalars(
            select(InspectorInvoice).join(inspector_invoice_jobs).where(inspector_invoice_jobs.c.job_id == job.id))]
    return d


@r.get("/jobs")
def list_jobs(status: str | None = None, q: str | None = None, db: Session = Depends(get_db), _=Depends(need("read"))):
    stmt = select(Job).where(Job.deleted.is_(False)).order_by(Job.id.desc())
    if status:
        stmt = stmt.where(Job.status.in_(status.split(",")))
    if q:
        stmt = stmt.where(Job.job_number.ilike(f"%{q}%") | Job.vendor.ilike(f"%{q}%") | Job.client_job_number.ilike(f"%{q}%"))
    ctx = Context(db)
    return [job_dict(j, db, ctx) for j in db.scalars(stmt)]


@r.get("/jobs/{jid}")
def get_job(jid: int, db: Session = Depends(get_db), _=Depends(need("read"))):
    job = db.get(Job, jid)
    if not job or job.deleted:
        raise HTTPException(404, "Работа не найдена")
    return job_dict(job, db, Context(db), with_lines=True)


def _check_job(data: dict, db: Session, exclude_id: int | None = None):
    num = data.get("job_number")
    if num is not None and not JOB_RE.match(str(num).strip()):
        raise HTTPException(422, "Job number должен быть в формате ГГ.КК-ННН, например 26.19-478")
    if "status" in data and data["status"] not in ("В работе", "Пауза", "Сдан"):
        raise HTTPException(422, "Статус работы: В работе, Пауза или Сдан")


@r.post("/jobs")
def create_job(data: dict, db: Session = Depends(get_db), user: User = Depends(need("write"))):
    _check_job(data, db)
    job = Job()
    apply(job, data)
    if not job.owner_id:
        job.owner_id = user.id
    if not job.client_id or not job.job_number:
        raise HTTPException(422, "Нужны Job number и клиент")
    db.add(job)
    _commit(db)
    return job_dict(job, db, Context(db))


@r.patch("/jobs/{jid}")
def update_job(jid: int, data: dict, db: Session = Depends(get_db), _=Depends(need("write"))):
    job = db.get(Job, jid)
    if not job or job.deleted:
        raise HTTPException(404, "Работа не найдена")
    _check_job(data, db)
    apply(job, data)
    _commit(db)
    return job_dict(job, db, Context(db))


@r.delete("/jobs/{jid}")
def delete_job(jid: int, db: Session = Depends(get_db), _=Depends(need("delete"))):
    job = db.get(Job, jid)
    if not job:
        raise HTTPException(404, "Работа не найдена")
    job.deleted = True
    _commit(db)
    return {"ok": True}


# ---------------------------------------------------------------- job lines
def _closed(db: Session, month: str) -> bool:
    return db.get(MonthClose, month) is not None


def _line_check(line: JobLine):
    if not re.match(r"^\d{4}-\d{2}$", line.month or ""):
        raise HTTPException(422, "Месяц в формате ГГГГ-ММ")
    if line.unit == "day" and not line.no_subcontractor and not line.inspector_rate:
        raise HTTPException(422, "Укажите ставку инспектору или отметьте «без подрядчика»")
    if line.currency not in ("USD", "EUR", "INR", "GBP"):
        raise HTTPException(422, "Валюта: USD, EUR, GBP или INR")


@r.get("/lines")
def list_lines(month: str | None = None, db: Session = Depends(get_db), _=Depends(need("read"))):
    stmt = select(JobLine).where(JobLine.deleted.is_(False)).order_by(JobLine.month.desc(), JobLine.id)
    if month:
        stmt = stmt.where(JobLine.month == month)
    ctx = Context(db)
    users = {u.id: u.initials for u in db.scalars(select(User))}
    insp = {i.id: i.name for i in db.scalars(select(Inspector))}
    out = []
    for l in db.scalars(stmt):
        job = l.job
        if job.deleted:
            continue
        d = to_dict(l)
        client = ctx.client(job.client_id)
        d.update(job_number=job.job_number, job_status=job.status, client_name=client.name if client else None,
                 country=job.country, owner=users.get(job.owner_id), inspector_name=insp.get(l.inspector_id),
                 calc=compute_line(l, job, ctx))
        out.append(d)
    return out


@r.post("/lines")
def create_line(data: dict, db: Session = Depends(get_db), _=Depends(need("write"))):
    line = JobLine()
    apply(line, data)
    if not line.job_id or not db.get(Job, line.job_id):
        raise HTTPException(422, "Не указана работа")
    if _closed(db, line.month):
        raise HTTPException(400, f"Месяц {line.month} закрыт, правки запрещены")
    _line_check(line)
    db.add(line)
    _commit(db)
    return to_dict(line)


@r.patch("/lines/{lid}")
def update_line(lid: int, data: dict, db: Session = Depends(get_db), _=Depends(need("write"))):
    line = db.get(JobLine, lid)
    if not line or line.deleted:
        raise HTTPException(404, "Строка не найдена")
    if _closed(db, line.month) or ("month" in data and _closed(db, data["month"])):
        raise HTTPException(400, f"Месяц {line.month} закрыт, правки запрещены")
    apply(line, data, {"snap_fx", "snap_gst", "snap_tds", "snap_admin", "snap_indian", "snap_rko_inr"})
    _line_check(line)
    _commit(db)
    return to_dict(line)


@r.delete("/lines/{lid}")
def delete_line(lid: int, db: Session = Depends(get_db), _=Depends(need("delete"))):
    line = db.get(JobLine, lid)
    if not line:
        raise HTTPException(404, "Строка не найдена")
    if _closed(db, line.month):
        raise HTTPException(400, "Месяц закрыт")
    line.deleted = True
    _commit(db)
    return {"ok": True}


# ---------------------------------------------------------------- calendar of agreed dates
@r.get("/calendar")
def calendar(month: str, db: Session = Depends(get_db), _=Depends(need("read"))):
    """Every agreed inspection day in `month`, read from the lines' «Даты» field."""
    y, m = int(month[:4]), int(month[5:7])
    near = {f"{y - (m == 1)}-{(m - 2) % 12 + 1:02d}", month, f"{y + (m == 12)}-{m % 12 + 1:02d}"}
    users = {u.id: u.initials for u in db.scalars(select(User))}
    insp = {i.id: i.name for i in db.scalars(select(Inspector))}
    clients = {c.id: c.name for c in db.scalars(select(Client))}
    out = []
    for l in db.scalars(select(JobLine).where(JobLine.deleted.is_(False), JobLine.month.in_(near))):
        job = l.job
        if job.deleted:
            continue
        for d in parse_dates(l.dates_text, l.month):
            if d.year == y and d.month == m:
                out.append({"date": d.isoformat(), "job_id": job.id, "job_number": job.job_number, "line_id": l.id,
                            "client": clients.get(job.client_id), "inspector": insp.get(l.inspector_id),
                            "country": job.country, "status": job.status, "owner": users.get(job.owner_id)})
    return sorted(out, key=lambda x: (x["date"], x["job_number"]))


@r.post("/dates/normalize")
def normalize_dates(data: dict, _=Depends(need("read"))):
    """Turn a list of ISO dates into the «Даты» text, and back."""
    if "dates" in data:
        import datetime as _dt
        return {"text": format_dates([_dt.date.fromisoformat(x) for x in data["dates"]])}
    return {"dates": [d.isoformat() for d in parse_dates(data.get("text"), data.get("month"))]}
