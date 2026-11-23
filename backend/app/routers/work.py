import datetime as dt
import re

from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from .. import files, sharepoint
from ..calc import Context, compute_line, snap_line
from ..dates import format_dates, parse_dates
from ..db import get_db
from ..directory import remember_country, remember_final_client, remember_vendor
from ..models import (Client, Setting, InspectorInvoice, Inspector, Job, JobLine, MonthClose, Request, SalesInvoice, User,
                      inspector_invoice_jobs)
from ..security import need
from .crud import _commit, apply, make_crud, to_dict

r = APIRouter()
JOB_RE = re.compile(r"^\d{2}\.\d{2}-\d{1,4}$")
REQ_STATUSES = ["В процессе", "Принято в работу", "Выполнено", "Перенос", "Отмена"]


# ---------------------------------------------------------------- requests
def _req_save(o: Request, data, db, user, created):
    if created and not o.owner_id:
        o.owner_id = user.id
    if o.status not in REQ_STATUSES:
        raise HTTPException(422, f"Статус должен быть одним из: {', '.join(REQ_STATUSES)}")
    ids = [int(i) for i in (o.inspector_ids or []) if i]
    o.inspector_ids = list(dict.fromkeys(ids)) or None
    if o.inspector_id and o.inspector_id not in (o.inspector_ids or []):
        o.inspector_ids = [o.inspector_id, *(o.inspector_ids or [])]
    if not o.inspector_id and o.inspector_ids and len(o.inspector_ids) == 1:
        o.inspector_id = o.inspector_ids[0]
    remember_country(db, o.country)
    remember_vendor(db, o.factory, o.country)
    remember_final_client(db, o.final_client)


r.include_router(make_crud(Request, "/requests", order_by=[Request.received_date.desc().nulls_last(), Request.id.desc()],
                           search=["factory", "country", "final_client", "notes"], before_save=_req_save,
                           delete_right="delete_work"))


@r.get("/request-statuses")
def request_statuses(_=Depends(need("read"))):
    return REQ_STATUSES


@r.post("/requests/{rid}/create-job")
def create_job_from_request(rid: int, data: dict, db: Session = Depends(get_db), user: User = Depends(need("write"))):
    """Open a job in the Табель from a request: the number is taken from the client's register, and everything
    entered at the request stage (factory, country, dates, rates, inspectors) is carried over."""
    req = db.get(Request, rid)
    if not req or req.deleted:
        raise HTTPException(404, "Заявка не найдена")
    if req.job_id:
        raise HTTPException(400, "По этой заявке уже есть работа")
    if req.status == "Отмена":
        raise HTTPException(400, "Отменённую заявку нельзя перенести в Табель")
    if not req.client_id:
        raise HTTPException(422, "В заявке не указан клиент")
    dates_text = (data.get("dates_text") or req.dates_text or "").strip()
    if not dates_text or not parse_dates(dates_text, _this_month()):
        raise HTTPException(422, "Укажите даты инспекции: работа в Табеле не может быть без дат" if not dates_text else
                            f"Не понял даты «{dates_text}» — например 05,06.11.2026 или 16-20.11.2026")
    if data.get("dates_text"):
        req.dates_text = dates_text
    number = (data.get("job_number") or "").strip() or next_job_number(db, req.client_id)
    if not JOB_RE.match(number):
        raise HTTPException(422, "Job number должен быть в формате ГГ.КК-ННН, например 26.19-478")
    if db.scalar(select(Job).where(Job.job_number == number)):
        raise HTTPException(409, f"Работа {number} уже есть в Табеле")
    notes = "\n".join(x for x in [f"Финальный клиент: {req.final_client}" if req.final_client else "", req.notes or ""] if x) or None
    job = Job(job_number=number, client_id=req.client_id, country=req.country, vendor=req.factory,
              owner_id=req.owner_id or user.id, status="В работе", notes=notes, service_type=req.type or "Inspection")
    db.add(job)
    db.flush()
    inspectors = [int(i) for i in (data.get("inspector_ids") or ([req.inspector_id] if req.inspector_id else []))]
    client = db.get(Client, req.client_id)
    cur = req.client_currency or (client.default_currency if client else None) or "USD"
    base = {"dates_text": req.dates_text, "unit": "day", "currency": cur, "client_rate": req.client_rate or 0,
            "inspector_rate": req.inspector_rate or 0, "inspector_currency": req.inspector_currency or cur}
    for g, iid in enumerate(inspectors or [None], start=1):
        sync_assignment(db, job, g, {**base, "inspector_id": iid}, strict=False)
    req.job_id = job.id
    if req.status != "Выполнено":
        req.status = "Принято в работу"
    if len(inspectors) == 1:
        req.inspector_id = inspectors[0]
    _commit(db)
    files.ensure_job_folder(db, job)
    return job_dict(job, db, Context(db))


# ---------------------------------------------------------------- job numbers: YY.KK-NNN, one queue per client code
NUM_RE = re.compile(r"^(\d{2})\.(\d{2})-(\d{1,4})$")


def last_seq(db: Session, yy: str, code: str) -> tuple[int, int]:
    """Highest NNN used this year with this client code (the queue restarts at 001 every January),
    from the Табель and from the imported history (setting jobseq:YY:KK). Returns (number, digits)."""
    best, width = 0, 3
    for (n,) in db.execute(select(Job.job_number).where(Job.job_number.like(f"{yy}.{code}-%"))):
        m = NUM_RE.match(n or "")
        if m and int(m[3]) >= best:
            best, width = int(m[3]), len(m[3])
    hist = db.get(Setting, f"jobseq:{yy}:{code}")
    if hist and hist.value.isdigit() and int(hist.value) > best:
        best, width = int(hist.value), max(2, len(hist.value))
    return best, (width if best else 3)


def next_job_number(db: Session, client_id: int) -> str:
    client = db.get(Client, client_id)
    if not client or not client.job_code:
        raise HTTPException(422, f"У клиента {client.name if client else ''} не указан код в номере работы (КК). "
                                 "Укажите его в «Справочники → Клиенты» или введите Job number вручную.")
    code, yy = client.job_code.zfill(2), f"{clock.today():%y}"
    seq, width = last_seq(db, yy, code)
    seq = max(seq, files.server_max(yy, code))  # folders created by hand on OneDrive take their numbers too
    return f"{yy}.{code}-{seq + 1:0{width}d}"


@r.get("/jobs/next-number")
def job_next_number(client_id: int, db: Session = Depends(get_db), _=Depends(need("read"))):
    return {"job_number": next_job_number(db, client_id)}


# ---------------------------------------------------------------- jobs
def _view(job: Job, lines: list[JobLine], month: str) -> dict:
    """The job as the Табель of one month shows it: only the days of that month."""
    ls = [l for l in lines if l.month == month]
    return {"month": month, "dates": sorted({x.isoformat() for l in ls for x in parse_dates(l.dates_text, l.month)
                                             if x.strftime("%Y-%m") == month}),
            "man_days": float(sum(Decimal(l.quantity or 0) for l in ls if l.unit == "day")),
            "quantity": float(sum(Decimal(l.quantity or 0) for l in ls)),
            "dates_text": "; ".join(l.dates_text for l in ls if l.dates_text) or None}


def _flags(job: Job, d: dict, shut: dict, users: dict) -> None:
    """Purple rows: a closed month changed later than 24 h after closing, or a job left open after its month closed."""
    last = d["dates"][-1] if d["dates"] else None
    open_ = job.status != "Завершен"
    d["last_date"] = last
    d["dates_passed"] = bool(open_ and last and last < clock.today().isoformat())
    m = last[:7] if last else None
    d["overdue"] = bool(d["dates_passed"] and m in shut and clock.now() > shut[m] + GRACE)
    d["late_edit_by"] = users.get(job.late_edit_by)
    d["flag"] = d["overdue"] or bool(job.late_edit_at)


def job_dict(job: Job, db: Session, ctx: Context, with_lines: bool = False, month: str | None = None,
             shut: dict | None = None, users: dict | None = None) -> dict:
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
    d["dates"] = sorted({x.isoformat() for l in lines for x in parse_dates(l.dates_text, l.month)})
    d["line_summary"] = [{"id": l.id, "month": l.month, "dates_text": l.dates_text, "inspector_id": l.inspector_id,
                          "closed": l.month in ctx.closed} for l in lines]
    d["totals_by_month"] = {}
    for l in lines:
        c = compute_line(l, job, ctx)
        t = d["totals_by_month"].setdefault(l.month, {"base_inr": 0.0, "net_inr": 0.0})
        t["base_inr"] += c["base_inr"] or 0
        t["net_inr"] += c["net_inr"] or 0
    d["assignments"] = assignments(job, db, ctx)
    d["files_enabled"] = sharepoint.enabled()
    if month:
        d["view"] = _view(job, lines, month)
    _flags(job, d, shut if shut is not None else closes(db),
           users if users is not None else {u.id: u.initials for u in db.scalars(select(User))})
    if with_lines:
        d["lines"] = out_lines
        d["sales_invoices"] = [to_dict(s) for s in db.scalars(
            select(SalesInvoice).where(SalesInvoice.id.in_({l.sales_invoice_id for l in lines if l.sales_invoice_id})))]
        d["inspector_invoices"] = [to_dict(i) for i in db.scalars(
            select(InspectorInvoice).join(inspector_invoice_jobs).where(inspector_invoice_jobs.c.job_id == job.id))]
    return d


@r.get("/jobs")
def list_jobs(status: str | None = None, q: str | None = None, month: str | None = None,
              db: Session = Depends(get_db), _=Depends(need("read"))):
    """The Табель. With `month` only the jobs with days in that month, showing those days; the current month also
    keeps the unfinished jobs whose dates are all in earlier months, so none is lost before it is closed."""
    stmt = select(Job).where(Job.deleted.is_(False)).order_by(Job.id.desc())
    if status:
        stmt = stmt.where(Job.status.in_(status.split(",")))
    if q:
        stmt = stmt.where(Job.job_number.ilike(f"%{q}%") | Job.vendor.ilike(f"%{q}%") | Job.client_job_number.ilike(f"%{q}%"))
    ctx, shut = Context(db), closes(db)
    users = {u.id: u.initials for u in db.scalars(select(User))}
    out = []
    for j in db.scalars(stmt):
        months = {l.month for l in j.lines if not l.deleted}
        if month and month not in months:
            continue
        out.append(job_dict(j, db, ctx, month=month, shut=shut, users=users))
    return out


@r.get("/jobs/unfinished")
def unfinished_jobs(before: str, db: Session = Depends(get_db), _=Depends(need("read"))):
    """Jobs not «Завершен» whose dates are all in months before `before`: shown above the Табель as a reminder."""
    out = []
    for j in db.scalars(select(Job).where(Job.deleted.is_(False), Job.status != "Завершен").order_by(Job.job_number)):
        months = {l.month for l in j.lines if not l.deleted}
        if months and max(months) < before:
            out.append({"id": j.id, "job_number": j.job_number, "month": max(months), "owner_id": j.owner_id})
    return out


@r.post("/jobs/{jid}/late-edit/clear")
def clear_late_edit(jid: int, db: Session = Depends(get_db), _=Depends(need("close_month"))):
    """The accountant has checked the change to a closed month: the purple mark goes."""
    job = db.get(Job, jid)
    if not job or job.deleted:
        raise HTTPException(404, "Работа не найдена")
    job.late_edit_at = job.late_edit_by = job.late_edit_months = None
    _commit(db)
    return {"ok": True}


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
    if "status" in data and data["status"] not in ("В работе", "Пауза", "Завершен"):
        raise HTTPException(422, "Статус работы: В работе, Пауза или Завершен")


@r.post("/jobs")
def create_job(data: dict, db: Session = Depends(get_db), user: User = Depends(need("write"))):
    """A new job with its first inspector and dates: a job without dates cannot be in the Табель."""
    _check_job(data, db)
    first = data.pop("assignment", None) or {}
    job = Job()
    apply(job, data)
    if not job.owner_id:
        job.owner_id = user.id
    if not job.client_id or not job.job_number:
        raise HTTPException(422, "Нужны Job number и клиент")
    if db.scalar(select(Job).where(Job.job_number == job.job_number)):
        raise HTTPException(409, f"Работа {job.job_number} уже есть в Табеле")
    remember_country(db, job.country)
    remember_vendor(db, job.vendor, job.country)
    db.add(job)
    db.flush()
    sync_assignment(db, job, 1, first, user=user)
    _commit(db)
    files.ensure_job_folder(db, job)
    return job_dict(job, db, Context(db))


@r.patch("/jobs/{jid}")
def update_job(jid: int, data: dict, db: Session = Depends(get_db), user: User = Depends(need("write"))):
    job = db.get(Job, jid)
    if not job or job.deleted:
        raise HTTPException(404, "Работа не найдена")
    _check_job(data, db)
    client = job.client_id
    apply(job, data)
    if job.client_id != client:  # the client changes the money of every month, closed ones too
        mark_late(db, job, {l.month for l in job.lines if not l.deleted}, user)
    remember_country(db, job.country)
    remember_vendor(db, job.vendor, job.country)
    _commit(db)
    files.ensure_job_folder(db, job)
    return job_dict(job, db, Context(db))


def _removable(job: Job, db: Session):
    """A job can leave the Табель only while nothing depends on it."""
    closed = {m.month for m in db.scalars(select(MonthClose))}
    lines = [l for l in job.lines if not l.deleted]
    if any(l.month in closed for l in lines):
        raise HTTPException(400, "Есть строки в закрытом месяце — работу нельзя удалить")
    if any(l.sales_invoice_id for l in lines):
        raise HTTPException(400, "Работа уже включена в инвойс клиенту — сначала уберите её из инвойса")
    if db.scalar(select(inspector_invoice_jobs.c.inspector_invoice_id).join(InspectorInvoice)
                 .where(inspector_invoice_jobs.c.job_id == job.id, InspectorInvoice.deleted.is_(False)).limit(1)):
        raise HTTPException(400, "К работе привязан счёт инспектора — сначала отвяжите его")
    return lines


def _drop(job: Job, lines: list[JobLine]):
    # the job number stays taken: deleted jobs keep it, so the queue never hands it out again
    job.deleted = True
    for l in lines:
        l.deleted = True


@r.delete("/jobs/{jid}")
def delete_job(jid: int, db: Session = Depends(get_db), _=Depends(need("delete_work"))):
    job = db.get(Job, jid)
    if not job or job.deleted:
        raise HTTPException(404, "Работа не найдена")
    lines = _removable(job, db)
    for req in db.scalars(select(Request).where(Request.job_id == job.id)):
        req.job_id = None
        req.notes = "\n".join(x for x in [req.notes, f"Работа {job.job_number} удалена из Табеля"] if x)
    _drop(job, lines)
    _commit(db)
    files.archive_job_folder(db, job)
    return {"ok": True}


@r.post("/jobs/{jid}/to-request")
def job_to_request(jid: int, db: Session = Depends(get_db), user: User = Depends(need("write"))):
    """Take a job out of the Табель and put it back to the requests. The request it came from is reopened;
    a job opened without a request gets a new request with everything that was entered."""
    job = db.get(Job, jid)
    if not job or job.deleted:
        raise HTTPException(404, "Работа не найдена")
    lines = _removable(job, db)
    req = db.scalar(select(Request).where(Request.job_id == job.id, Request.deleted.is_(False)))
    note = f"Возвращена из Табеля (была работа {job.job_number})"
    if not req:
        a = (assignments(job, db, Context(db)) or [{}])[0]
        ids = [x["inspector_id"] for x in assignments(job, db, Context(db)) if x.get("inspector_id")]
        req = Request(received_date=clock.today(), type="Inspection", client_id=job.client_id, country=job.country,
                      factory=job.vendor, dates_text=a.get("dates_text"), client_rate=a.get("client_rate"),
                      client_currency=a.get("currency"), inspector_rate=a.get("inspector_rate"),
                      inspector_currency=a.get("inspector_currency"), inspector_ids=ids or None,
                      inspector_id=ids[0] if len(ids) == 1 else None, owner_id=job.owner_id or user.id,
                      notes=job.notes)
        db.add(req)
    req.job_id = None
    req.status = "В процессе"
    req.notes = "\n".join(x for x in [req.notes, note] if x)
    _drop(job, lines)
    _commit(db)
    files.archive_job_folder(db, job)
    return {"ok": True, "request_id": req.id}


# ---------------------------------------------------------------- job lines
def _closed(db: Session, month: str) -> bool:
    return db.get(MonthClose, month) is not None


def _line_check(line: JobLine, strict: bool = True):
    if not re.match(r"^\d{4}-\d{2}$", line.month or ""):
        raise HTTPException(422, "Месяц в формате ГГГГ-ММ")
    if strict and line.unit == "day" and not line.no_subcontractor and not line.inspector_rate:
        raise HTTPException(422, "Укажите ставку инспектору или отметьте «без подрядчика»")
    for c in (line.currency, line.inspector_currency or line.currency):
        if c not in ("USD", "EUR", "INR", "GBP"):
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
def create_line(data: dict, db: Session = Depends(get_db), user: User = Depends(need("write"))):
    line = JobLine()
    apply(line, data)
    job = db.get(Job, line.job_id) if line.job_id else None
    if not job:
        raise HTTPException(422, "Не указана работа")
    _line_check(line)
    db.add(line)
    _snap_new(db, job, [line], closes(db))
    mark_late(db, job, {line.month}, user)
    _commit(db)
    return to_dict(line)


@r.patch("/lines/{lid}")
def update_line(lid: int, data: dict, db: Session = Depends(get_db), user: User = Depends(need("write"))):
    line = db.get(JobLine, lid)
    if not line or line.deleted:
        raise HTTPException(404, "Строка не найдена")
    was, old = _state(line), line.month
    apply(line, data, {"snap_fx", "snap_fx_insp", "snap_gst", "snap_tds", "snap_admin", "snap_indian", "snap_wht", "snap_rko_inr"})
    _line_check(line)
    if old != line.month:
        line.snap_fx = None
        _snap_new(db, line.job, [line], closes(db))
    if was != _state(line) or old != line.month:
        mark_late(db, line.job, {old, line.month}, user)
    _commit(db)
    return to_dict(line)


@r.delete("/lines/{lid}")
def delete_line(lid: int, db: Session = Depends(get_db), user: User = Depends(need("delete_work"))):
    line = db.get(JobLine, lid)
    if not line:
        raise HTTPException(404, "Строка не найдена")
    if line.sales_invoice_id:
        raise HTTPException(400, "Строка уже в инвойсе клиенту")
    line.deleted = True
    mark_late(db, line.job, {line.month}, user)
    _commit(db)
    return {"ok": True}


# ---------------------------------------------------------------- assignments: the job as one row
# A job is one row of the Табель. Behind it the P&L keeps one line per month (a job can run from October into
# November) and per inspector (rarely two inspectors work on one job). Managers edit the assignment as a whole;
# the month lines are rebuilt from its dates. Lines of closed months are never touched.
COMMON = ("inspector_id", "unit", "currency", "client_rate", "inspector_rate", "inspector_currency", "no_subcontractor",
          "payment_method_id", "notes")
LAST_ONLY = ("overtime_client", "overtime_inspector", "rko_override_inr")


def _this_month() -> str:
    return clock.today().strftime("%Y-%m")


TRACKED = ("inspector_id", "dates_text", "quantity", "unit", "currency", "client_rate", "inspector_rate",
           "inspector_currency", "overtime_client", "overtime_inspector", "no_subcontractor", "payment_method_id",
           "rko_override_inr", "deleted")
GRACE = dt.timedelta(hours=24)  # after closing a month, managers have a day to finish it without a mark


def _state(l: JobLine) -> tuple:
    return tuple(str(getattr(l, k)) if getattr(l, k) is not None else "" for k in TRACKED)


def closes(db: Session) -> dict[str, dt.datetime]:
    return {m.month: m.closed_at for m in db.scalars(select(MonthClose))}


def mark_late(db: Session, job: Job, months: set[str], user: User | None) -> None:
    """A closed month of the job was changed: later than 24 h after closing, the job is marked (purple row)."""
    shut = closes(db)
    late = sorted(m for m in months if m in shut and clock.now() > shut[m] + GRACE)
    if not late:
        return
    job.late_edit_at = clock.now()
    job.late_edit_by = user.id if user else None
    job.late_edit_months = ",".join(sorted(set(filter(None, (job.late_edit_months or "").split(","))) | set(late)))


def _snap_new(db: Session, job: Job, lines: list[JobLine], shut: dict) -> None:
    """A line added to a closed month gets that month's frozen rates (live rates if the month has none)."""
    ctx = None
    for l in lines:
        if l.month in shut and l.snap_fx is None and not l.deleted:
            ctx = ctx or Context(db)
            try:
                snap_line(l, job, ctx)
            except ValueError:
                pass


def sync_assignment(db: Session, job: Job, grp: int, data: dict, strict: bool = True,
                    user: User | None = None) -> list[JobLine]:
    """Rebuild the month lines of one inspector on the job from its dates. Closed months can be changed too:
    such a change is recorded (mark_late), the month keeps its frozen FX and tax rates."""
    lines = [l for l in job.lines if not l.deleted and (l.grp or 1) == grp] if job.id else []
    shut = closes(db)
    ref = max((l.month for l in lines), default=None) or _this_month()
    text = (data.get("dates_text") or "").strip() or None
    dates = parse_dates(text, ref) if text else []
    if strict and not dates:
        raise HTTPException(422, f"Не понял даты «{text}» — например 05,06.11.2026 или 16-20.11.2026" if text else
                            "Укажите даты инспекции: работа в Табеле не может быть без дат")
    unit = data.get("unit") or (lines[-1].unit if lines else "day")
    qty_in = data.get("quantity")
    plan: dict[str, dict] = {}
    if dates:
        by_m: dict[str, list] = {}
        for d in dates:
            by_m.setdefault(d.strftime("%Y-%m"), []).append(d)
        if unit == "day" and len(by_m) > 1:
            plan = {m: {"dates_text": format_dates(ds), "quantity": len(ds)} for m, ds in by_m.items()}
        else:  # a visit, a lump sum: the month of the (last) visit date
            m = max(by_m)
            empty = qty_in in (None, "") or (unit == "day" and float(qty_in or 0) == 0)  # 0 MD with dates = not filled in
            q = (len(dates) if unit == "day" else 0) if empty else qty_in
            plan = {m: {"dates_text": format_dates(dates), "quantity": q}}
    else:
        plan = {ref: {"dates_text": text, "quantity": qty_in or 0}}
    have = {l.month: l for l in lines}
    before = {m: _state(l) for m, l in have.items()}
    last = max(plan) if plan else None
    out = []
    for m, spec in sorted(plan.items()):
        line = have.get(m)
        vals = {k: data[k] for k in COMMON if k in data}
        if line is None:  # a new month of the assignment: same inspector, currencies and rates as its other months
            line = JobLine(job_id=job.id, month=m, grp=grp)
            tpl = lines[-1] if lines else None
            for k in COMMON:
                if k not in vals and k != "notes":
                    vals[k] = getattr(tpl, k) if tpl else None
            vals["currency"] = vals.get("currency") or "USD"
            vals["client_rate"] = vals.get("client_rate") or 0
            vals["inspector_rate"] = vals.get("inspector_rate") or 0
            vals["no_subcontractor"] = bool(vals.get("no_subcontractor"))
        vals.update(spec, unit=unit)
        for k in LAST_ONLY:
            if k in data:
                vals[k] = data[k] if m == last else (None if k == "rko_override_inr" else 0)
        apply(line, vals, {"snap_fx", "snap_fx_insp", "snap_gst", "snap_tds", "snap_admin", "snap_indian", "snap_rko_inr"})
        if line.inspector_currency == line.currency:
            line.inspector_currency = None
        _line_check(line, strict)
        if line.id is None:
            db.add(line)
        out.append(line)
    for m, l in have.items():
        if m not in plan:
            if l.sales_invoice_id:
                raise HTTPException(400, f"Строка за {m} уже в инвойсе клиенту — даты из этого месяца убрать нельзя")
            l.deleted = True
    changed = {m for m in set(plan) | set(have) if m in shut and
               (m not in have or before[m] != _state(have[m]))}
    _snap_new(db, job, out, shut)
    mark_late(db, job, changed, user)
    db.flush()
    db.refresh(job)
    return out


def fill_from_dates(db: Session) -> int:
    """Open-month day lines that do not match their dates: 0 MD with dates (dates typed in words before the parser
    understood them, or booked ahead), or dates of other months in the line (imported «30.11, 07.12, 15.12»).
    The assignment is rebuilt from its dates: each month gets its own days. Runs at start-up; touches nothing else."""
    closed = {m.month for m in db.scalars(select(MonthClose))}
    n = 0
    for l in list(db.scalars(select(JobLine).where(JobLine.deleted.is_(False), JobLine.unit == "day",
                                              JobLine.dates_text.is_not(None)))):
        ds = parse_dates(l.dates_text, l.month)
        if l.month in closed or not ds or any(d.strftime("%Y-%m") in closed for d in ds):
            continue
        other = any(d.strftime("%Y-%m") != l.month for d in ds)
        if not (float(l.quantity or 0) == 0 or (other and float(l.quantity) == len(ds))):
            continue
        group = [x for x in l.job.lines if not x.deleted and (x.grp or 1) == (l.grp or 1)]
        if len(group) == 1:  # a single-month assignment: rebuild it from its dates (may move to the right month)
            try:
                with db.begin_nested():
                    sync_assignment(db, l.job, l.grp or 1, {"dates_text": l.dates_text, "quantity": None}, strict=False)
                n += 1
            except Exception:  # e.g. the dates fall into a closed month: leave the line for a manager
                continue
    if n:
        db.commit()
    return n


def assignments(job: Job, db: Session, ctx: Context) -> list[dict]:
    groups: dict[int, list[JobLine]] = {}
    for l in job.lines:
        if not l.deleted:
            groups.setdefault(l.grp or 1, []).append(l)
    insp = {i.id: i.name for i in db.scalars(select(Inspector).where(Inspector.id.in_({l.inspector_id for l in job.lines if l.inspector_id})))}
    out = []
    for g, ls in sorted(groups.items()):
        ls.sort(key=lambda l: l.month)
        last = ls[-1]
        all_dates = sorted({d for l in ls for d in parse_dates(l.dates_text, l.month)})
        unparsed = [l.dates_text for l in ls if l.dates_text and not parse_dates(l.dates_text, l.month)]
        calc = [compute_line(l, job, ctx) for l in ls]
        icur = last.inspector_currency or last.currency
        out.append({
            "grp": g, "inspector_id": last.inspector_id, "inspector_name": insp.get(last.inspector_id),
            "dates_text": "; ".join([format_dates(all_dates)] * bool(all_dates) + unparsed) or None,
            "dates": [d.isoformat() for d in all_dates],
            "quantity": float(sum(Decimal(l.quantity or 0) for l in ls)), "unit": last.unit,
            "currency": last.currency, "client_rate": float(last.client_rate or 0),
            "inspector_currency": icur, "inspector_rate": float(last.inspector_rate or 0),
            "overtime_client": float(sum(Decimal(l.overtime_client or 0) for l in ls)),
            "overtime_inspector": float(sum(Decimal(l.overtime_inspector or 0) for l in ls)),
            "no_subcontractor": last.no_subcontractor, "payment_method_id": last.payment_method_id,
            "rko_override_inr": float(last.rko_override_inr) if last.rko_override_inr is not None else None,
            "notes": last.notes,
            "months": [l.month for l in ls], "closed_months": [l.month for l in ls if l.month in ctx.closed],
            "invoiced": any(l.sales_invoice_id for l in ls),
            "amount_client": round(sum(c["amount_currency"] for c in calc), 2),
            "amount_inspector": round(sum(c["cost_currency"] for c in calc), 2),
            "line_ids": [l.id for l in ls],
        })
    return out


@r.put("/jobs/{jid}/assignments/{grp}")
def put_assignment(jid: int, grp: int, data: dict, db: Session = Depends(get_db), user: User = Depends(need("write"))):
    job = db.get(Job, jid)
    if not job or job.deleted:
        raise HTTPException(404, "Работа не найдена")
    sync_assignment(db, job, grp, data, user=user)
    _commit(db)
    files.ensure_job_folder(db, job)
    return job_dict(job, db, Context(db), with_lines=True)


@r.post("/jobs/{jid}/assignments")
def add_assignment(jid: int, data: dict, db: Session = Depends(get_db), user: User = Depends(need("write"))):
    job = db.get(Job, jid)
    if not job or job.deleted:
        raise HTTPException(404, "Работа не найдена")
    grp = max((l.grp or 1 for l in job.lines if not l.deleted), default=0) + 1
    sync_assignment(db, job, grp, data, user=user)
    _commit(db)
    files.ensure_job_folder(db, job)
    return job_dict(job, db, Context(db), with_lines=True)


@r.delete("/jobs/{jid}/assignments/{grp}")
def delete_assignment(jid: int, grp: int, db: Session = Depends(get_db), user: User = Depends(need("delete_work"))):
    job = db.get(Job, jid)
    if not job:
        raise HTTPException(404, "Работа не найдена")
    mine = [l for l in job.lines if not l.deleted and (l.grp or 1) == grp]
    if len({l.grp or 1 for l in job.lines if not l.deleted}) <= 1:
        raise HTTPException(400, "Это единственный инспектор работы: работа в Табеле не может быть без дат")
    if any(l.sales_invoice_id for l in mine):
        raise HTTPException(400, "Строки уже в инвойсе клиенту — удалить нельзя")
    for l in mine:
        l.deleted = True
    mark_late(db, job, {l.month for l in mine}, user)
    _commit(db)
    files.ensure_job_folder(db, job)
    return job_dict(job, db, Context(db), with_lines=True)


# ---------------------------------------------------------------- job documents on OneDrive
def _job_with_folder(jid: int, db: Session) -> Job:
    if not sharepoint.enabled():
        raise HTTPException(400, "Хранилище файлов не подключено (нет настроек Microsoft 365 на сервере)")
    job = db.get(Job, jid)
    if not job or job.deleted:
        raise HTTPException(404, "Работа не найдена")
    if not job.sp_folder_id:
        files.ensure_job_folder(db, job)
    if not job.sp_folder_id:
        raise HTTPException(502, job.sp_error or "Папка работы не создана")
    return job


@r.post("/jobs/{jid}/folder")
def job_folder(jid: int, db: Session = Depends(get_db), _=Depends(need("write"))):
    """Create, find or rename the job folder now (the «Повторить» button)."""
    job = db.get(Job, jid)
    if not job or job.deleted:
        raise HTTPException(404, "Работа не найдена")
    if not sharepoint.enabled():
        raise HTTPException(400, "Хранилище файлов не подключено")
    files.ensure_job_folder(db, job)
    if job.sp_error:
        raise HTTPException(502, job.sp_error)
    return {"url": job.sp_folder_url}


@r.get("/jobs/{jid}/files")
def job_files(jid: int, db: Session = Depends(get_db), _=Depends(need("read"))):
    job = _job_with_folder(jid, db)
    try:
        return {"url": job.sp_folder_url, "folders": files.job_files(job)}
    except sharepoint.GraphError as e:
        raise HTTPException(502, f"OneDrive: {e}")


@r.post("/jobs/{jid}/files")
async def upload_job_file(jid: int, folder: str = Form(...), file: UploadFile = File(...),
                          db: Session = Depends(get_db), _=Depends(need("write"))):
    job = _job_with_folder(jid, db)
    content = await file.read()
    if len(content) > 250 * 1024 * 1024:
        raise HTTPException(422, "Файл больше 250 MB")
    name = file.filename or "file"
    m = re.fullmatch(r"(?i)(image|img_\d+|photo|video|capturedimage)(\.\w{1,5})", name)
    if m:  # a photo taken on the phone: «26.29-43 2026-11-22 14.05.31.jpg» instead of «image.jpg»
        name = f"{job.job_number} {clock.now():%Y-%m-%d %H.%M.%S}{m[2].lower()}"
    try:
        item = files.upload_to_job(job, folder, name, content, file.content_type)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except sharepoint.GraphError as e:
        raise HTTPException(502, f"OneDrive: {e}")
    return {"name": item.get("name"), "url": item.get("webUrl")}


@r.get("/jobs/{jid}/files/{item_id}/download")
def download_job_file(jid: int, item_id: str, db: Session = Depends(get_db), _=Depends(need("read"))):
    job = _job_with_folder(jid, db)
    try:
        return RedirectResponse(files.download_url(job, item_id), status_code=302)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except sharepoint.GraphError as e:
        raise HTTPException(502, f"OneDrive: {e}")


# ---------------------------------------------------------------- inspectors already booked
@r.post("/inspectors/busy")
def inspectors_busy(data: dict, db: Session = Depends(get_db), _=Depends(need("read"))):
    """For each inspector: the days of `dates_text` on which they already work on another job.
    {"inspector_ids": [..], "dates_text": "24-26.11.2026", "exclude_job_id": 5} → {"12": [{date, job_id, job_number}]}"""
    ids = [int(i) for i in (data.get("inspector_ids") or []) if i]
    want = set(parse_dates(data.get("dates_text"), _this_month())) if data.get("dates_text") else set()
    if not ids or not want:
        return {}
    skip = data.get("exclude_job_id")
    lo, hi = min(want), max(want)
    months, cur = set(), lo.replace(day=1)
    while cur <= hi:
        months.add(cur.strftime("%Y-%m"))
        cur = (cur + dt.timedelta(days=32)).replace(day=1)
    out: dict[str, list] = {}
    q = select(JobLine).join(Job).where(JobLine.deleted.is_(False), Job.deleted.is_(False), JobLine.inspector_id.in_(ids),
                                        JobLine.month.in_(months))
    for l in db.scalars(q):
        if skip and l.job_id == int(skip):
            continue
        for d in sorted(want & set(parse_dates(l.dates_text, l.month))):
            out.setdefault(str(l.inspector_id), []).append({"date": d.isoformat(), "job_id": l.job_id, "job_number": l.job.job_number})
    for v in out.values():
        v.sort(key=lambda x: (x["date"], x["job_number"]))
    return out


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
