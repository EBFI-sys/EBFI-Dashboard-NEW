"""Import November 2026 and the open items from the Google Sheets (downloaded as .xlsx).

    docker compose exec api python -m scripts.import_xlsx \
        --pnl /data/import/pnl.xlsx --requests /data/import/requests.xlsx \
        --sales /data/import/sales.xlsx --invoices /data/import/invoices.xlsx --month 2026-11 [--reset]

What is imported:
  * every P&L line of --month, plus earlier lines whose job is still «В работе» / «Пауза»;
  * requests of --month and every still-open request;
  * the whole client invoice register and inspector invoice list;
  * FX rates found in the P&L ($/€ column) for the imported months.
Run it again with --reset to wipe the imported work data and start over (users are kept).
"""
import argparse
import datetime as dt
import re
from collections import Counter, defaultdict
from decimal import Decimal

import openpyxl
from sqlalchemy import delete, select

from app.db import Base, SessionLocal, engine
from app.models import (AuditLog, Client, FxRate, Inspector, InspectorInvoice, Job, JobLine, PaymentMethod, Request,
                        SalesInvoice, TdsEntry, User, inspector_invoice_jobs)
from app.routers.money import _sales_after

MONTHS = {"Январь": 1, "Февраль": 2, "Март": 3, "Апрель": 4, "Май": 5, "Июнь": 6, "Июль": 7, "Август": 8,
          "Сентябрь": 9, "Октябрь": 10, "Ноябрь": 11, "Декабрь": 12}
ALIAS = {"Клиент": "client", "Client Name": "client", "№ бизнеса": "job", "Job number": "job", "Страна": "country",
         "Country": "country", "Инспектор": "inspector", "Inspector Name": "inspector", "Чья": "owner", "i": "owner",
         "Дата": "dates", "Date": "dates", "Total": "qty", "Статус": "status", "$1 €2": "cur",
         "Нам платят чел/день": "rate", "Manday Rate": "rate", "Мы платим чел/день": "cost", "Мы платим": "cost",
         "overtime Нам платим": "ot_client", "overtime Мы платим": "ot_insp", "Сумма Инвойса": "invoice",
         "Invoice Amount": "invoice", "Приход на р/с с учетом TDS и GST": "income", "$/€": "fx",
         "Client Project Coordinator": "contact", "Vendor Name": "vendor",
         "Client Job Number / Client Name": "client_job"}
CLIENT_FIX = {"COPERION": "Coperion", "IRCLass": "IRClass", "TUVTPS": "TUV TPS", "MASMarine": "MAS Marine", "APPLUS": "Applus"}
COUNTRY_FIX = {"China .": "China", "Gernany": "Germany", "Afrika": "Africa", "Marocco": "Morocco"}
OWNER = {"Л": "LM", "М": "MB", "С": "SV", "C": "SV", "Лю": "LR", "Д": "Д", "А": "А", "A": "А", "Т": "Т"}
REQ_STATUS = {"В процесссе": "В процессе", "В процессе": "В процессе", "Выполнено": "Выполнено", "Отмена": "Отмена",
              "Принято в работу": "Принято в работу", "Перенос": "Перенос"}


def norm(x) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()


def num(x) -> Decimal:
    if x in (None, ""):
        return Decimal(0)
    try:
        return Decimal(str(x).replace(",", "").replace(" ", ""))
    except Exception:
        return Decimal(0)


def job_no(x) -> str:
    return norm(x).replace("–", "-").replace("—", "-").rstrip(",").strip()


def method_of(text: str) -> str:
    u = (text or "").upper()
    for key, name in (("REVOLUT", "Revolut"), ("WISE", "Wise"), ("PAYPAL", "PayPal"), ("CASH", "Cash")):
        if key in u:
            return name
    return "Bank"


class Importer:
    def __init__(self, db):
        self.db = db
        self.clients: dict[str, Client] = {c.name: c for c in db.scalars(select(Client))}
        self.inspectors: dict[str, Inspector] = {i.name.lower(): i for i in db.scalars(select(Inspector))}
        self.users = {u.initials: u for u in db.scalars(select(User))}
        self.methods = {m.name: m for m in db.scalars(select(PaymentMethod))}
        self.jobs: dict[str, Job] = {j.job_number: j for j in db.scalars(select(Job))}
        self.stats = Counter()

    def client(self, name: str) -> Client | None:
        name = CLIENT_FIX.get(norm(name), norm(name))
        if not name:
            return None
        if name not in self.clients:
            c = Client(name=name, default_currency="USD")
            self.db.add(c)
            self.db.flush()
            self.clients[name] = c
            self.stats["clients"] += 1
        return self.clients[name]

    def inspector(self, name: str) -> Inspector | None:
        n = norm(name)
        if not n:
            return None
        key = n.lower()
        if key not in self.inspectors:
            i = Inspector(name=n)
            self.db.add(i)
            self.db.flush()
            self.inspectors[key] = i
            self.stats["inspectors"] += 1
        return self.inspectors[key]

    # ------------------------------------------------------------ P&L
    def pnl(self, path: str, month: str):
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        fx_seen: dict[tuple[str, str], Counter] = defaultdict(Counter)
        for ws in wb.worksheets:
            parts = ws.title.strip().split()
            if parts[0] not in MONTHS:
                continue
            m = f"{int(parts[1]) if len(parts) > 1 else 2025}-{MONTHS[parts[0]]:02d}"
            rows = ws.iter_rows(values_only=True)
            idx = {}
            for i, h in enumerate(next(rows)):
                k = ALIAS.get(norm(h))
                if norm(h) == "Итого":
                    break
                if k and k not in idx:
                    idx[k] = i
            for r in rows:
                g = lambda k: r[idx[k]] if k in idx and idx[k] < len(r) else None
                cname, jn = norm(g("client")), job_no(g("job"))
                if not cname or cname in ("Итого", "#REF!"):
                    continue
                if not num(g("invoice")) and not num(g("income")):
                    continue
                if not jn:  # the sheet has a few lines without a job number: give them a visible placeholder
                    if m != month:
                        continue
                    self.stats["no_job_number"] += 1
                    jn = f"БН-{m}-{self.stats['no_job_number']}"
                status = norm(g("status")) or "Сдан"
                if m != month and status not in ("В работе", "Пауза"):
                    continue
                cur = {1: "USD", 2: "EUR"}.get(int(num(g("cur")) or 0), "USD")
                fx = num(g("fx"))
                if fx > 1:
                    fx_seen[(m, cur)][fx] += 1
                client = self.client(cname)
                job = self.jobs.get(jn)
                owner = self.users.get(OWNER.get(norm(g("owner")), ""))
                if not job:
                    country = COUNTRY_FIX.get(norm(g("country")), norm(g("country")))
                    job = Job(job_number=jn, client_id=client.id, country=country, vendor=norm(g("vendor"))[:300] or None,
                              client_contact=norm(g("contact"))[:120] or None, client_job_number=norm(g("client_job"))[:120] or None,
                              owner_id=owner.id if owner else None, status=status if status in ("В работе", "Пауза") else "Сдан",
                              pre_november=m < month)
                    self.db.add(job)
                    self.db.flush()
                    self.jobs[jn] = job
                    self.stats["jobs"] += 1
                elif status in ("В работе", "Пауза"):
                    job.status = status
                rate, cost = num(g("rate")), num(g("cost"))
                unit = "day"
                if Decimal(0) < rate < Decimal(50):
                    unit = "hour" if client.name == "Qualcon" else "ton"
                insp = self.inspector(g("inspector"))
                line = JobLine(job_id=job.id, month=m, inspector_id=insp.id if insp else None,
                               dates_text=(g("dates").strftime("%d.%m.%Y") if isinstance(g("dates"), dt.datetime) else norm(g("dates")))[:300], quantity=num(g("qty")), unit=unit, currency=cur,
                               client_rate=rate, inspector_rate=cost, overtime_client=num(g("ot_client")),
                               overtime_inspector=num(g("ot_insp")), no_subcontractor=cost == 0)
                self.db.add(line)
                self.stats["lines"] += 1
        for (m, cur), cnt in fx_seen.items():
            rate = cnt.most_common(1)[0][0]
            fx = self.db.scalar(select(FxRate).where(FxRate.month == m, FxRate.currency == cur))
            if not fx:
                self.db.add(FxRate(month=m, currency=cur, rate=rate))
                self.stats["fx_rates"] += 1

    # ------------------------------------------------------------ requests
    def requests(self, path: str, month: str):
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        sheet_month = {"Июль": "2026-07", "Август": "2026-08", "Сентябрь": "2026-09", "Октябрь": "2026-10", "Ноябрь": "2026-11"}
        for ws in wb.worksheets:
            china = "China" in ws.title
            key = ws.title.replace("Requests", "").strip()
            for r in list(ws.iter_rows(values_only=True))[1:]:
                r = list(r) + [None] * 14
                if china:
                    typ, d, cl, country, insp, pay, irate, fac, dates, st = r[0], r[1], r[3], r[5], r[6], r[7], r[8], r[9], r[10], r[11]
                    notes = r[12]
                    if isinstance(d, dt.datetime):
                        rdate = d.date()
                    else:
                        mm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", str(d or ""))
                        rdate = dt.date(int(mm[3]), int(mm[2]), int(mm[1])) if mm else None
                else:
                    typ, cl, country, insp, pay, irate, fac, dates, st, notes = r[0], r[1], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10]
                    m = sheet_month.get(key)
                    rdate = dt.date.fromisoformat(m + "-01") if m else None
                status = REQ_STATUS.get(norm(st))
                if not status or not norm(cl):
                    continue
                m = rdate.strftime("%Y-%m") if rdate else None
                if m != month and status not in ("Принято в работу", "В процессе", "Перенос"):
                    continue
                client = self.client(cl)

                def money(v, default_cur=None):
                    mm = re.match(r"\s*([\d.,]+)\s*([A-Za-zА-я€$£]*)", str(v or ""))
                    if not mm:
                        return None, None
                    c = mm[2].lower()
                    cur = ("EUR" if c.startswith("eu") or c == "€" else "GBP" if c.startswith("gb") else
                           "INR" if c.startswith("руп") else "USD" if c.startswith("us") or c == "$" else default_cur)
                    return num(mm[1]), cur

                cr, cc = money(pay, "USD" if china else None)
                ir, ic = money(irate, "USD" if china else None)
                t = norm(typ)
                t = t.split()[0].capitalize() if t and not t[0].isdigit() else "Inspection"
                self.db.add(Request(received_date=rdate, type=t, client_id=client.id if client else None,
                                    country=COUNTRY_FIX.get(norm(country), norm(country).title() if norm(country).islower() else norm(country)),
                                    factory=norm(fac)[:300], dates_text=norm(dates)[:200], client_rate=cr, client_currency=cc,
                                    inspector_rate=ir, inspector_currency=ic, inspector_id=(self.inspector(insp).id if norm(insp) else None),
                                    status=status, cancel_reason="перенос из Google Таблиц" if status == "Перенос" else None,
                                    notes=norm(notes)[:2000] or None))
                self.stats["requests"] += 1

    # ------------------------------------------------------------ client invoices
    def sales(self, path: str):
        ws = openpyxl.load_workbook(path, data_only=True)["Invoice Register"]
        rows = ws.iter_rows(values_only=True)
        h = [norm(x) for x in next(rows)]
        for r in rows:
            d = dict(zip(h, r))
            if not d.get("Invoice No.") or not d.get("Invoice Amount"):
                continue
            number = norm(d["Invoice No."])
            if self.db.scalar(select(SalesInvoice).where(SalesInvoice.number == number)):
                continue
            client = self.client(d.get("Folder / Business Unit"))
            gst_yes = norm(d.get("GST Applicable")).lower() == "yes"
            if gst_yes and not client.is_indian:
                client.is_indian = True
                client.legal_name = norm(d.get("Customer"))
            elif not client.legal_name:
                client.legal_name = norm(d.get("Customer"))
            try:
                date = dt.datetime.strptime(norm(d["Invoice Date"]), "%d-%B-%Y").date()
            except ValueError:
                date = None
            amount = num(d["Invoice Amount"])
            taxable = num(d.get("Taxable Amount (INR)"))
            status = norm(d.get("Payment Status")) or "Not Verified"
            inv = SalesInvoice(number=number, date=date, client_id=client.id, currency=norm(d["Currency"]) or "USD",
                               amount=amount, status=status if status in ("Not Verified", "Отправлен клиенту", "Paid") else "Not Verified",
                               received_amount=num(d.get("Amount Received")) or None,
                               fx_rate=(taxable / amount).quantize(Decimal("0.0001")) if taxable and amount else None,
                               taxable_inr=taxable or None, cgst=num(d.get("CGST Amount (INR)")),
                               sgst=num(d.get("SGST Amount (INR)")), igst=num(d.get("IGST Amount (INR)")),
                               notes=norm(d.get("Notes")) or None)
            self.db.add(inv)
            self.db.flush()
            _sales_after(inv, self.db)
            self.stats["sales_invoices"] += 1

    # ------------------------------------------------------------ inspector invoices
    def invoices(self, path: str):
        ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
        rows = ws.iter_rows(values_only=True)
        h = [norm(x) for x in next(rows)]
        cur = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}
        for r in rows:
            d = dict(zip(h, r))
            name, amount = norm(d.get("Contractor / Inspector")), num(d.get("Invoice Amount"))
            if not name or not amount:
                continue
            insp = self.inspector(name)
            no = norm(d.get("Invoice №"))
            no = no[:-2] if no.endswith(".0") else no
            idate = d.get("Invoice date")
            m = self.methods.get(method_of(norm(d.get("Payment method"))))
            inv = InspectorInvoice(number=no or None, inspector_id=insp.id,
                                   invoice_date=idate.date() if isinstance(idate, dt.datetime) else None,
                                   dates_text=norm(d.get("Dates"))[:300], days=num(d.get("Days")) or None,
                                   rate=num(d.get("MD rate")) or None, amount=amount,
                                   currency=cur.get(norm(d.get("currency")), norm(d.get("currency")) or "USD"),
                                   payment_method_id=m.id if m else None, paid=d.get("Status of payment") is True,
                                   comment="; ".join(x for x in [norm(d.get("Comments")), norm(d.get("Payment method"))] if x) or None)
            inv.jobs = [self.jobs[j] for j in (job_no(x) for x in re.split(r"[;,/]", norm(d.get("EBFI №")))) if j in self.jobs]
            if inv.paid and not inv.paid_date:
                inv.paid_date = inv.invoice_date
            self.db.add(inv)
            self.stats["inspector_invoices"] += 1


def reset(db):
    for t in (inspector_invoice_jobs,):
        db.execute(delete(t))
    for model in (TdsEntry, InspectorInvoice, JobLine, Request, SalesInvoice, Job, FxRate, Inspector, Client, AuditLog):
        if model is SalesInvoice:
            db.execute(JobLine.__table__.update().values(sales_invoice_id=None))
        db.execute(delete(model))
    db.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pnl")
    ap.add_argument("--requests")
    ap.add_argument("--sales")
    ap.add_argument("--invoices")
    ap.add_argument("--month", default="2026-11")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if a.reset:
            reset(db)
        if not db.scalar(select(User).where(User.initials == "MB")):
            raise SystemExit("Сначала создайте пользователей: python -m scripts.create_admin")
        imp = Importer(db)
        if a.pnl:
            imp.pnl(a.pnl, a.month)
        if a.requests:
            imp.requests(a.requests, a.month)
        if a.sales:
            imp.sales(a.sales)
        if a.invoices:
            imp.invoices(a.invoices)
        db.commit()
        for k, v in imp.stats.items():
            print(f"{k:20s} {v}")


if __name__ == "__main__":
    main()
