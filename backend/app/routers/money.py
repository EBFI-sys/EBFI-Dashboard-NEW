import os
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..calc import Context, get_setting
from ..config import settings
from ..db import get_db
from ..models import Client, Inspector, InspectorInvoice, Job, JobLine, PaymentMethod, SalesInvoice, TdsEntry, User
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
            entry = TdsEntry(sales_invoice_id=o.id, amount_inr=amt, quarter=fy_quarter(o.date or date.today()))
            db.add(entry)
        else:
            entry.amount_inr = amt
            entry.quarter = fy_quarter(o.date or date.today())
    elif entry and entry.status == "Ожидается":
        db.delete(entry)


def _sales_ser(o: SalesInvoice, db: Session):
    d = to_dict(o)
    c = db.get(Client, o.client_id)
    d["client_name"] = c.name if c else None
    d["gst_total"] = float((o.cgst or 0) + (o.sgst or 0) + (o.igst or 0))
    d["outstanding"] = float(Decimal(o.amount) - Decimal(o.received_amount or 0)) if o.status != "Paid" else 0.0
    d["line_ids"] = [l.id for l in db.scalars(select(JobLine).where(JobLine.sales_invoice_id == o.id))]
    return d


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
    inv = SalesInvoice(number=data.get("number"), date=date.fromisoformat(data["date"]) if data.get("date") else date.today(),
                       client_id=clients.pop(), currency=currencies.pop(), amount=amount, status="Not Verified")
    if not inv.number:
        raise HTTPException(422, "Укажите номер инвойса")
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
    d["has_file"] = bool(o.file_path)
    # expected amount from the job lines of this inspector, to catch mismatches
    expected = Decimal(0)
    for j in o.jobs:
        for l in j.lines:
            if l.inspector_id == o.inspector_id and not l.deleted and l.currency == o.currency:
                expected += Decimal(l.quantity or 0) * Decimal(l.inspector_rate or 0) + Decimal(l.overtime_inspector or 0)
    d["expected_amount"] = float(expected) if o.jobs else None
    return d


def _ii_save(o: InspectorInvoice, data: dict, db: Session, user, created):
    if "job_ids" in data:
        o.jobs = [db.get(Job, int(j)) for j in data["job_ids"] if db.get(Job, int(j))]
    if o.paid and not o.paid_date:
        o.paid_date = date.today()
    if not o.inspector_id or o.amount is None:
        raise HTTPException(422, "Нужны инспектор и сумма")


r.include_router(make_crud(InspectorInvoice, "/inspector-invoices",
                           order_by=[InspectorInvoice.invoice_date.desc().nulls_last(), InspectorInvoice.id.desc()],
                           search=["number", "comment"], serialize=_ii_ser, before_save=_ii_save, readonly={"file_path"}))


@r.post("/inspector-invoices/{iid}/file")
async def upload_file(iid: int, file: UploadFile = File(...), db: Session = Depends(get_db), _=Depends(need("write"))):
    inv = db.get(InspectorInvoice, iid)
    if not inv:
        raise HTTPException(404, "Счёт не найден")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg"):
        raise HTTPException(422, "Загрузите PDF или изображение")
    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(422, "Файл больше 15 MB")
    os.makedirs(settings.upload_dir, exist_ok=True)
    name = f"inv-{iid}-{uuid.uuid4().hex[:8]}{ext}"
    with open(os.path.join(settings.upload_dir, name), "wb") as f:
        f.write(content)
    inv.file_path = name
    _commit(db)
    return {"ok": True}


@r.get("/inspector-invoices/{iid}/file")
def download_file(iid: int, db: Session = Depends(get_db), _=Depends(need("read"))):
    inv = db.get(InspectorInvoice, iid)
    if not inv or not inv.file_path:
        raise HTTPException(404, "Файл не загружен")
    return FileResponse(os.path.join(settings.upload_dir, inv.file_path))
