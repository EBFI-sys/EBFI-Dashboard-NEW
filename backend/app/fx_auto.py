"""Month-end RBI reference rates (published by FBIL) for USD, EUR and GBP, read from a public archive page.

Only months that are over are filled in, with the rate of their last published day, and a rate an admin entered
by hand is never changed. Until then the P&L uses the previous month's rate, marked as provisional, as before."""
import datetime as dt
import logging
import re
import urllib.request
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clock
from .config import settings
from .models import FxRate

log = logging.getLogger("ebfi.fx")
CODES = {"USDINR": "USD", "EURINR": "EUR", "GBPINR": "GBP"}


def fetch(url: str | None = None) -> str:
    req = urllib.request.Request(url or settings.fx_source, headers={"User-Agent": "Mozilla/5.0 (EBFI Ops)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def parse(page: str) -> dict[dt.date, dict[str, Decimal]]:
    """Rows «20-Nov-2026 | 92.9699 | 102.1504 | 121.9337 | 58.43» under a «Date USDINR EURINR GBPINR JPYINR» header."""
    text = re.sub(r"<[^>]+>", " ", page)
    text = re.sub(r"\s+", " ", text)
    head = re.search(r"Date\s+((?:(?:USD|EUR|GBP|JPY)INR\s*){3,4})", text)
    order = head.group(1).split() if head else ["USDINR", "EURINR", "GBPINR", "JPYINR"]
    out: dict[dt.date, dict[str, Decimal]] = {}
    for m in re.finditer(r"(\d{2}-[A-Z][a-z]{2}-\d{4})((?:\s+\d+\.\d+){3,4})", text):
        try:
            day = dt.datetime.strptime(m[1], "%d-%b-%Y").date()
        except ValueError:
            continue
        nums = m[2].split()
        out[day] = {CODES[c]: Decimal(n) for c, n in zip(order, nums) if c in CODES}
    return out


def import_month_end(db: Session, page: str | None = None) -> dict[str, dict[str, str]]:
    """Fill in missing month-end rates for months that are over. Returns what was added, e.g. {"2026-11": {"USD": "92.97"}}."""
    rows = parse(page if page is not None else fetch())
    if not rows:
        raise ValueError("на странице курсов не найдено ни одной строки")
    this_month = clock.today().strftime("%Y-%m")
    months = sorted({d.strftime("%Y-%m") for d in rows})
    have = {(r.month, r.currency) for r in db.scalars(select(FxRate))}
    added: dict[str, dict[str, str]] = {}
    for m in months:
        later = any(d.strftime("%Y-%m") > m for d in rows)
        if m >= this_month or not later:  # the month is not over, or its last days are not on the page yet
            continue
        last = max(d for d in rows if d.strftime("%Y-%m") == m)
        y, mo = int(m[:4]), int(m[5:])
        month_end = dt.date(y + mo // 12, mo % 12 + 1, 1) - dt.timedelta(days=1)
        if (month_end - last).days > 4:  # the page no longer shows the last days of that month: leave it to a person
            continue
        for cur, rate in rows[last].items():
            if (m, cur) not in have:
                db.add(FxRate(month=m, currency=cur, rate=rate))
                added.setdefault(m, {})[cur] = f"{rate} ({last:%d.%m})"
    db.commit()
    if added:
        log.warning("FX month-end rates added: %s", added)
    return added
