import datetime as dt
import re

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..calc import Context, compute_line
from ..dates import format_dates, parse_dates
from ..db import get_db
from ..directory import remember_country, remember_vendor
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


r.include_router(make_crud(Request, "/requests", order_by=[Request.received_date.desc().nulls_last(), Request.id.desc()],
                           search=["factory", "country", "final_client", "notes"], before_save=_req_save))


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
    if not req.client_id:
        raise HTTPException(422, "В заявке не указан клиент")
    number = (data.get("job_number") or "").strip() or next_job_number(db, req.client_id)
    if not JOB_RE.match(number):
        raise HTTPException(422, "Job number должен быть в формате ГГ.КК-ННН, например 26.19-478")
    if db.scalar(select(Job).where(Job.job_number == number)):
        raise HTTPException(409, f"Работа {number} уже есть в Табеле")
    notes = "\n".join(x for x in [f"Конечный клиент: {req.final_client}" if req.final_client else "", req.notes or ""] if x) or None
    job = Job(job_number=number, client_id=req.client_id, country=req.country, vendor=req.factory,
              owner_id=req.owner_id or user.id, status="В работе", notes=notes)
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
    req.status = "Принято в работу"
    if len(inspectors) == 1:
        req.inspector_id = inspectors[0]
    _commit(db)
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
    code, yy = client.job_code.zfill(2), f"{dt.date.today():%y}"
    seq, width = last_seq(db, yy, code)
    return f"{yy}.{code}-{seq + 1:0{width}d}"


@r.get("/jobs/next-number")
def job_next_number(client_id: int, db: Session = Depends(get_db), _=Depends(need("read"))):
    return {"job_number": next_job_number(db, client_id)}


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
    remember_country(db, job.country)
    remember_vendor(db, job.vendor, job.country)
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
    remember_country(db, job.country)
    remember_vendor(db, job.vendor, job.country)
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


# ---------------------------------------------------------------- assignments: the job as one row
# A job is one row of the Табель. Behind it the P&L keeps one line per month (a job can run from October into
# November) and per inspector (rarely two inspectors work on one job). Managers edit the assignment as a whole;
# the month lines are rebuilt from its dates. Lines of closed months are never touched.
COMMON = ("inspector_id", "unit", "currency", "client_rate", "inspector_rate", "inspector_currency", "no_subcontractor",
          "payment_method_id", "notes")
LAST_ONLY = ("overtime_client", "overtime_inspector", "rko_override_inr")


def _this_month() -> str:
    return dt.date.today().strftime("%Y-%m")


def sync_assignment(db: Session, job: Job, grp: int, data: dict, strict: bool = True) -> list[JobLine]:
    lines = [l for l in job.lines if not l.deleted and (l.grp or 1) == grp] if job.id else []
    closed = {m.month for m in db.scalars(select(MonthClose))}
    ref = max((l.month for l in lines), default=None) or _this_month()
    text = data.get("dates_text")
    dates = parse_dates(text, ref) if text else []
    unit = data.get("unit") or (lines[-1].unit if lines else "day")
    qty_in = data.get("quantity")
    plan: dict[str, dict] = {}
    if dates:
        by_m: dict[str, list] = {}
        for d in dates:
            by_m.setdefault(d.strftime("%Y-%m"), []).append(d)
        if unit == "day" and len(by_m) > 1:
            plan = {m: {"dates_text": format_dates(ds), "quantity": len(ds)} for m, ds in by_m.items()}
        else:
            m = max(by_m)
            empty = qty_in in (None, "") or (unit == "day" and float(qty_in or 0) == 0)  # 0 MD with dates = not filled in
            q = (len(dates) if unit == "day" else 0) if empty else qty_in
            plan = {m: {"dates_text": format_dates(dates), "quantity": q}}
    else:
        plan = {ref: {"dates_text": text or None, "quantity": qty_in or 0}}
    have = {l.month: l for l in lines}
    for m, l in have.items():
        if m in closed:
            same = m in plan and (plan[m]["dates_text"] or "") == (l.dates_text or "") and \
                float(plan[m]["quantity"] or 0) == float(l.quantity or 0)
            if strict and not same and (m in plan or l.quantity):
                raise HTTPException(400, f"Месяц {m} закрыт: даты и количество за него менять нельзя")
            plan.pop(m, None)
    for m in plan:
        if m in closed:
            raise HTTPException(400, f"Месяц {m} закрыт: добавить в него даты нельзя")
    last = max(plan) if plan else None
    out = []
    for m, spec in sorted(plan.items()):
        line = have.get(m) or JobLine(job_id=job.id, month=m, grp=grp)
        vals = {k: data[k] for k in COMMON if k in data}
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
        if m not in closed and m not in plan:
            if l.sales_invoice_id:
                raise HTTPException(400, f"Строка за {m} уже в инвойсе клиенту — даты из этого месяца убрать нельзя")
            l.deleted = True
    db.flush()
    db.refresh(job)
    return out


def fill_from_dates(db: Session) -> int:
    """Open-month day lines with dates but 0 MD (dates typed in words before the parser understood them):
    count the days and store the dates in the standard form. Runs at start-up; touches nothing else."""
    closed = {m.month for m in db.scalars(select(MonthClose))}
    n = 0
    for l in list(db.scalars(select(JobLine).where(JobLine.deleted.is_(False), JobLine.unit == "day", JobLine.quantity == 0,
                                              JobLine.dates_text.is_not(None)))):
        if l.month in closed or not parse_dates(l.dates_text, l.month):
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
def put_assignment(jid: int, grp: int, data: dict, db: Session = Depends(get_db), _=Depends(need("write"))):
    job = db.get(Job, jid)
    if not job or job.deleted:
        raise HTTPException(404, "Работа не найдена")
    sync_assignment(db, job, grp, data)
    _commit(db)
    return job_dict(job, db, Context(db), with_lines=True)


@r.post("/jobs/{jid}/assignments")
def add_assignment(jid: int, data: dict, db: Session = Depends(get_db), _=Depends(need("write"))):
    job = db.get(Job, jid)
    if not job or job.deleted:
        raise HTTPException(404, "Работа не найдена")
    grp = max((l.grp or 1 for l in job.lines if not l.deleted), default=0) + 1
    sync_assignment(db, job, grp, data)
    _commit(db)
    return job_dict(job, db, Context(db), with_lines=True)


@r.delete("/jobs/{jid}/assignments/{grp}")
def delete_assignment(jid: int, grp: int, db: Session = Depends(get_db), _=Depends(need("delete"))):
    job = db.get(Job, jid)
    if not job:
        raise HTTPException(404, "Работа не найдена")
    closed = {m.month for m in db.scalars(select(MonthClose))}
    for l in job.lines:
        if not l.deleted and (l.grp or 1) == grp:
            if l.month in closed or l.sales_invoice_id:
                raise HTTPException(400, "Есть закрытый месяц или инвойс клиенту — удалить нельзя")
            l.deleted = True
    _commit(db)
    return job_dict(job, db, Context(db), with_lines=True)


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
