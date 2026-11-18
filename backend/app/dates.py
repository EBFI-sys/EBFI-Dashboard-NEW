"""Read the agreed inspection dates out of the free-text «Даты» field.

Handles the forms used in the sheets: "05,06,07.10.2026", "01-30.10.2026", "13.11.2026",
"17.09, 01.10.2026", "02,03,18.07" (year taken from the line's month) and "2026-11-20".
"""
import datetime as dt
import re

PART = re.compile(r"((?:\d{1,2}\s*[-–,]\s*)*\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?")
ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
SPAN = re.compile(r"(\d{1,2})\.(\d{1,2})\s*[-–]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")  # 05.10-05.11.2026


def parse_dates(text: str | None, month: str | None = None) -> list[dt.date]:
    if not text:
        return []
    default_year = int(month[:4]) if month else dt.date.today().year
    out: set[dt.date] = set()
    for y, m, d in ISO.findall(text):
        try:
            out.add(dt.date(int(y), int(m), int(d)))
        except ValueError:
            pass
    text = ISO.sub(" ", text)
    for d1, m1, d2, m2, y in SPAN.findall(text):
        try:
            a, b = dt.date(int(y), int(m1), int(d1)), dt.date(int(y), int(m2), int(d2))
        except ValueError:
            continue
        while a <= b and len(out) < 400:
            out.add(a)
            a += dt.timedelta(days=1)
    text = SPAN.sub(" ", text)
    matches = list(PART.finditer(text))
    years = [m.group(3) for m in matches]
    for i, mt in enumerate(matches):
        days, mon, year = mt.group(1), int(mt.group(2)), mt.group(3)
        if not year:  # "17.09, 01.10.2026": borrow the year of a later part
            year = next((y for y in years[i + 1:] if y), None)
        y = int(year) if year else default_year
        if y < 100:
            y += 2000
        for piece in re.split(r"\s*,\s*", days):
            if not piece:
                continue
            rng = re.split(r"\s*[-–]\s*", piece)
            try:
                a = int(rng[0])
                b = int(rng[-1])
            except ValueError:
                continue
            if b < a or b - a > 31:
                continue
            for day in range(a, b + 1):
                try:
                    out.add(dt.date(y, mon, day))
                except ValueError:
                    pass
    return sorted(out)


def format_dates(dates: list[dt.date]) -> str:
    """Inverse of parse_dates: group by month, e.g. "05,06,07.10.2026; 01.11.2026"."""
    by_month: dict[tuple[int, int], list[int]] = {}
    for d in sorted(set(dates)):
        by_month.setdefault((d.year, d.month), []).append(d.day)
    return "; ".join(",".join(f"{x:02d}" for x in days) + f".{m:02d}.{y}" for (y, m), days in by_month.items())
