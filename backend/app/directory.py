"""Keep the vendor and country lists growing as people type new names."""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Country, FinalClient, Vendor

LEGAL = r"\b(co|company|corp|corporation|ltd|limited|llc|llp|inc|gmbh|ag|se|spa|s ?p ?a|srl|s ?r ?l|sas|s ?a ?s|sa|bv|nv|pvt|private|plc|oy|ab|as|kft|sro|s ?r ?o|pty|jsc|ojsc|ooo)\b"


def clean_vendor(name: str | None) -> str:
    n = (name or "").replace("\uff0c", ",").replace("\uff08", "(").replace("\uff09", ")")
    n = re.sub(r"^\s*m\s*/\s*s\.?\s*", "", n, flags=re.I)  # "M/s. Zhejiang ..." -> "Zhejiang ..."
    n = re.sub(r"\s+", " ", n).strip(" ,.;")
    return n


SUFFIX = {  # legal-form words, mapped to one spelling
    "co": "co", "company": "co", "corp": "corp", "corporation": "corp", "ltd": "ltd", "limited": "ltd", "llc": "llc",
    "llp": "llp", "inc": "inc", "gmbh": "gmbh", "ag": "ag", "se": "se", "spa": "spa", "srl": "srl", "sas": "sas",
    "sa": "sa", "bv": "bv", "nv": "nv", "pvt": "pvt", "private": "pvt", "plc": "plc", "oy": "oy", "ab": "ab", "as": "as",
    "kft": "kft", "sro": "sro", "pty": "pty", "jsc": "jsc",
}


def _parts(name: str) -> tuple[str, frozenset]:
    """("abbbase", {"ab"}): the name without legal-form words, and those words."""
    k = clean_vendor(name).lower()
    k = re.sub(r"\bs\.?\s?p\.?\s?a\b\.?", " spa ", k)
    k = re.sub(r"\bs\.?\s?r\.?\s?l\b\.?", " srl ", k)
    k = re.sub(r"\bs\.?\s?a\.?\s?s\b\.?", " sas ", k)
    words = re.findall(r"[\w]+", k)
    suffix = frozenset(SUFFIX[w] for w in words if w in SUFFIX) - {"co"}
    base = "".join(w for w in words if w not in SUFFIX)
    return base, suffix


def vendor_key(name: str) -> str:
    base, suffix = _parts(name)
    return base + ("|" + ",".join(sorted(suffix)) if suffix else "")


def same_vendor(a: str, b: str) -> bool:
    """Same base name and either the same legal form or one of them gives none.
    "Diemme Filtration" = "Diemme Filtration Srl", but "ABB AB" != "ABB AS" and "Flender GmbH" != "Flender Corporation"."""
    (ba, sa), (bb, sb) = _parts(a), _parts(b)
    return bool(ba) and ba == bb and (sa == sb or not sa or not sb)


def remember_vendor(db: Session, name: str | None, country: str | None = None) -> None:
    n = clean_vendor(name)
    if not n:
        return
    for v in db.scalars(select(Vendor)):
        if same_vendor(v.name, n):
            if country and not v.country:
                v.country = country
            return
    db.add(Vendor(name=n[:300], country=country or None))


def remember_final_client(db: Session, name: str | None) -> None:
    n = " ".join((name or "").split())[:200]
    if not n or n in ("-", "—"):
        return
    if not db.scalar(select(FinalClient).where(func.lower(FinalClient.name) == n.lower())):
        db.add(FinalClient(name=n))


COUNTRY_FIX = {"china": "China", "gernany": "Germany", "afrika": "Africa", "marocco": "Morocco", "huangry": "Hungary",
               "netherland": "Netherlands", "saudi arabai": "Saudi Arabia", "ksa": "Saudi Arabia", "singapor": "Singapore",
               "czech": "Czech Republic", "usa": "USA", "uk": "UK", "uae": "UAE", "us": "USA"}


def clean_country(name: str | None) -> str | None:
    """One country per name; lists ("Germany/Italy", "Germany, USA and Dubai") and regions are not countries."""
    n = re.sub(r"\s+", " ", (name or "")).strip(" .")
    if n.lower() in COUNTRY_FIX:
        return COUNTRY_FIX[n.lower()]
    if not n or re.search(r"[/,]| and ", n) or len(n) < 3 or n.lower() in ("europe", "asia"):
        return None
    if n.lower() in COUNTRY_FIX:
        return COUNTRY_FIX[n.lower()]
    words = n.split()
    if len(words) > 1 and len(set(w.lower() for w in words)) < len(words):  # "Italy Italy Germany"
        return None
    return n.title() if (n.isupper() or n.islower()) else n


def remember_country(db: Session, name: str | None) -> None:
    n = clean_country(name)
    if not n:
        return
    if not db.scalar(select(Country).where(func.lower(Country.name) == n.lower())):
        from .routers.dashboard import region_of
        db.add(Country(name=n, region=region_of(n, {})))
