"""Merge spelling variants of the same inspector name.

"ZHANG XINYU" / "Zhang Xinyu", "Andriy Melnychuk" / "Andrii Melnychuk", "Mohammad Maki Pour" / "Mohammad Makipour",
"Chineme Ofoma" / "Chineme Christian Ofoma", "Ioan_Mihut" / "Ioan Mihut" become one inspector.
Short tokens (4 letters or less) must match exactly, so "Wang Ming" and "Wang Ning" stay apart.
"""
import re
from collections import Counter, defaultdict


def token_key(t: str) -> str:
    t = t.lower()
    t = t.replace("y", "i").replace("kh", "h").replace("ph", "f").replace("w", "v")
    t = re.sub(r"(.)\1+", r"\1", t)  # double letters
    return t


def tokens(name: str) -> list[str]:
    s = re.sub(r"[_\-.,()/]+", " ", name)
    s = re.sub(r"[^A-Za-zÀ-ÿ\s]", "", s)
    return [token_key(t) for t in s.split() if t]


def _lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _tok_eq(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) <= 4:
        return False
    if min(len(a), len(b)) >= 6 and (a.startswith(b) or b.startswith(a)) and abs(len(a) - len(b)) <= 1:
        return True
    return min(len(a), len(b)) >= 7 and _lev(a, b) <= 1


def same_person(a: list[str], b: list[str]) -> bool:
    if not a or not b:
        return False
    if "".join(a) == "".join(b) or "".join(sorted(a)) == "".join(sorted(b)):
        return True
    if len(a) == len(b) and len(a) >= 2:
        if all(_tok_eq(x, y) for x, y in zip(a, b)) or all(_tok_eq(x, y) for x, y in zip(sorted(a), sorted(b))):
            return True
    small, big = (a, b) if len(a) < len(b) else (b, a)
    if len(small) >= 2 and len(big) > len(small) and all(any(_tok_eq(s, t) for t in big) for s in small):
        return True
    return False


def canonical_groups(counts: Counter) -> dict[str, str]:
    """Map every spelling to one canonical name (the most frequent, nicely cased variant)."""
    names = list(counts)
    toks = {n: tokens(n) for n in names}
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # a cell naming several people ("Yurii Kondrus / Masud") is never merged into one of them
    multi = [n for n in names if len(toks[n]) >= 2 and "/" not in n]
    for i, a in enumerate(multi):
        for b in multi[i + 1:]:
            if same_person(toks[a], toks[b]):
                parent[find(a)] = find(b)
    # single-word names: attach only when exactly one multi-word person starts with that word
    for n in names:
        if len(toks[n]) == 1:
            hits = {find(m) for m in multi if _tok_eq(toks[m][0], toks[n][0])}
            if len(hits) == 1:
                parent[find(n)] = hits.pop()
    groups = defaultdict(list)
    for n in names:
        groups[find(n)].append(n)

    def nice(n):  # prefer the fullest spelling, then the most frequent
        return (len(toks[n]), counts[n], n != n.upper(), len(n))

    out = {}
    for members in groups.values():
        best = max(members, key=nice)
        best = re.sub(r"\s+", " ", best.replace("_", " ")).strip()
        # "ZHANG XINYU" -> "Zhang Xinyu", but abbreviations ("ESS", "JK", "(DAIS)", "T.R.") stay as written
        words = best.split()
        shout = best.isupper() and len(words) > 1  # the whole name in capitals: "REN MINGYONG"
        best = " ".join(w.capitalize() if w.isalpha() and (shout or (len(w) > 3 and (w.islower() or w.isupper()))) else w
                        for w in words)
        for m in members:
            out[m] = best
    return out
