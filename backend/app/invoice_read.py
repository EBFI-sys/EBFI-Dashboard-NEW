"""Read an inspector's invoice (PDF or Word): number, date, total, currency, days, rate, EBFI job numbers, inspector.
Text-based files only; a scanned PDF (a picture) has no text to read and the form is filled in by hand."""
import datetime as dt
import io
import re
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Inspector, Job

JOB = re.compile(r"\b(\d{2}\.\d{2}-\d{1,4})\b")
CUR = {"USD": "USD", "US$": "USD", "$": "USD", "EUR": "EUR", "€": "EUR", "EURO": "EUR", "GBP": "GBP", "£": "GBP",
       "INR": "INR", "₹": "INR", "RS": "INR", "RS.": "INR"}
NUM = r"(\d{1,3}(?:[ ,. ]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def text_of(filename: str, content: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(content)).pages)
    if name.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(content))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    raise ValueError("Прочитать можно PDF или Word (.docx). Старый .doc сохраните как .docx")


def _num(s: str) -> Decimal | None:
    s = s.replace(" ", " ").replace(" ", "")
    if re.search(r"[.,]\d{1,2}$", s):  # decimal part is the last separator
        whole, frac = s[:-len(re.search(r"[.,]\d{1,2}$", s)[0])], re.search(r"\d{1,2}$", s)[0]
        s = re.sub(r"[.,]", "", whole) + "." + frac
    else:
        s = re.sub(r"[.,]", "", s)
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _date(s: str) -> dt.date | None:
    for pat, f in ((r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", "dmy"), (r"(\d{4})-(\d{2})-(\d{2})", "ymd"),
                   (r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})", "dMy"),
                   (r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", "Mdy")):
        m = re.search(pat, s)
        if not m:
            continue
        try:
            if f == "dmy":
                return dt.date(int(m[3]), int(m[2]), int(m[1]))
            if f == "ymd":
                return dt.date(int(m[1]), int(m[2]), int(m[3]))
            if f == "dMy" and m[2].lower()[:3] in MONTHS:
                return dt.date(int(m[3]), MONTHS[m[2].lower()[:3]], int(m[1]))
            if f == "Mdy" and m[1].lower()[:3] in MONTHS:
                return dt.date(int(m[3]), MONTHS[m[1].lower()[:3]], int(m[2]))
        except ValueError:
            continue
    return None


def _currency(s: str) -> str | None:
    for k in sorted(CUR, key=len, reverse=True):
        if re.search(r"(?<![A-Za-z])" + re.escape(k) + r"(?![A-Za-z])", s, re.I if k.isalpha() else 0):
            return CUR[k]
    return None


def read(db: Session, filename: str, content: bytes) -> dict:
    text = text_of(filename, content)
    flat = re.sub(r"[ \t]+", " ", text)
    out: dict = {"text_found": bool(flat.strip())}
    if not flat.strip():
        out["message"] = "В файле нет текста (скан?) — заполните счёт вручную"
        return out

    m = re.search(r"(?:invoice|inv|счет|счёт|bill)\s*(?:no\.?|number|num\.?|#|№)\s*[:#№.]?\s*([A-Za-z0-9][\w/\-.]{0,30})", flat, re.I)
    if m and not re.fullmatch(r"date|dated?", m[1], re.I):
        out["number"] = m[1].rstrip(".")
    m = re.search(r"(?:invoice\s*date|date\s*of\s*invoice|date|дата)\s*[:.]?\s*([^\n]{0,40})", flat, re.I)
    d = _date(m[1]) if m else None
    out["invoice_date"] = (d or _date(flat)).isoformat() if (d or _date(flat)) else None

    # the total: the last «total / amount due / итого» line with a number
    amount, cur = None, None
    for line in flat.splitlines():
        if re.search(r"grand\s*total|total\s*(?:amount|due|payable)?|amount\s*(?:due|payable)|balance\s*due|итого|к оплате|всего", line, re.I):
            nums = [_num(x) for x in re.findall(NUM, line)]
            nums = [x for x in nums if x is not None and x > 0]
            if nums:
                amount, cur = max(nums), _currency(line) or cur
    if amount is None:  # fall back to the biggest amount next to a currency sign
        best = None
        for mm in re.finditer(r"(?:USD|EUR|GBP|INR|US\$|[$€£₹])\s*" + NUM + "|" + NUM + r"\s*(?:USD|EUR|GBP|INR)", flat):
            v = _num(mm[1] or mm[2])
            if v and (best is None or v > best[0]):
                best = (v, _currency(mm[0]))
        if best:
            amount, cur = best
    out["amount"] = float(amount) if amount is not None else None
    out["currency"] = cur or _currency(flat)

    m = re.search(NUM + r"\s*(?:man[- ]?days?|days?|MD|дн(?:ей|я)?)\b", flat, re.I)
    if m and _num(m[1]) and _num(m[1]) < 400:
        out["days"] = float(_num(m[1]))
    m = re.search(r"(?:rate|per\s*day|daily\s*rate|ставка)[^\d\n]{0,20}" + NUM, flat, re.I)
    if not m:  # «22 days x USD 145.00»
        m = re.search(r"days?\s*[x×*@]\s*(?:USD|EUR|GBP|INR|[$€£₹])?\s*" + NUM, flat, re.I)
    if m and _num(m[1]):
        out["rate"] = float(_num(m[1]))

    numbers = list(dict.fromkeys(JOB.findall(flat)))
    jobs = list(db.scalars(select(Job).where(Job.job_number.in_(numbers), Job.deleted.is_(False)))) if numbers else []
    out["job_numbers"] = numbers
    out["job_ids"] = [j.id for j in jobs]
    out["unknown_jobs"] = [n for n in numbers if n not in {j.job_number for j in jobs}]

    low = flat.lower()
    best = None
    for i in db.scalars(select(Inspector)):
        name = (i.name or "").strip()
        if len(name) >= 5 and name.lower() in low and (best is None or len(name) > len(best.name)):
            best = i
    if not best and jobs:  # the inspector of the jobs on the invoice
        ids = {l.inspector_id for j in jobs for l in j.lines if not l.deleted and l.inspector_id}
        if len(ids) == 1:
            best = db.get(Inspector, ids.pop())
    out["inspector_id"] = best.id if best else None
    return out
