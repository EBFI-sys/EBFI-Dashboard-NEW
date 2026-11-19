"""Import the starting data from the four Google Sheets (downloaded as .xlsx).

    docker compose exec api python -m scripts.import_xlsx --reset \
        --pnl /data/import/pnl.xlsx --requests /data/import/requests.xlsx \
        --sales /data/import/sales.xlsx --invoices /data/import/invoices.xlsx [--months 2026-10,2026-11]

What is imported (decision of 18 Nov 2026 — no history before October 2026):
  * P&L lines, requests, client invoices and inspector invoices of --months only;
  * reference lists from the whole history: every inspector who worked in any month (spelling variants
    merged, see scripts/names.py) and every client name;
  * FX rates found in the P&L ($/€ column) for --months.
--reset wipes the work data and reference lists first (users are kept), so the command can be repeated.
"""
import argparse
import datetime as dt
import re
from collections import Counter, defaultdict
from decimal import Decimal

import openpyxl
from sqlalchemy import delete, select

from app.migrate import upgrade
from app.db import Base, SessionLocal, engine
from app.directory import clean_country, clean_vendor, same_vendor, vendor_key
from app.models import (AuditLog, Client, Country, FxRate, Inspector, InspectorInvoice, Job, JobLine, MonthClose,
                        PaymentMethod, Request, SalesInvoice, Setting, TdsEntry, User, Vendor, inspector_invoice_jobs)
from app.routers.dashboard import region_of
from app.routers.money import _sales_after
from scripts.names import canonical_groups, same_person, tokens

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
CLIENT_FIX = {"COPERION": "Coperion", "IRCLass": "IRClass", "TUVTPS": "TUV TPS", "MASMarine": "MAS Marine", "APPLUS": "Applus",
              # confirmed by MB on 18 Nov 2026
              "BV Italy": "BV Italia", "TUV R QATAR": "TUV Rheinland Qatar", "TUV Oman": "TUV Rheinland Oman",
              "TUVR Oman": "TUV Rheinland Oman", "TUV R Oman": "TUV Rheinland Oman"}
COUNTRY_FIX = {"China .": "China", "Gernany": "Germany", "Afrika": "Africa", "Marocco": "Morocco"}
OWNER = {"Л": "LM", "М": "MB", "С": "SV", "C": "SV", "Лю": "LR", "Д": "Д", "А": "А", "A": "А", "Т": "Т"}
REQ_STATUS = {"В процесссе": "В процессе", "В процессе": "В процессе", "Выполнено": "Выполнено", "Отмена": "Отмена",
              "Принято в работу": "Принято в работу", "Перенос": "Перенос"}
SHEET_MONTH = {"Июль": "2026-07", "Август": "2026-08", "Сентябрь": "2026-09", "Октябрь": "2026-10", "Ноябрь": "2026-11"}
# merges confirmed by MB on 18 Nov 2026, on top of the automatic rules in scripts/names.py
MANUAL_MERGE = {"Lin Chenghao": "Chonghao Lin", "Masud": "Masud Ramezanian", "Mojtaba": "Mojtaba Shahvali",
                "Orlando": "Orlando De Leon", "Andrei Kostiyuk": "Andrii Kostiuk", "Ceng Meng": "Cheng Meng", "Chenmeng": "Cheng Meng", "ChenMeng": "Cheng Meng",
                "Vasyliev Marko": "Mark Vasilyev", "Mohammad Sheydaeemr": "Mohammad Sheydaeemeehr",
                "Saad Mahmoud": "Saad Mehmood", "Soroush Soufi": "Soroush Soroufi", "K Parameswaran": "Parameswaran Kaliraj"}


# spellings that look alike but are different (or unconfirmed) people: never merged
KEEP_SEPARATE = {"Vitalik", "Rahim"}


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


def client_name(x) -> str:
    n = norm(x)
    return CLIENT_FIX.get(n, n)


def method_of(text: str) -> str:
    u = (text or "").upper()
    for key, name in (("REVOLUT", "Revolut"), ("WISE", "Wise"), ("PAYPAL", "PayPal"), ("CASH", "Cash")):
        if key in u:
            return name
    return "Bank"


def pnl_rows(path: str):
    """Yield (month, getter) for every real P&L row of every monthly tab."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    for ws in wb.worksheets:
        parts = ws.title.strip().split()
        if not parts or parts[0] not in MONTHS:
            continue
        m = f"{int(parts[1]) if len(parts) > 1 else 2025}-{MONTHS[parts[0]]:02d}"
        rows = ws.iter_rows(values_only=True)
        idx = {}
        for i, h in enumerate(next(rows)):
            if norm(h) == "Итого":
                break
            k = ALIAS.get(norm(h))
            if k and k not in idx:
                idx[k] = i
        for r in rows:
            g = (lambda row: lambda k: row[idx[k]] if k in idx and idx[k] < len(row) else None)(r)
            cname = norm(g("client"))
            if not cname or cname in ("Итого", "#REF!"):
                continue
            if not num(g("invoice")) and not num(g("income")):
                continue
            yield m, g


def split_people(cell: str) -> list[str]:
    return [p for p in (norm(x) for x in re.split(r"[/;]", cell or "")) if p]


class Importer:
    def __init__(self, db, months: set[str]):
        self.db = db
        self.months = months
        self.clients: dict[str, Client] = {}
        self.inspectors: dict[str, Inspector] = {}  # canonical name -> row
        self.alias: dict[str, str] = {}  # any spelling -> canonical name
        self.users = {u.initials: u for u in db.scalars(select(User))}
        self.methods = {m.name: m for m in db.scalars(select(PaymentMethod))}
        self.jobs: dict[str, Job] = {}
        self.grps: dict[str, dict] = {}  # job number -> {inspector id: assignment group}
        self.vendor_name: dict[str, str] = {}  # vendor_key -> canonical name
        self.stats = Counter()

    # ------------------------------------------------------------ reference lists from the whole history
    def build_references(self, pnl: str | None, requests: str | None, sales: str | None, invoices: str | None):
        names, countries, rates, methods = Counter(), defaultdict(Counter), {}, defaultdict(Counter)
        client_names = Counter()
        vendors: dict[str, Counter] = defaultdict(Counter)
        vendor_country: dict[str, Counter] = defaultdict(Counter)
        country_names = Counter()
        self.codes: dict[str, Counter] = defaultdict(Counter)  # client -> KK codes seen in its job numbers
        self.seq: dict[str, int] = {}  # "YY:KK" -> highest NNN in the history
        if pnl:
            for m, g in pnl_rows(pnl):
                client_names[client_name(g("client"))] += 1
                jm = re.match(r"^(\d{2})\.(\d{2})-(\d{1,4})$", job_no(g("job")))
                if jm:
                    self.codes[client_name(g("client"))][jm[2]] += 1
            # every job number anywhere in the old Табель, including rows without amounts: the queue continues after them
            for ws in openpyxl.load_workbook(pnl, data_only=True, read_only=True).worksheets:
                for row in ws.iter_rows(values_only=True):
                    for v in row:
                        jm = re.match(r"^(\d{2})\.(\d{2})-(\d{1,4})$", job_no(v)) if isinstance(v, str) else None
                        if jm:
                            k = f"{jm[1]}:{jm[2]}"  # year and client code: the queue restarts every year
                            self.seq[k] = max(self.seq.get(k, 0), int(jm[3]))
                cn = clean_country(g("country"))
                if cn:
                    country_names[cn] += 1
                v = clean_vendor(norm(g("vendor")))
                if v:
                    vendors[vendor_key(v)][v] += 1
                    if cn:
                        vendor_country[vendor_key(v)][cn] += 1
                people = split_people(norm(g("inspector")))
                for p in people:
                    names[p] += 1
                    countries[p][COUNTRY_FIX.get(norm(g("country")), norm(g("country")))] += 1
                if len(people) == 1 and num(g("cost")) >= 50:
                    rates[people[0]] = (m, num(g("cost")), {1: "USD", 2: "EUR"}.get(int(num(g("cur")) or 0), "USD"))
        if invoices:
            ws = openpyxl.load_workbook(invoices, data_only=True).worksheets[0]
            rows = ws.iter_rows(values_only=True)
            h = [norm(x) for x in next(rows)]
            for r in rows:
                d = dict(zip(h, r))
                n = norm(d.get("Contractor / Inspector"))
                if n and num(d.get("Invoice Amount")):
                    names[n] += 1
                    methods[n][method_of(norm(d.get("Payment method")))] += 1
                    if norm(d.get("Country")):
                        countries[n][norm(d.get("Country"))] += 1
        if requests:
            for row in self._request_rows(requests):
                if row["client"]:
                    client_names[client_name(row["client"])] += 1
                cn = clean_country(row["country"])
                if cn:
                    country_names[cn] += 1
        if sales:
            for d in self._sales_rows(sales):
                client_names[client_name(d.get("Folder / Business Unit"))] += 1

        # inspectors: merge spelling variants, then hand-checked merges
        auto = canonical_groups(names)
        for k in KEEP_SEPARATE:
            if k in auto:
                auto[k] = k
        self.alias = {k: MANUAL_MERGE.get(k, MANUAL_MERGE.get(v, v)) for k, v in auto.items()}
        merged = defaultdict(set)
        for k, v in self.alias.items():
            merged[v].add(k)
        for canon, variants in sorted(merged.items()):
            c = Counter()
            for v in variants:
                c.update(countries[v])
            rate = max((rates[v] for v in variants if v in rates), default=None, key=lambda x: x[0])
            mc = Counter()
            for v in variants:
                mc.update(methods[v])
            others = sorted(v for v in variants if v != canon)
            insp = Inspector(name=canon, country=(c.most_common(1)[0][0] or None) if c else None,
                             rate=rate[1] if rate else None, currency=rate[2] if rate else None,
                             payment_method_id=self.methods[mc.most_common(1)[0][0]].id if mc else None,
                             notes=("Варианты написания: " + "; ".join(others)) if others else None)
            self.db.add(insp)
            self.inspectors[canon] = insp
        self.db.flush()
        self.stats["inspectors"] = len(self.inspectors)
        self.stats["inspector_spellings_merged"] = len(names) - len(self.inspectors)

        # clients: one row per legal entity, spelling variants differing only in case or spaces merged
        seen: dict[str, str] = {}
        for n, _ in client_names.most_common():
            key = re.sub(r"[\s._-]+", "", n.lower())
            if not n or key in seen or "/" in n:  # "BV / NORD" is a typo in the request log
                continue
            seen[key] = n
            c = Client(name=n, default_currency="USD")
            self.db.add(c)
            self.clients[n] = c
        self._client_key = seen
        for n, cnt in self.codes.items():  # the client's KK code: the one it used most often
            canon = seen.get(re.sub(r"[\s._-]+", "", n.lower()))
            if canon in self.clients and not self.clients[canon].job_code:
                self.clients[canon].job_code = cnt.most_common(1)[0][0]
        for code, last in self.seq.items():
            row = self.db.get(Setting, f"jobseq:{code}") or Setting(key=f"jobseq:{code}", value="0")
            row.value = str(max(last, int(row.value) if row.value.isdigit() else 0))
            self.db.add(row)
        self.stats["client_job_codes"] = sum(1 for c in self.clients.values() if c.job_code)
        self.db.flush()
        self.stats["clients"] = len(self.clients)

        # vendors from every month of the P&L: spelling variants merged (scripts → app/directory.py), alphabetical
        spell = Counter()
        country_of = defaultdict(Counter)
        for key, sp in vendors.items():
            spell.update(sp)
            for name in sp:
                country_of[name].update(vendor_country[key])
        groups: list[list[str]] = []
        for name, _ in spell.most_common():
            for g in groups:
                if all(same_vendor(name, x) for x in g):
                    g.append(name)
                    break
            else:
                groups.append([name])
        for g in sorted(groups, key=lambda g: g[0].lower()):
            canon = max(g, key=lambda x: (spell[x], x != x.upper(), len(x)))[:300]
            vc = Counter()
            for x in g:
                vc.update(country_of[x])
                self.vendor_name[x] = canon
            others = sorted(x for x in g if x != canon)
            self.db.add(Vendor(name=canon, country=vc.most_common(1)[0][0] if vc else None,
                               notes=("Варианты написания: " + "; ".join(others))[:2000] if others else None))
        self.stats["vendors"] = len(groups)
        self.stats["vendor_spellings_merged"] = len(spell) - len(groups)
        for cn in sorted(country_names):
            self.db.add(Country(name=cn, region=region_of(cn, {})))
        self.stats["countries"] = len(country_names)
        self.db.flush()

    @staticmethod
    def country(raw) -> str:
        """Clean single-country name; a list like "Germany/Italy" is kept as typed (it is not added to the list)."""
        return clean_country(raw) or norm(raw).strip(" .")

    def vendor(self, raw) -> str | None:
        v = clean_vendor(norm(raw))
        return self.vendor_name.get(v, v)[:300] if v else None

    def client(self, name) -> Client | None:
        n = client_name(name)
        if not n:
            return None
        canon = self._client_key.get(re.sub(r"[\s._-]+", "", n.lower()), n)
        if canon not in self.clients:
            c = Client(name=canon, default_currency="USD")
            self.db.add(c)
            self.db.flush()
            self.clients[canon] = c
        return self.clients[canon]

    def inspector(self, name: str) -> tuple[Inspector | None, str | None]:
        """Return (inspector, note). Multi-person cells map to the first person; unknown names are not created."""
        people = split_people(name)
        if not people:
            return None, None
        note = name if len(people) > 1 else None
        first = people[0]
        canon = self.alias.get(first)
        if canon:
            return self.inspectors[canon], note
        t = tokens(first)  # a spelling not seen in the P&L, e.g. from the request log
        for canon, insp in self.inspectors.items():
            if same_person(t, tokens(canon)):
                return insp, note
        return None, f"Инспектор: {name}"

    # ------------------------------------------------------------ P&L
    def pnl(self, path: str):
        fx_seen: dict[tuple[str, str], Counter] = defaultdict(Counter)
        for m, g in pnl_rows(path):
            if m not in self.months:
                continue
            jn = job_no(g("job"))
            if not jn:  # a few sheet lines have no job number: give them a visible placeholder
                self.stats["no_job_number"] += 1
                jn = f"БН-{m}-{self.stats['no_job_number']}"
            status = norm(g("status")) or "Сдан"
            cur = {1: "USD", 2: "EUR"}.get(int(num(g("cur")) or 0), "USD")
            fx = num(g("fx"))
            if fx > 1:
                fx_seen[(m, cur)][fx] += 1
            client = self.client(g("client"))
            job = self.jobs.get(jn)
            owner = self.users.get(OWNER.get(norm(g("owner")), ""))
            if not job:
                country = self.country(g("country"))
                job = Job(job_number=jn, client_id=client.id, country=country or None, vendor=self.vendor(g("vendor")),
                          client_contact=norm(g("contact"))[:120] or None, client_job_number=norm(g("client_job"))[:120] or None,
                          owner_id=owner.id if owner else None, status="Сдан")
                self.db.add(job)
                self.db.flush()
                self.jobs[jn] = job
                self.stats["jobs"] += 1
            if status in ("В работе", "Пауза") or (job.status == "Сдан" and m == max(self.months)):
                job.status = status if status in ("В работе", "Пауза", "Сдан") else "Сдан"
            rate, cost = num(g("rate")), num(g("cost"))
            unit = "day"
            if Decimal(0) < rate < Decimal(50):
                unit = "hour" if client.name == "Qualcon" else "ton"
            insp, note = self.inspector(norm(g("inspector")))
            dates = g("dates")
            g_of = self.grps.setdefault(jn, {})
            grp = g_of.setdefault(insp.id if insp else None, len(g_of) + 1)
            line = JobLine(job_id=job.id, month=m, grp=grp, inspector_id=insp.id if insp else None,
                           dates_text=(dates.strftime("%d.%m.%Y") if isinstance(dates, dt.datetime) else norm(dates))[:300] or None,
                           quantity=num(g("qty")), unit=unit, currency=cur, client_rate=rate, inspector_rate=cost,
                           overtime_client=num(g("ot_client")), overtime_inspector=num(g("ot_insp")),
                           no_subcontractor=cost == 0, notes=note)
            self.db.add(line)
            self.stats["lines"] += 1
        for (m, cur), cnt in fx_seen.items():
            self.db.add(FxRate(month=m, currency=cur, rate=cnt.most_common(1)[0][0]))
            self.stats["fx_rates"] += 1

    # ------------------------------------------------------------ requests
    def _request_rows(self, path: str):
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        for ws in wb.worksheets:
            china = "China" in ws.title
            key = ws.title.replace("Requests", "").strip()
            for r in list(ws.iter_rows(values_only=True))[1:]:
                r = list(r) + [None] * 14
                if china:
                    typ, d, cl, country, insp, pay, irate, fac, dates, st, notes = r[0], r[1], r[3], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12]
                    if isinstance(d, dt.datetime):
                        rdate = d.date()
                    else:
                        mm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", str(d or ""))
                        rdate = dt.date(int(mm[3]), int(mm[2]), int(mm[1])) if mm else None
                else:
                    typ, cl, country, insp, pay, irate, fac, dates, st, notes = r[0], r[1], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10]
                    m = SHEET_MONTH.get(key)
                    rdate = dt.date.fromisoformat(m + "-01") if m else None
                yield dict(china=china, type=typ, date=rdate, client=norm(cl), country=country, inspector=norm(insp),
                           pay=pay, irate=irate, factory=fac, dates=dates, status=REQ_STATUS.get(norm(st)), notes=notes)

    def requests(self, path: str):
        def money(v, default_cur=None):
            mm = re.match(r"\s*([\d.,]+)\s*([A-Za-zА-я€$£]*)", str(v or ""))
            if not mm:
                return None, None
            c = mm[2].lower()
            cur = ("EUR" if c.startswith("eu") or c == "€" else "GBP" if c.startswith("gb") else
                   "INR" if c.startswith("руп") else "USD" if c.startswith("us") or c == "$" else default_cur)
            return num(mm[1]), cur

        for q in self._request_rows(path):
            if not q["status"] or not q["client"] or not q["date"] or q["date"].strftime("%Y-%m") not in self.months:
                continue
            client = self.client(q["client"])
            cr, cc = money(q["pay"], "USD" if q["china"] else None)
            ir, ic = money(q["irate"], "USD" if q["china"] else None)
            t = norm(q["type"])
            t = t.split()[0].capitalize() if t and not t[0].isdigit() else "Inspection"
            insp, note = self.inspector(q["inspector"]) if q["inspector"] else (None, None)
            country = self.country(q["country"])
            notes = "\n".join(x for x in [norm(q["notes"])[:2000], note or ""] if x) or None
            self.db.add(Request(received_date=q["date"], type=t, client_id=client.id if client else None,
                                country=country or None,
                                factory=norm(q["factory"])[:300] or None, dates_text=(q["dates"].strftime("%d.%m.%Y") if isinstance(q["dates"], dt.datetime) else norm(q["dates"]))[:200] or None,
                                client_rate=cr, client_currency=cc, inspector_rate=ir, inspector_currency=ic,
                                inspector_id=insp.id if insp else None, inspector_ids=[insp.id] if insp else None,
                                status=q["status"],
                                cancel_reason="перенос из Google Таблиц" if q["status"] == "Перенос" else None, notes=notes))
            self.stats["requests"] += 1

    # ------------------------------------------------------------ client invoices
    def _sales_rows(self, path: str):
        wb = openpyxl.load_workbook(path, data_only=True)
        if "Invoice Register" not in wb.sheetnames:
            raise SystemExit(f"В {path} нет вкладки «Invoice Register». Вкладки: {wb.sheetnames}. "
                             "Скачайте таблицу EBFI_Sales_Invoices_Register_October_2026_EN_GST.")
        rows = wb["Invoice Register"].iter_rows(values_only=True)
        h = [norm(x) for x in next(rows)]
        for r in rows:
            d = dict(zip(h, r))
            if d.get("Invoice No.") and d.get("Invoice Amount"):
                yield d

    def sales(self, path: str):
        for d in self._sales_rows(path):
            try:
                date = dt.datetime.strptime(norm(d["Invoice Date"]), "%d-%B-%Y").date()
            except ValueError:
                date = d["Invoice Date"].date() if isinstance(d["Invoice Date"], dt.datetime) else None
            if not date or date.strftime("%Y-%m") not in self.months:
                continue
            client = self.client(d.get("Folder / Business Unit"))
            if norm(d.get("GST Applicable")).lower() == "yes":
                client.is_indian = True
            if not client.legal_name:
                client.legal_name = norm(d.get("Customer")) or None
            amount, taxable = num(d["Invoice Amount"]), num(d.get("Taxable Amount (INR)"))
            status = norm(d.get("Payment Status")) or "Not Verified"
            inv = SalesInvoice(number=norm(d["Invoice No."]), date=date, client_id=client.id, currency=norm(d["Currency"]) or "USD",
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
            idate = d.get("Invoice date")
            idate = idate.date() if isinstance(idate, dt.datetime) else None
            if not name or not amount or not idate or idate.strftime("%Y-%m") not in self.months:
                continue
            insp, _ = self.inspector(name)
            if not insp:
                continue
            no = norm(d.get("Invoice №"))
            no = no[:-2] if no.endswith(".0") else no
            m = self.methods.get(method_of(norm(d.get("Payment method"))))
            inv = InspectorInvoice(number=no or None, inspector_id=insp.id, invoice_date=idate,
                                   dates_text=(d["Dates"].strftime("%d.%m.%Y") if isinstance(d.get("Dates"), dt.datetime) else norm(d.get("Dates")))[:300] or None, days=num(d.get("Days")) or None,
                                   rate=num(d.get("MD rate")) or None, amount=amount,
                                   currency=cur.get(norm(d.get("currency")), norm(d.get("currency")) or "USD"),
                                   payment_method_id=m.id if m else None, paid=d.get("Status of payment") is True,
                                   paid_date=idate if d.get("Status of payment") is True else None,
                                   comment="; ".join(x for x in [norm(d.get("Comments")), norm(d.get("Payment method"))] if x) or None)
            inv.jobs = [self.jobs[j] for j in (job_no(x) for x in re.split(r"[;,/]", norm(d.get("EBFI №")))) if j in self.jobs]
            self.db.add(inv)
            self.stats["inspector_invoices"] += 1


def reset(db):
    db.execute(delete(inspector_invoice_jobs))
    db.execute(JobLine.__table__.update().values(sales_invoice_id=None))
    for model in (TdsEntry, InspectorInvoice, JobLine, Request, SalesInvoice, Job, FxRate, MonthClose, Inspector, Client,
                  Vendor, Country, AuditLog):
        db.execute(delete(model))
    db.execute(delete(Setting).where(Setting.key.like("jobseq:%")))
    db.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pnl")
    ap.add_argument("--requests")
    ap.add_argument("--sales")
    ap.add_argument("--invoices")
    ap.add_argument("--months", default="2026-10,2026-11")
    ap.add_argument("--month", help="устаревший параметр, игнорируется")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    Base.metadata.create_all(engine)
    upgrade(engine)
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.initials == "MB")):
            raise SystemExit("Сначала создайте пользователей: python -m scripts.create_admin")
        if a.reset:
            reset(db)
        elif db.scalar(select(Job).limit(1)):
            raise SystemExit("В базе уже есть данные. Запустите с --reset, чтобы загрузить заново.")
        imp = Importer(db, {m.strip() for m in a.months.split(",")})
        imp.build_references(a.pnl, a.requests, a.sales, a.invoices)
        if a.pnl:
            imp.pnl(a.pnl)
        if a.requests:
            imp.requests(a.requests)
        if a.sales:
            imp.sales(a.sales)
        if a.invoices:
            imp.invoices(a.invoices)
        db.commit()
        print(f"Месяцы: {', '.join(sorted(imp.months))}")
        for k, v in imp.stats.items():
            print(f"{k:28s} {v}")


if __name__ == "__main__":
    main()
