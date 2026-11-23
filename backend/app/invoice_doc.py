"""Client invoice as a Word file (and PDF, and the TUV Rheinland Annexure) from the client's template.

The template is the client's last real invoice with the figures replaced by placeholders ([NNN], [Job No], [Qty]…).
Following the invoicing instructions, the document is edited in place, never rebuilt: the service row of the template
is cloned once per invoice line, placeholders are replaced paragraph by paragraph (text into the first run, the
other runs emptied), so fonts (Times New Roman 10 pt), borders and the EBFI bank block stay exactly as in the template."""
import copy
import datetime as dt
import io
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from decimal import ROUND_HALF_UP, Decimal

from lxml import etree
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clock
from . import sharepoint as sp
from .config import settings
from .dates import format_dates, parse_dates
from .invoice_rules import Rule, rule_for
from .models import Client, Inspector, Job, JobLine, SalesInvoice

NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % NS
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
HERE = os.path.join(os.path.dirname(__file__), "invoice_templates")
TEMPLATE_DIR = "Templates/Invoices"  # under EBFI/ on OneDrive: edited copies there win over the built-in ones
UNITS = {"day": "Man-Day", "hour": "Man-Hour", "ton": "MT", "lump": "Per Lot", "pcs": "Pcs", "ot": "OT"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
PLACEHOLDER = re.compile(r"\[(?:NNN|DD-Month-YYYY|DD\.MM\.YYYY|Month(?: YYYY / dates)?|COUNTRY|Country|Job series|Job No|"
                         r"Vendor name|Inspector name|Coordinator name|Dates|SAP number|End client|Client job number|"
                         r"Client job ref|Vessel name|Qty|Rate|Amount|Exchange rate|Inspection subject|PO No|Equipment / cargo|"
                         r"Days|Day rate USD|Day rate INR|Amount INR|Amount INR with GST|Overtime|Total INR|Total INR with GST)\]")
TWO = Decimal("0.01")


class InvoiceError(Exception):
    pass


# ---------------------------------------------------------------- numbers and dates
def r2(x) -> Decimal:
    return Decimal(x).quantize(TWO, rounding=ROUND_HALF_UP)


def fmt(x, style: str = "std", decimals: int | None = None) -> str:
    """std 4,920 / 1,234.50 · eu 8 151 / 0,17 / 47 944,830 · inr 16,25,746.80"""
    x = Decimal(x)
    if style == "inr":
        s = f"{r2(x):.2f}"
        whole, frac = s.split(".")
        neg = whole.startswith("-")
        whole = whole.lstrip("-")
        if len(whole) > 3:
            head, tail = whole[:-3], whole[-3:]
            head = ",".join(re.findall(r"\d{1,2}(?=(?:\d{2})*$)", head))
            whole = f"{head},{tail}"
        return ("-" if neg else "") + whole + "." + frac
    if decimals is None:
        decimals = 0 if x == x.to_integral_value() else (3 if abs(x) >= 1000 and x != r2(x) else 2)
    s = f"{x:,.{decimals}f}"
    if style == "eu":
        s = s.replace(",", " ").replace(".", ",")
    return s


def month_end(month: str) -> dt.date:
    y, m = int(month[:4]), int(month[5:7])
    return dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)


def long_date(d: dt.date) -> str:
    return f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}"


def submission_date(d: dt.date) -> dt.date:
    """TUV Rheinland India / LRQA India: the 5th of the following month."""
    return dt.date(d.year + d.month // 12, d.month % 12 + 1, 5)


# ---------------------------------------------------------------- templates
def template_bytes(name: str) -> bytes:
    """EBFI/Templates/Invoices/<name> on OneDrive when it is there (so templates can be edited in Word), else built in."""
    if sp.enabled():
        try:
            g = sp.graph()
            item = g.item(f"{settings.ms_root}/{TEMPLATE_DIR}/{name}")
            url = item and item.get("@microsoft.graph.downloadUrl")
            if url:
                with urllib.request.urlopen(url, timeout=60) as r:
                    return r.read()
        except Exception:  # noqa: BLE001 - fall back to the built-in template
            pass
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        raise InvoiceError(f"Нет шаблона {name}")
    with open(path, "rb") as f:
        return f.read()


def publish_templates(force: bool = False) -> list[str]:
    """Copy the built-in templates to EBFI/Templates/Invoices on OneDrive (existing files are kept unless force)."""
    g = sp.graph()
    folder = g.path_folder(*TEMPLATE_DIR.split("/"))
    have = {c["name"] for c in g.children(folder["id"])}
    done = []
    for name in sorted(os.listdir(HERE)):
        if name.startswith(".") or (name in have and not force):
            continue
        with open(os.path.join(HERE, name), "rb") as f:
            g.upload(folder["id"], name, f.read(), None, conflict="replace")
        done.append(name)
    return done


# ---------------------------------------------------------------- word xml helpers
def _t(p) -> str:
    return "".join(t.text or "" for t in p.iter(W + "t"))


def _set(p, text: str) -> None:
    ts = list(p.iter(W + "t"))
    if not ts:
        if not text:
            return
        r = etree.SubElement(p, W + "r")
        rpr = p.find(f"{W}pPr/{W}rPr")
        if rpr is not None:
            r.append(copy.deepcopy(rpr))
        ts = [etree.SubElement(r, W + "t")]
    ts[0].text = text
    ts[0].set(XML_SPACE, "preserve")
    for t in ts[1:]:
        t.text = ""
        t.set(XML_SPACE, "preserve")


def _paras(el):
    return list(el.iter(W + "p"))


def _cells(tr):
    return tr.findall(W + "tc")


def _row_text(tr) -> str:
    return " ".join(_t(p) for p in _paras(tr))


def _replace(p, values: dict[str, str]) -> None:
    text = _t(p)
    if "[" not in text:
        return
    new = text
    for k, v in values.items():
        new = new.replace(f"[{k}]", v)
    if new != text:
        _set(p, new)


# ---------------------------------------------------------------- what goes on the invoice
def _final_client(job: Job) -> str:
    m = re.search(r"Финальный клиент:\s*(.+)", job.notes or "")
    return m[1].strip() if m else ""


def _country(c: str | None) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() for w in (c or "").split())


def items_of(db: Session, inv: SalesInvoice, rule: Rule, line_ids: list[int] | None = None) -> list[dict]:
    """line_ids: the lines as they were on the invoice (a credit note keeps them after they are released)."""
    q = select(JobLine).where(JobLine.id.in_(line_ids)) if line_ids else select(JobLine).where(JobLine.sales_invoice_id == inv.id)
    lines = list(db.scalars(q.where(JobLine.deleted.is_(False))))
    lines.sort(key=lambda l: (l.job.job_number, l.month, l.grp or 1))
    insp = {i.id: i.name for i in db.scalars(select(Inspector).where(Inspector.id.in_({l.inspector_id for l in lines if l.inspector_id})))}
    out = []
    for l in lines:
        j = l.job
        dates = parse_dates(l.dates_text, l.month)
        base = {"job": j.job_number, "country": j.country or "", "vendor": j.vendor or "", "inspector": insp.get(l.inspector_id, ""),
                "coordinator": j.client_contact or "", "client_ref": j.client_job_number or "", "end_client": _final_client(j),
                "dates": format_dates(dates) if dates else (l.dates_text or ""), "month": l.month,
                "service": j.service_type or "Inspection", "equipment": j.equipment or j.cargo or "",
                "cargo": j.cargo or "", "tonnage": j.tonnage}
        qty, rate = Decimal(l.quantity or 0), Decimal(l.client_rate or 0)
        if l.unit == "ton" and not qty and j.tonnage:  # marine loading: the tonnage from the job card
            qty = Decimal(j.tonnage)
        out.append({**base, "kind": "line", "unit": l.unit or "day", "qty": qty, "rate": rate, "amount": qty * rate})
        if Decimal(l.overtime_client or 0):
            ot = Decimal(l.overtime_client)
            out.append({**base, "kind": "ot", "unit": "ot", "qty": Decimal(1), "rate": ot, "amount": ot})
    for x in inv.extra_lines or []:  # lab analysis, draft survey… added in the invoice dialog
        qty, rate = Decimal(str(x.get("qty") or 0)), Decimal(str(x.get("rate") or 0))
        job = next((i for i in out if i["job"] == x.get("job")), out[0] if out else {})
        out.append({**{k: job.get(k, "") for k in ("job", "country", "vendor", "inspector", "coordinator", "client_ref",
                                                    "end_client", "dates", "month", "service", "equipment", "cargo", "tonnage")},
                    "kind": "extra", "proto": int(x.get("proto") or 0), "unit": x.get("unit") or "lump", "qty": qty, "rate": rate,
                    "amount": qty * rate, "text": x.get("text") or ""})
    return out


# ---------------------------------------------------------------- the document
def suggest_marine(db: Session, inv: SalesInvoice, protos: list[dict]) -> list[dict]:
    """Extra rows of a marine survey from the job's cargo, tonnage and country (instructions, section 6):
    corn — 1 composite sample (750 $ Argentina / 795 $ Brazil); soya and others — ceil(MT / 5000) lots × 660 $
    + pesticides 1 × 150 $; draft survey 1 × 700 $ (Argentina) / 600 $ (Brazil). Rates can be changed before saving."""
    import math
    rule = rule_for(db.get(Client, inv.client_id))
    if not rule or rule.style != "eu" or not protos:
        return []
    jobs = {l.job for l in db.scalars(select(JobLine).where(JobLine.sales_invoice_id == inv.id))}
    out = []
    find = lambda *words: next((p["idx"] for p in protos if all(w in p["label"].lower() for w in words)), None)  # noqa: E731
    for j in sorted(jobs, key=lambda x: x.job_number):
        if not j.tonnage:
            continue
        country = (j.country or "").lower()
        brazil = "brazil" in country
        corn = any(w in (j.cargo or "").lower() for w in ("corn", "maize", "кукуруз"))
        lab, pest, draft = find("lab", "composite") or find("lab"), find("pesticide"), find("draft")
        if lab is not None:
            if corn:
                out.append({"proto": lab, "qty": 1, "rate": 795 if brazil else 750, "job": j.job_number})
            else:
                out.append({"proto": lab, "qty": math.ceil(float(j.tonnage) / 5000), "rate": 660, "job": j.job_number})
                if pest is not None:
                    out.append({"proto": pest, "qty": 1, "rate": 150, "job": j.job_number})
        if draft is not None:
            out.append({"proto": draft, "qty": 1, "rate": 600 if brazil else 700, "job": j.job_number})
    return out


def build_docx(db: Session, inv: SalesInvoice, line_ids: list[int] | None = None,
               credit: tuple[str, dt.date] | None = None) -> tuple[bytes, list[str], dict]:
    """credit=(CN-2627-NNN, date): the credit note against this invoice — the same document with the title
    «INVOICE № CN-… / CREDIT NOTE PASS AGAINST INVOICE № EBFI-…» and the credit note's date."""
    client = db.get(Client, inv.client_id)
    rule = rule_for(client)
    if not rule:
        raise InvoiceError(f"Для клиента «{client.name if client else '—'}» не выбран шаблон инвойса (Справочники → Клиент)")
    items = items_of(db, inv, rule, line_ids)
    if not items:
        raise InvoiceError("В инвойсе нет строк работ: создайте его через «Инвойс из работ»")
    warnings: list[str] = []
    style = rule.style
    src = template_bytes(rule.file)
    zin = zipfile.ZipFile(io.BytesIO(src))
    root = etree.fromstring(zin.read("word/document.xml"))
    tbl = root.find(f".//{W}tbl")
    rows = tbl.findall(W + "tr")
    texts = [_row_text(r) for r in rows]

    perf = next(i for i, t in enumerate(texts) if "Performance Date" in t)
    recv = next(i for i, t in enumerate(texts) if "Receiver Details" in t)
    first_total = next(i for i in range(perf + 1, recv) if "[Job No]" not in texts[i])
    protos = rows[perf + 1:first_total]
    totals = rows[first_total:recv]
    header = "\n".join(texts[:2])
    m = re.search(r"Currency:\s*([A-Z$]+)", header)
    base_cur = m[1] if m else "USD"
    inr_only = base_cur == "INR"
    has = lambda s: any(s in t for t in texts[first_total:recv])  # noqa: E731
    gst_kind = "igst" if has("IGST") else "cgst" if has("CGST") else None
    has_inr = has("Indian Rupees") or inr_only
    wht = has("Withholding")

    fx = r2(inv.fx_rate) if inv.fx_rate else None  # the invoice shows and uses the rate with 2 decimals
    if (has_inr or rule.inr_lines) and inv.currency != "INR" and not fx:
        raise InvoiceError(f"Нет курса {inv.currency}/INR за месяц инвойса: внесите его в «Справочники → Курс валют» или в поле «Курс к INR» инвойса")
    if gst_kind and not client.is_indian:
        warnings.append("В шаблоне есть GST, а в карточке клиента не отмечено «Клиент из Индии» — реестр не начислит GST и TDS")
    if not gst_kind and client.is_indian:
        warnings.append("Клиент отмечен как индийский, а в шаблоне нет GST")
    if fx is None:
        fx = Decimal(1)

    # amounts
    if rule.inr_lines and inv.currency != "INR":
        for it in items:
            it["rate"] = r2(it["rate"] * fx)
            it["amount"] = it["qty"] * it["rate"]
    total = sum((it["amount"] for it in items), Decimal(0))
    base_inr = r2(total) if (rule.inr_lines or inr_only) else r2(total * fx)
    cgst = r2(base_inr * Decimal("0.09")) if gst_kind == "cgst" else Decimal(0)
    igst = r2(base_inr * Decimal("0.18")) if gst_kind == "igst" else Decimal(0)
    grand_inr = base_inr + 2 * cgst + igst
    wht_amt = r2(total * Decimal("0.05")) if wht else Decimal(0)
    if rule.limit_inr and grand_inr > rule.limit_inr:
        warnings.append(f"Сумма с GST ₹{fmt(grand_inr, 'inr')} больше лимита ₹20,00,000 — разделите работы на несколько инвойсов")

    cur_label = {"EUR": "EURO" if base_cur == "EURO" else "EUR"}.get(inv.currency, inv.currency)
    money_style = "inr" if (rule.inr_lines or inr_only) else style

    # service rows: one per invoice line, cloned from the template row with the same unit (MT, Per Lot, Pcs…)
    def proto_for(it) -> etree._Element:
        if it["kind"] == "extra" and 0 <= it.get("proto", 0) < len(protos):
            return protos[it["proto"]]
        want = UNITS.get(it["unit"], "")
        for p in protos:
            cells = _cells(p)
            if len(cells) > 2 and _t(cells[2]).strip() == want:
                return p
        return protos[0]

    anchor = protos[0]
    new_rows = []
    for it in items:
        tr = copy.deepcopy(proto_for(it))
        cells = _cells(tr)
        vals = {"Job No": it["job"], "COUNTRY": it["country"].upper(), "Country": _country(it["country"]),
                "Vendor name": it["vendor"], "Vessel name": re.sub(r"^\s*(?:M\.?V\.?|M/V)\s+", "", it["vendor"], flags=re.I), "Inspector name": it["inspector"],
                "Coordinator name": it["coordinator"], "Dates": it["dates"],
                "Month YYYY / dates": it["dates"] or f"{MONTHS[int(it['month'][5:]) - 1]} {it['month'][:4]}",
                "SAP number": it["client_ref"], "Client job number": it["client_ref"], "Client job ref": it["client_ref"],
                "PO No": it["client_ref"], "End client": it["end_client"], "Inspection subject": it["service"],
                "Equipment / cargo": it["equipment"],
                "Qty": fmt(it["qty"], style, 3 if it["unit"] == "ton" and it["qty"] != it["qty"].to_integral_value() else None),
                "Rate": fmt(it["rate"], money_style), "Amount": fmt(it["amount"], money_style)}
        for p in _paras(tr):
            _replace(p, vals)
        if len(cells) > 2:
            if it["kind"] == "ot":
                desc = _paras(cells[1])
                _set(desc[0], "Over-Time")
                for p in desc[1:]:
                    cells[1].remove(p) if p.getparent() is cells[1] else _set(p, "")
            elif it["kind"] == "extra" and it.get("text"):
                _set(_paras(cells[1])[0], it["text"])
            unit = UNITS.get(it["unit"])
            if unit and it["kind"] != "extra" and _t(cells[2]).strip() != unit:
                _set(_paras(cells[2])[0], unit)
        new_rows.append(tr)
    for tr in new_rows:
        anchor.addprevious(tr)
    for p in protos:
        tbl.remove(p)

    # totals
    for tr in totals:
        t = _row_text(tr)
        if "Indian Rupees" in t or (inr_only and "Total Amount in" in t):
            v = base_inr
        elif "CGST" in t or "SGST" in t:
            v = cgst
        elif "IGST" in t:
            v = igst
        elif "Withholding" in t:
            v = wht_amt
        elif "TOTAL AMOUNT" in t:
            v = grand_inr if (gst_kind or inr_only) else (total - wht_amt)
        elif "Amount in" in t:
            v = total
        else:
            continue
        st = "inr" if ("INR" in t or "Rupees" in t or "GST" in t or (("TOTAL AMOUNT" in t) and (gst_kind or inr_only))) else money_style
        for p in _paras(tr):
            _replace(p, {"Amount": fmt(v, st), "Exchange rate": f"{fx:.2f}"})

    # header and title
    month = max(it["month"] for it in items)
    inv_date = inv.date or (month_end(month) if rule.date == "month_end" else clock.today())
    sub = submission_date(inv_date)
    countries = ", ".join(dict.fromkeys(it["country"].upper() for it in items if it["country"]))
    jobs = list(dict.fromkeys(it["job"] for it in items))
    series = jobs[0] if (rule.full_job_ref and len(jobs) == 1) else ", ".join(dict.fromkeys(j.split("-")[0] for j in jobs))
    for p in _paras(tbl):
        text = _t(p)
        if "[" in text:
            text2 = text.replace("EBFI-2627-[NNN]", inv.number).replace("[NNN]", inv.number.split("-")[-1])
            if "ubmission" in text2 and "[DD-Month-YYYY]" in text2 and "Dated" not in text2:
                text2 = text2.replace("[DD-Month-YYYY]", long_date(sub))
            text2 = (text2.replace("[DD-Month-YYYY]", long_date(inv_date)).replace("[DD.MM.YYYY]", sub.strftime("%d.%m.%Y"))
                     .replace("[Month]", MONTHS[int(month[5:]) - 1]).replace("[COUNTRY]", countries)
                     .replace("[Job series]", series))
            text2 = PLACEHOLDER.sub("", text2)
            if text2 != text:
                _set(p, text2)
    # currency of the template → the invoice currency (EUR invoice from a USD template and back)
    if not inr_only and cur_label != base_cur:
        rows = tbl.findall(W + "tr")
        recv_row = next(r for r in rows if "Receiver Details" in _row_text(r))
        for r in rows[:rows.index(recv_row)]:
            for p in _paras(r):
                t = _t(p)
                t2 = re.sub(rf"(?<![A-Za-z]){re.escape(base_cur)}(?![A-Za-z])", cur_label, t)
                if t2 != t:
                    _set(p, t2)

    if credit:
        cn_no, cn_date = credit
        title = _paras(tbl.findall(W + "tr")[0])
        _set(title[0], f"INVOICE № {cn_no}")
        second = title[1] if len(title) > 1 else copy.deepcopy(title[0])
        if len(title) == 1:
            title[0].addnext(second)
        _set(second, f"CREDIT NOTE PASS AGAINST INVOICE № {inv.number}")
        for p in _paras(tbl.findall(W + "tr")[1]):  # «Dated» / «Invoice Date» becomes the credit note's date
            t = _t(p)
            if long_date(inv_date) in t and (t.strip().startswith("Dated") or "ubmission" not in t):
                _set(p, t.replace(long_date(inv_date), long_date(cn_date), 1))

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for item in zin.infolist():
            data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True) if item.filename == "word/document.xml" else zin.read(item.filename)
            z.writestr(item, data)
    left = PLACEHOLDER.findall(" ".join(_t(p) for p in _paras(root)))
    if left:
        warnings.append(f"Не заполнены поля: {', '.join(sorted(set(left)))}")
    for it in items:
        if it["kind"] == "line" and not it["coordinator"] and "Coordinator" in "".join(texts):
            warnings.append(f"{it['job']}: не указан контакт клиента (Project Coordinator)")
            break
    summary = {"template": rule.title, "items": len(items), "total": float(total), "currency": inv.currency,
               "base_inr": float(base_inr) if has_inr or rule.inr_lines else None, "gst": float(2 * cgst + igst),
               "grand_inr": float(grand_inr) if gst_kind or inr_only else None, "wht": float(wht_amt), "date": inv_date.isoformat()}
    return out.getvalue(), warnings, summary


def build_annexure(db: Session, inv: SalesInvoice, summary: dict) -> bytes | None:
    """TUV Rheinland: the Excel Annexure with one row per invoice line; its totals equal the invoice."""
    from openpyxl import load_workbook
    client = db.get(Client, inv.client_id)
    rule = rule_for(client)
    if not rule or not rule.annexure:
        return None
    wb = load_workbook(io.BytesIO(template_bytes(rule.annexure)))
    ws = wb.active
    fx = r2(inv.fx_rate or 1)
    inv_date = dt.date.fromisoformat(summary["date"])
    items = [it for it in items_of(db, inv, rule) if it["kind"] != "extra"]
    rows: dict[tuple, dict] = {}
    for it in items:  # overtime goes into the OVERTIME column of its line
        key = (it["job"], it["inspector"], it["dates"])
        row = rows.setdefault(key, {**it, "ot": Decimal(0), "qty": Decimal(0), "line_amount": Decimal(0)})
        if it["kind"] == "ot":
            row["ot"] += it["amount"]
        else:
            row["qty"] += it["qty"]
            row["rate"] = it["rate"]
            row["line_amount"] += it["amount"]
    gst = Decimal("1.18")
    header = {"[NNN]": inv.number.split("-")[-1], "[Month]": MONTHS[inv_date.month - 1], "[Exchange rate]": float(fx)}
    for row in ws.iter_rows(min_row=1, max_row=4):
        for c in row:
            if isinstance(c.value, str):
                v = c.value
                if v.strip() == "[Exchange rate]":
                    c.value = float(fx)
                    continue
                v = v.replace("EBFI-2627-[NNN]", inv.number).replace("[Month]", header["[Month]"])
                v = v.replace("exchange USD/INR [DD.MM.YYYY]", f"exchange {inv.currency}/INR {inv_date:%d.%m.%Y}")
                v = v.replace("[DD.MM.YYYY]", submission_date(inv_date).strftime("%d.%m.%Y"))
                v = v.replace("D.S Business Galleria, Office no.1209,12th Floor,\nL.B.S Marg, Kanjurmarg (West). Mumbai – 400078",
                              "Office Number 904 to 910, 9th Floor, Damji Shamji Business 78,\nNear Kanjurmarg Station, Kanjurmarg (West), Mumbai-400078")
                c.value = v
    for c in ws[5]:
        if isinstance(c.value, str) and "(USD)" in c.value:
            c.value = c.value.replace("(USD)", f"({inv.currency})")
    proto = [copy.copy(c._style) for c in ws[6]]
    total_style = [copy.copy(c._style) for c in ws[7]]
    total_vals = [c.value for c in ws[7]]
    ws.delete_rows(6, 2)
    r = 6
    sum_l = sum_m = Decimal(0)
    for it in rows.values():
        rate_inr = r2(it["rate"] * fx)
        amount_inr = r2(it["line_amount"] * fx)
        ot_inr = r2(it["ot"] * fx)
        with_gst = r2((amount_inr + ot_inr) * gst)
        vals = [it["client_ref"], it["job"], it["dates"], float(it["qty"]), it["end_client"], it["vendor"], it["country"].upper(),
                "Inspection", it["inspector"], float(it["rate"]), float(rate_inr), float(amount_inr), float(with_gst),
                float(ot_inr) if ot_inr else None, it["coordinator"]]
        for col, v in enumerate(vals, start=1):
            c = ws.cell(row=r, column=col, value=v)
            if col - 1 < len(proto):
                c._style = copy.copy(proto[col - 1])
        sum_l += amount_inr + ot_inr
        sum_m += with_gst
        r += 1
    for col, st in enumerate(total_style, start=1):
        c = ws.cell(row=r, column=col)
        c._style = copy.copy(st)
        v = total_vals[col - 1]
        c.value = float(sum_l) if v == "[Total INR]" else float(sum_m) if v == "[Total INR with GST]" else v
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_pdf(docx: bytes, name: str) -> bytes | None:
    """PDF through LibreOffice when it is installed on the server (Times New Roman → metric-compatible Liberation Serif)."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, name + ".docx")
        with open(src, "wb") as f:
            f.write(docx)
        env = {**os.environ, "HOME": d}
        subprocess.run([soffice, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", d, src],
                       check=True, timeout=120, env=env, capture_output=True)
        pdf = os.path.join(d, name + ".pdf")
        if not os.path.exists(pdf):
            return None
        with open(pdf, "rb") as f:
            return f.read()
