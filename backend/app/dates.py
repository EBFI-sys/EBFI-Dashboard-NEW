"""Read the agreed inspection dates out of the free-text «Даты» field.

Handles the forms used in the sheets: "05,06,07.10.2026", "01-30.10.2026", "13.11.2026",
"17.09, 01.10.2026", "02,03,18.07" (year taken from the line's month) and "2026-11-20".
Also the wording clients use in requests: "16th, 17th, 18th, 19th & 20th Nov-26", "19-Nov-2026",
"20th OCT'26 TO 23rd OCT '26", "26/10/2026 to 29/10/2026", "23rd October, 2026". Vague text
("1st week of December", "ASAP") gives no dates.
"""
import datetime as dt
import re

from . import clock

PART = re.compile(r"((?:\d{1,2}\s*[-–,]\s*)*\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?")
ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
FULLSPAN = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(?:to|till|until|по|-|–|—)\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DAY = r"\d{1,2}\s*(?:st|nd|rd|th)?"
SEP = r"\s*(?:,|&|\+|and|to|-|–)\s*"
WORDS = re.compile(
    rf"((?:{DAY}{SEP})*{DAY})[\s-]*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
    r"(?:[\s,]*(\d{4})|\s*[-'’‘`]\s*(\d{2}))?(?![\d])", re.I)
SPAN = re.compile(r"(\d{1,2})\.(\d{1,2})\s*[-–]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})")  # 05.10-05.11.2026


def parse_dates(text: str | None, month: str | None = None) -> list[dt.date]:
    if not text:
        return []
    default_year = int(month[:4]) if month else clock.today().year
    out: set[dt.date] = set()
    for y, m, d in ISO.findall(text):
        try:
            out.add(dt.date(int(y), int(m), int(d)))
        except ValueError:
            pass
    text = ISO.sub(" ", text)
    text = SLASH.sub(r"\1.\2.\3", text)
    for d1, m1, y1, d2, m2, y2 in FULLSPAN.findall(text):  # "16.11.2026 to 30.11.2026"
        try:
            a, b = dt.date(int(y1), int(m1), int(d1)), dt.date(int(y2), int(m2), int(d2))
        except ValueError:
            continue
        while a <= b and len(out) < 400:
            out.add(a)
            a += dt.timedelta(days=1)
    text = FULLSPAN.sub(" ", text)
    out |= _words(text, default_year)
    text = WORDS.sub(" ", text)
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


def _words(text: str, default_year: int) -> set[dt.date]:
    """Dates written with month names; "X Oct to Y Oct" across two groups becomes a range."""
    groups = []  # (start, end, [dates])
    found = list(WORDS.finditer(text))
    years = [m.group(3) or m.group(4) for m in found]
    for i, mt in enumerate(found):
        mon = MONTHS[mt.group(2)[:3].lower()]
        year = years[i] or next((y for y in years[i + 1:] if y), None)
        y = int(year) if year else default_year
        if y < 100:
            y += 2000
        nums = [(int(n.group(1)), n.start()) for n in re.finditer(r"(\d{1,2})\s*(?:st|nd|rd|th)?", mt.group(1))]
        ds = []
        for k, (n, pos) in enumerate(nums):
            prev = nums[k - 1] if k else None
            between = mt.group(1)[prev[1]:pos] if prev else ""
            if prev and re.search(r"(?:to|-|–)\s*$", between, re.I) and n > prev[0]:
                rng = range(prev[0] + 1, n + 1)
            else:
                rng = [n]
            for d in rng:
                try:
                    ds.append(dt.date(y, mon, d))
                except ValueError:
                    pass
        groups.append((mt.start(), mt.end(), ds))
    out = {d for g in groups for d in g[2]}
    for (s1, e1, a), (s2, e2, b) in zip(groups, groups[1:]):
        if a and b and re.fullmatch(r"\s*(?:to|till|until|-|–)\s*", text[e1:s2], re.I):
            d = max(a)
            while d < min(b) and len(out) < 400:
                out.add(d)
                d += dt.timedelta(days=1)
    return out


def format_dates(dates: list[dt.date]) -> str:
    """Inverse of parse_dates: group by month, e.g. "05,06,07.10.2026; 01.11.2026"."""
    by_month: dict[tuple[int, int], list[int]] = {}
    for d in sorted(set(dates)):
        by_month.setdefault((d.year, d.month), []).append(d.day)
    return "; ".join(",".join(f"{x:02d}" for x in days) + f".{m:02d}.{y}" for (y, m), days in by_month.items())
