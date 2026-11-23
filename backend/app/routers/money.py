import os
import re
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import invoice_read, clock
from .. import files, sharepoint
from ..calc import Context, get_setting
from ..config import settings
from ..db import get_db
from ..models import Setting, Client, Inspector, InspectorInvoice, Job, JobLine, PaymentMethod, SalesInvoice, TdsEntry, User
from ..security import need
from .crud import _commit, apply, make_crud, to_dict

r = APIRouter()
SALES_STATUSES = ["Not Verified", "Отправлен клиенту", "Paid"]
TDS_STATUSES = ["Ожидается", "В Form 26AS", "Зачтён"]


def fy_quarter(d: date) -> str:
    """Indian financial year April–March: 15 Nov 2026 → FY27-Q3."""
    fy = d.year + 1 if d.month >= 4 else d.year
    q = ((d.month - 4) % 12) // 3 + 1
    return f"FY{str(fy)[-2:]}-Q{q}"


# ---------------------------------------------------------------- sales invoices
def _sales_save(o: SalesInvoice, data: dict, db: Session, user, created):
    if created and not (o.number or "").strip():
        o.number = next_invoice_number(db, o.date)[0]
        if not o.number:
            raise HTTPException(422, "Укажите номер инвойса (автонумерация ещё не включена)")
    if created:
        _bump_counter(db, o.number)
    if o.status not in SALES_STATUSES:
        raise HTTPException(422, f"Статус: {', '.join(SALES_STATUSES)}")
    client = db.get(Client, o.client_id)
    if not client:
        raise HTTPException(422, "Не указан клиент")
    if not o.fx_rate:
        if o.currency == "INR":
            o.fx_rate = Decimal(1)
        elif o.date:
            fx = Context(db).fx(o.date.strftime("%Y-%m"), o.currency)
            o.fx_rate = fx.rate
    manual_gst = any(k in data for k in ("cgst", "sgst", "igst"))
    if client.is_indian and o.fx_rate:
        o.taxable_inr = (Decimal(o.amount) * Decimal(o.fx_rate)).quantize(Decimal("0.01"))
        if not manual_gst:
            gst = Decimal(get_setting(db, "gst_rate"))
            same_state = (client.state or "").strip().lower() == get_setting(db, "company_state").strip().lower()
            if same_state:
                o.cgst = o.sgst = (o.taxable_inr * gst / 2).quantize(Decimal("0.01"))
                o.igst = Decimal(0)
            else:
                o.cgst = o.sgst = Decimal(0)
                o.igst = (o.taxable_inr * gst).quantize(Decimal("0.01"))
    elif not client.is_indian:
        o.taxable_inr = None
        o.cgst = o.sgst = o.igst = Decimal(0)


def _sales_after(o: SalesInvoice, db: Session):
    """Indian clients withhold TDS: keep one TDS register entry per invoice."""
    client = db.get(Client, o.client_id)
    entry = db.scalar(select(TdsEntry).where(TdsEntry.sales_invoice_id == o.id))
    if client and client.is_indian and o.taxable_inr and not o.deleted:
        amt = (Decimal(o.taxable_inr) * Decimal(get_setting(db, "tds_rate"))).quantize(Decimal("0.01"))
        if not entry:
            entry = TdsEntry(sales_invoice_id=o.id, amount_inr=amt, quarter=fy_quarter(o.date or clock.today()))
            db.add(entry)
        else:
            entry.amount_inr = amt
            entry.quarter = fy_quarter(o.date or clock.today())
    elif entry and entry.status == "Ожидается":
        db.delete(entry)


def _sales_ser(o: SalesInvoice, db: Session):
    d = to_dict(o)
    c = db.get(Client, o.client_id)
    d["client_name"] = c.name if c else None
    d["gst_total"] = float((o.cgst or 0) + (o.sgst or 0) + (o.igst or 0))
    # WHT the client keeps when paying (5%), in the invoice currency: it is not credited anywhere, so it is our loss
    d["wht"] = float(Decimal(o.amount) * Decimal(get_setting(db, "wht_rate"))) if c and c.wht else 0.0
    d["outstanding"] = float(Decimal(o.amount) - Decimal(o.received_amount or 0)) if o.status != "Paid" else 0.0
    d["file_url"] = o.sp_file_url
    d["line_ids"] = [l.id for l in db.scalars(select(JobLine).where(JobLine.sales_invoice_id == o.id))]
    return d




# ---------------------------------------------------------------- invoice numbers: EBFI-<FY>-NNN, one queue for all clients
INV_RE = re.compile(r"^EBFI-(\d{4})-(\d+)$")


def fy_code(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def next_invoice_number(db: Session, d: date | None = None) -> tuple[str, int] | tuple[None, None]:
    """Next number in the single queue 300, 301, 302… for all clients. Works only after the admin has entered the last
    issued number in «Справочники → Налоги и нумерация»; until then numbers are typed by hand."""
    last = str(get_setting(db, "sales_invoice_last")).strip()
    if not last.isdigit():
        return None, None
    used = {int(m[2]) for (n,) in db.execute(select(SalesInvoice.number)) if (m := INV_RE.match(n or ""))}
    seq = int(last) + 1
    while seq in used:
        seq += 1
    return f"EBFI-{fy_code(d or clock.today())}-{seq}", seq


def _bump_counter(db: Session, number: str):
    m = INV_RE.match(number or "")
    if not m:
        return
    last = str(get_setting(db, "sales_invoice_last")).strip()
    if last.isdigit() and int(m[2]) > int(last):  # auto-numbering on: move the counter forward
        row = db.get(Setting, "sales_invoice_last") or Setting(key="sales_invoice_last", value="")
        row.value = m[2]
        db.add(row)


@r.get("/sales-invoices/next-number")
def sales_next_number(on: str | None = None, db: Session = Depends(get_db), _=Depends(need("read"))):
    return {"number": next_invoice_number(db, date.fromisoformat(on) if on else None)[0]}


r.include_router(make_crud(SalesInvoice, "/sales-invoices", order_by=[SalesInvoice.date.desc().nulls_last(), SalesInvoice.id.desc()],
                           search=["number", "notes"], serialize=_sales_ser, before_save=_sales_save, after_save=_sales_after))


@r.get("/sales-statuses")
def sales_statuses(_=Depends(need("read"))):
    return SALES_STATUSES


@r.post("/sales-invoices/from-lines")
def invoice_from_lines(data: dict, db: Session = Depends(get_db), user: User = Depends(need("write"))):
    """Create a client invoice from selected job lines (same client and currency)."""
    ids = data.get("line_ids") or []
    lines = [db.get(JobLine, i) for i in ids]
    if not lines or any(l is None or l.deleted for l in lines):
        raise HTTPException(422, "Выберите строки работ")
    if any(l.sales_invoice_id for l in lines):
        raise HTTPException(400, "Часть строк уже включена в инвойс")
    clients = {l.job.client_id for l in lines}
    currencies = {l.currency for l in lines}
    if len(clients) != 1 or len(currencies) != 1:
        raise HTTPException(422, "Все строки должны быть одного клиента и одной валюты")
    amount = sum(Decimal(l.quantity or 0) * Decimal(l.client_rate or 0) + Decimal(l.overtime_client or 0) for l in lines)
    inv_date = date.fromisoformat(data["date"]) if data.get("date") else clock.today()
    inv = SalesInvoice(number=(data.get("number") or "").strip() or next_invoice_number(db, inv_date)[0], date=inv_date,
                       client_id=clients.pop(), currency=currencies.pop(), amount=amount, status="Not Verified")
    if not inv.number:
        raise HTTPException(422, "Укажите номер инвойса (автонумерация ещё не включена)")
    if db.scalar(select(SalesInvoice).where(SalesInvoice.number == inv.number)):
        raise HTTPException(409, f"Инвойс {inv.number} уже есть")
    _bump_counter(db, inv.number)
    _sales_save(inv, {}, db, user, True)
    db.add(inv)
    db.flush()
    for l in lines:
        l.sales_invoice_id = inv.id
    _sales_after(inv, db)
    _commit(db)
    return _sales_ser(inv, db)


# ---------------------------------------------------------------- TDS register
def _tds_ser(o: TdsEntry, db: Session):
    d = to_dict(o)
    inv = db.get(SalesInvoice, o.sales_invoice_id)
    if inv:
        c = db.get(Client, inv.client_id)
        d.update(invoice_number=inv.number, invoice_date=inv.date.isoformat() if inv.date else None,
                 client_name=c.name if c else None, taxable_inr=float(inv.taxable_inr or 0), invoice_status=inv.status)
    return d


def _tds_save(o: TdsEntry, data, db, user, created):
    if o.status not in TDS_STATUSES:
        raise HTTPException(422, f"Статус: {', '.join(TDS_STATUSES)}")


r.include_router(make_crud(TdsEntry, "/tds", order_by=TdsEntry.id.desc(), serialize=_tds_ser, before_save=_tds_save,
                           readonly={"sales_invoice_id", "amount_inr"}))


# ---------------------------------------------------------------- inspector invoices
def _ii_ser(o: InspectorInvoice, db: Session):
    d = to_dict(o)
    insp = db.get(Inspector, o.inspector_id)
    d["inspector_name"] = insp.name if insp else None
    pm = db.get(PaymentMethod, o.payment_method_id) if o.payment_method_id else None
    d["payment_method"] = pm.name if pm else None
    d["job_ids"] = [j.id for j in o.jobs]
    d["job_numbers"] = [j.job_number for j in o.jobs]
    d["has_file"] = bool(o.file_path or o.sp_file_url)
    d["file_url"] = o.sp_file_url
    d.update(_check(o))
    return d


def _insp_cost(l: JobLine) -> Decimal:
    if l.no_subcontractor:
        return Decimal(0)
    return Decimal(l.quantity or 0) * Decimal(l.inspector_rate or 0) + Decimal(l.overtime_inspector or 0)


def _check(o: InspectorInvoice) -> dict:
    """Compare the invoice with the Табель: days × inspector rate (+ OT) of this inspector on the linked jobs,
    in the inspector's own currency — the client may be billed in another currency, which is fine."""
    rows = []
    for j in o.jobs:
        for l in sorted(j.lines, key=lambda x: x.month):
            if l.deleted or l.inspector_id != o.inspector_id:
                continue
            rows.append({"job_id": j.id, "job_number": j.job_number, "month": l.month, "dates_text": l.dates_text,
                         "quantity": float(l.quantity or 0), "unit": l.unit, "rate": float(l.inspector_rate or 0),
                         "overtime": float(l.overtime_inspector or 0), "amount": float(_insp_cost(l)),
                         "currency": l.inspector_currency or l.currency})
    if not o.jobs:
        return {"expected_amount": None, "check": {"status": "no_jobs", "rows": []}}
    if not rows:
        return {"expected_amount": None, "check": {"status": "no_lines", "rows": [],
                "message": "В привязанных работах этот инспектор не указан"}}
    by_cur: dict[str, float] = {}
    for r in rows:
        by_cur[r["currency"]] = by_cur.get(r["currency"], 0) + r["amount"]
    expected = by_cur.get(o.currency)
    problems = []
    if expected is None:
        status = "currency"
        problems.append(f"Счёт в {o.currency}, а в Табеле ставка инспектора в {', '.join(by_cur)}")
    else:
        diff = round(float(o.amount) - expected, 2)
        status = "ok" if abs(diff) <= 1 else "amount"
        if status == "amount":
            problems.append(f"Сумма счёта {float(o.amount):,.2f} {o.currency}, по Табелю {expected:,.2f} {o.currency} "
                            f"(разница {diff:+,.2f})")
        if status == "amount":  # explain where the difference comes from
            days = sum(r["quantity"] for r in rows if r["unit"] == "day" and r["currency"] == o.currency)
            if o.days and abs(float(o.days) - days) > 0.01:
                problems.append(f"Дней: в счёте {float(o.days):g}, в Табеле {days:g}")
            rates = {r["rate"] for r in rows if r["currency"] == o.currency}
            if o.rate and rates and float(o.rate) not in rates:
                problems.append(f"Ставка: в счёте {float(o.rate):g}, в Табеле {', '.join(f'{x:g}' for x in sorted(rates))}")
    return {"expected_amount": expected, "check": {"status": status, "rows": rows, "problems": problems,
                                                   "by_currency": by_cur}}


def _ii_save(o: InspectorInvoice, data: dict, db: Session, user, created):
    if "job_ids" in data:
        o.jobs = [db.get(Job, int(j)) for j in data["job_ids"] if db.get(Job, int(j))]
    if o.paid and not o.paid_date:
        o.paid_date = clock.today()
    if not o.inspector_id or o.amount is None:
        raise HTTPException(422, "Нужны инспектор и сумма")


@r.post("/inspector-invoices/read")
async def read_invoice(file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(need("write"))):
    """Fill the new-invoice form from the inspector's PDF or Word file."""
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(422, "Файл больше 25 MB")
    try:
        return invoice_read.read(db, file.filename or "", content)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # noqa: BLE001 - a damaged file
        raise HTTPException(422, f"Не удалось прочитать файл: {e}")


r.include_router(make_crud(InspectorInvoice, "/inspector-invoices",
                           order_by=[InspectorInvoice.invoice_date.desc().nulls_last(), InspectorInvoice.id.desc()],
                           search=["number", "comment"], serialize=_ii_ser, before_save=_ii_save, readonly={"file_path"}))


@r.get("/inspectors/{iid}/work")
def inspector_work(iid: int, invoice_id: int | None = None, db: Session = Depends(get_db), _=Depends(need("read"))):
    """Jobs of this inspector from the Табель, with the amounts due to him; `invoiced` marks jobs already covered
    by another of his invoices."""
    taken: dict[int, str] = {}
    for inv in db.scalars(select(InspectorInvoice).where(InspectorInvoice.inspector_id == iid, InspectorInvoice.deleted.is_(False))):
        if inv.id != invoice_id:
            for j in inv.jobs:
                taken[j.id] = inv.number or f"#{inv.id}"
    jobs: dict[int, dict] = {}
    for l in db.scalars(select(JobLine).where(JobLine.inspector_id == iid, JobLine.deleted.is_(False)).order_by(JobLine.month)):
        j = l.job
        if j.deleted:
            continue
        cur = l.inspector_currency or l.currency
        x = jobs.setdefault(j.id, {"job_id": j.id, "job_number": j.job_number, "client": j.client.name if j.client else None,
                                   "status": j.status, "months": [], "dates": [], "days": 0.0, "amounts": {},
                                   "rates": set(), "invoiced_in": taken.get(j.id)})
        x["months"].append(l.month)
        if l.dates_text:
            x["dates"].append(l.dates_text)
        if l.unit == "day":
            x["days"] += float(l.quantity or 0)
        x["amounts"][cur] = x["amounts"].get(cur, 0) + float(_insp_cost(l))
        x["rates"].add(f"{float(l.inspector_rate or 0):g} {cur}")
    out = []
    for x in jobs.values():
        x["rates"] = sorted(x["rates"])
        x["dates"] = "; ".join(x["dates"])
        out.append(x)
    out.sort(key=lambda x: x["months"][-1], reverse=True)
    out.sort(key=lambda x: x["invoiced_in"] is not None)
    return out


ALLOWED = (".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx", ".xls", ".xlsx")


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED:
        raise HTTPException(422, "Загрузите PDF, Word, Excel или изображение")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(422, "Файл больше 25 MB")
    return content, ext


@r.post("/inspector-invoices/{iid}/file")
async def upload_file(iid: int, file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(need("write"))):
    """The inspector's invoice: to Incoming Invoice Register on OneDrive when it is connected, else kept on the server."""
    inv = db.get(InspectorInvoice, iid)
    if not inv:
        raise HTTPException(404, "Счёт не найден")
    content, ext = await _read_upload(file)
    if sharepoint.enabled():
        try:
            files.upload_incoming(db, inv, file.filename or f"invoice{ext}", content, file.content_type)
        except sharepoint.GraphError as e:
            raise HTTPException(502, f"OneDrive: {e}")
    else:
        os.makedirs(settings.upload_dir, exist_ok=True)
        name = f"inv-{iid}-{uuid.uuid4().hex[:8]}{ext}"
        with open(os.path.join(settings.upload_dir, name), "wb") as f:
            f.write(content)
        inv.file_path = name
    _commit(db)
    return {"ok": True, "url": inv.sp_file_url}


@r.get("/inspector-invoices/{iid}/file")
def download_file(iid: int, db: Session = Depends(get_db), _=Depends(need("read"))):
    inv = db.get(InspectorInvoice, iid)
    if inv and inv.sp_file_url:
        return RedirectResponse(inv.sp_file_url)
    if not inv or not inv.file_path:
        raise HTTPException(404, "Файл не загружен")
    return FileResponse(os.path.join(settings.upload_dir, inv.file_path))


@r.post("/sales-invoices/{iid}/file")
async def upload_sales_file(iid: int, file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(need("write"))):
    """Our invoice to the client: to Outgoing Invoice Register / month / client on OneDrive."""
    inv = db.get(SalesInvoice, iid)
    if not inv:
        raise HTTPException(404, "Инвойс не найден")
    if not sharepoint.enabled():
        raise HTTPException(400, "Хранилище файлов не подключено")
    content, ext = await _read_upload(file)
    try:
        files.upload_outgoing(db, inv, file.filename or f"invoice{ext}", content, file.content_type)
    except sharepoint.GraphError as e:
        raise HTTPException(502, f"OneDrive: {e}")
    _commit(db)
    return {"ok": True, "url": inv.sp_file_url}


@r.get("/files/status")
def files_status(db: Session = Depends(get_db), _=Depends(need("settings"))):
    """Check the OneDrive connection: token, drive and the EBFI folder."""
    if not sharepoint.enabled():
        return {"enabled": False, "message": "Не заданы MS_TENANT_ID / MS_CLIENT_ID / MS_CLIENT_SECRET / MS_SITE_ID в .env"}
    try:
        g = sharepoint.graph()
        root = g.item(settings.ms_root)
        years = [c["name"] for c in g.children(root["id"]) if "folder" in c] if root else []
        return {"enabled": True, "ok": True, "root": root.get("webUrl") if root else None, "folders": years}
    except sharepoint.GraphError as e:
        return {"enabled": True, "ok": False, "message": str(e)}


@r.post("/files/sync-numbers")
def files_sync_numbers(db: Session = Depends(get_db), _=Depends(need("settings"))):
    """Take the job numbers already used on the server into the number queues."""
    if not sharepoint.enabled():
        raise HTTPException(400, "Хранилище файлов не подключено")
    try:
        return {"queues": files.sync_numbers(db)}
    except sharepoint.GraphError as e:
        raise HTTPException(502, f"OneDrive: {e}")
