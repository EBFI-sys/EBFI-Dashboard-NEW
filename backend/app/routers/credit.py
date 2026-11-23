"""Credit notes (CN-2627-NNN): owner and accountant only. A credit note cancels a client invoice completely: it will
not be paid, so its TDS entry goes; the invoice number stays used. Its jobs can be freed to be invoiced again under
a new number (e.g. to another payer, as with SPEX HK → TÜV Austria). Credit note numbers are never reused."""
import re
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock, files, invoice_doc, sharepoint
from .. import sharepoint as sp
from ..calc import get_setting
from ..db import get_db
from ..models import Client, CreditNote, JobLine, SalesInvoice, Setting, TdsEntry
from ..security import need
from .crud import _commit, make_crud, to_dict

r = APIRouter()
CN_RE = re.compile(r"^CN-(\d{4})-(\d+)$")


def _fy(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def next_cn_number(db: Session, d: date | None = None) -> str:
    last = str(get_setting(db, "credit_note_last") or "").strip()
    used = {int(m[2]) for (n,) in db.execute(select(CreditNote.number)) if (m := CN_RE.match(n or ""))}
    seq = max([int(last) if last.isdigit() else 0, *used]) + 1
    return f"CN-{_fy(d or clock.today())}-{seq:03d}"


def _ser(o: CreditNote, db: Session) -> dict:
    d = to_dict(o)
    inv = db.get(SalesInvoice, o.sales_invoice_id)
    c = db.get(Client, o.client_id) if o.client_id else None
    d["invoice_number"] = inv.number if inv else None
    d["client_name"] = c.name if c else None
    d["jobs"] = list(dict.fromkeys(l.job.job_number for l in db.scalars(select(JobLine).where(JobLine.id.in_(o.line_ids or [])))))
    return d


def _save(o: CreditNote, data: dict, db: Session, user, created: bool):
    inv = db.get(SalesInvoice, o.sales_invoice_id) if o.sales_invoice_id else None
    if not inv or inv.deleted:
        raise HTTPException(422, "Выберите инвойс, против которого выставляется кредит-нота")
    if created:
        other = db.scalar(select(CreditNote).where(CreditNote.sales_invoice_id == inv.id, CreditNote.deleted.is_(False)))
        if other:
            raise HTTPException(409, f"Против {inv.number} уже есть кредит-нота {other.number}")
        o.number = (o.number or "").strip() or next_cn_number(db, o.date)
        if not CN_RE.match(o.number):
            raise HTTPException(422, "Номер кредит-ноты: CN-2627-NNN")
        n = int(CN_RE.match(o.number)[2])
        used = {int(m[2]) for (x,) in db.execute(select(CreditNote.number)) if (m := CN_RE.match(x or ""))}  # deleted ones too
        if n in used:
            raise HTTPException(409, f"Номер {o.number} уже использован — номера кредит-нот не повторяются (следующий {next_cn_number(db, o.date)})")
        o.date = o.date or clock.today()
        o.client_id, o.currency = inv.client_id, inv.currency
        o.amount = o.amount if o.amount is not None else inv.amount
        o.gst_inr = Decimal(inv.cgst or 0) + Decimal(inv.sgst or 0) + Decimal(inv.igst or 0)
        o.line_ids = [l.id for l in db.scalars(select(JobLine).where(JobLine.sales_invoice_id == inv.id))]
        m = CN_RE.match(o.number)
        row = db.get(Setting, "credit_note_last") or Setting(key="credit_note_last", value="0")
        if not row.value.isdigit() or int(m[2]) > int(row.value):
            row.value = str(int(m[2]))
        db.add(row)
    if data.get("release") and not o.released:  # free the jobs for a new invoice (another payer, corrected invoice)
        for l in db.scalars(select(JobLine).where(JobLine.sales_invoice_id == inv.id)):
            l.sales_invoice_id = None
        o.released = True
    if created:
        db.flush()
        for t in db.scalars(select(TdsEntry).where(TdsEntry.sales_invoice_id == inv.id)):  # the invoice will not be paid
            db.delete(t)


def _before_delete(o: CreditNote, db: Session):
    """A credit note entered by mistake: the invoice is valid again and gets its TDS entry back; the CN number stays used."""
    if o.released:
        raise HTTPException(400, "Работы этой кредит-ноты уже освобождены для нового инвойса — удалить её нельзя")
    from .money import _sales_after
    inv = db.get(SalesInvoice, o.sales_invoice_id)
    o.deleted = True
    db.flush()
    if inv:
        _sales_after(inv, db)


def _after(o: CreditNote, db: Session):
    """Keeps the invoice's TDS entry in line (also when a deleted credit note is brought back with «Отменить»)."""
    from .money import _sales_after
    inv = db.get(SalesInvoice, o.sales_invoice_id)
    if inv:
        _sales_after(inv, db)


@r.get("/credit-notes/next-number")
def cn_next(on: str | None = None, db: Session = Depends(get_db), _=Depends(need("credit_notes"))):
    return {"number": next_cn_number(db, date.fromisoformat(on) if on else None)}


def _cn(db: Session, cid: int) -> tuple[CreditNote, SalesInvoice]:
    cn = db.get(CreditNote, cid)
    if not cn or cn.deleted:
        raise HTTPException(404, "Кредит-нота не найдена")
    return cn, db.get(SalesInvoice, cn.sales_invoice_id)


def _build(db: Session, cn: CreditNote, inv: SalesInvoice) -> bytes:
    try:
        docx, _, _ = invoice_doc.build_docx(db, inv, line_ids=cn.line_ids, credit=(cn.number, cn.date or clock.today()))
    except invoice_doc.InvoiceError as e:
        raise HTTPException(422, str(e))
    return docx


@r.post("/credit-notes/{cid}/document")
def cn_document(cid: int, db: Session = Depends(get_db), _=Depends(need("credit_notes"))):
    """Word + PDF into Outgoing Invoice Register / YYYY-MM / <client> / Credit Notes."""
    cn, inv = _cn(db, cid)
    docx = _build(db, cn, inv)
    warnings = []
    try:
        pdf = invoice_doc.to_pdf(docx, cn.number)
    except Exception as e:  # noqa: BLE001
        pdf, _ = None, warnings.append(f"PDF не сделан: {e}")
    if sharepoint.enabled():
        try:
            g = sp.graph()
            client = db.get(Client, cn.client_id)
            folder = g.path_folder(sp.OUTGOING, (cn.date or clock.today()).strftime("%Y-%m"), client.name if client else "Без клиента", "Credit Notes")
            d = g.upload(folder["id"], f"{cn.number}.docx", docx, None, conflict="replace")
            cn.doc_url = d.get("webUrl")
            if pdf:
                cn.pdf_url = g.upload(folder["id"], f"{cn.number}.pdf", pdf, "application/pdf", conflict="replace").get("webUrl")
        except sharepoint.GraphError as e:
            warnings.append(f"OneDrive: {e}")
    _commit(db)
    return {"doc_url": cn.doc_url, "pdf_url": cn.pdf_url, "warnings": warnings, "pdf": bool(pdf)}


@r.get("/credit-notes/{cid}/document/{kind}")
def cn_download(cid: int, kind: str, db: Session = Depends(get_db), _=Depends(need("credit_notes"))):
    cn, inv = _cn(db, cid)
    docx = _build(db, cn, inv)
    if kind == "pdf":
        body = invoice_doc.to_pdf(docx, cn.number)
        if body is None:
            raise HTTPException(404, "PDF недоступен: на сервере нет LibreOffice")
        return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{cn.number}.pdf"'})
    return Response(docx, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{cn.number}.docx"'})


r.include_router(make_crud(CreditNote, "/credit-notes", order_by=[CreditNote.date.desc().nulls_last(), CreditNote.id.desc()],
                           search=["number", "reason"], serialize=_ser, before_save=_save, before_delete=_before_delete,
                           after_save=_after,
                           readonly={"client_id", "currency", "gst_inr", "line_ids", "released", "doc_url", "pdf_url"},
                           read_right="credit_notes", write_right="credit_notes", delete_right="credit_notes"))
