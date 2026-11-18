from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..calc import Context, compute_line
from ..db import get_db
from ..models import Client, Country, Inspector, InspectorInvoice, Job, JobLine, Request, SalesInvoice, TdsEntry, User
from ..security import need

r = APIRouter()

EU = {"Germany", "Italy", "France", "UK", "Sweden", "Netherlands", "Switzerland", "Belgium", "Spain", "Finland", "Bulgaria",
      "Austria", "Denmark", "Hungary", "Czech", "Czech Republic", "Poland", "Portugal", "Estonia", "Bosnia", "Norway", "Greece",
      "Romania", "Latvia", "Slovenia", "Ireland", "Croatia", "Serbia", "Slovakia", "Lithuania", "Turkey"}
CIS = {"Russia", "Ukraine", "Uzbekistan", "Kazakhstan", "Belarus", "Azerbaijan", "Georgia", "Armenia"}
AM = {"Mexico", "Argentina", "Brazil", "Colombia", "Canada", "Chile", "Peru"}
ME = {"Saudi Arabia", "UAE", "Qatar", "Oman", "Israel", "Lebanon", "Kuwait", "Bahrain", "Iraq"}


def region_of(country: str | None, table: dict[str, str]) -> str:
    c = (country or "").strip()
    if c in table:
        return table[c]
    if c == "China" or c.startswith("China"):
        return "China"
    if c in ("India", "USA"):
        return c
    if c in EU:
        return "Europe"
    if c in CIS:
        return "Russia & CIS"
    if c in AM:
        return "Latin America & Canada"
    if c in ME:
        return "Middle East"
    return "Unspecified" if not c else "Asia-Pacific & other"


def in_period(month: str, period: str) -> bool:
    if not period or period == "all":
        return True
    if period == "fy":  # current Indian financial year
        t = date.today()
        start = date(t.year if t.month >= 4 else t.year - 1, 4, 1).strftime("%Y-%m")
        return month >= start
    if period == "last3":
        t = date.today()
        y, m = t.year, t.month - 2
        if m <= 0:
            y, m = y - 1, m + 12
        return month >= f"{y}-{m:02d}"
    if len(period) == 4:
        return month.startswith(period)
    return month == period


@r.get("/dashboard")
def dashboard(period: str = "all", client_id: int | None = None, region: str | None = None,
              owner_id: int | None = None, currency: str = "INR",
              db: Session = Depends(get_db), _=Depends(need("read"))):
    ctx = Context(db)
    regions = {c.name: c.region for c in db.scalars(select(Country))}
    users = {u.id: u for u in db.scalars(select(User))}
    clients = {c.id: c for c in db.scalars(select(Client))}
    inspectors = {i.id: i.name for i in db.scalars(select(Inspector))}

    def conv(inr: float | None, month: str) -> float:
        if inr is None:
            return 0.0
        if currency == "INR":
            return inr
        fx = ctx.fx(month, currency)
        return inr / float(fx.rate) if fx.rate else 0.0

    rows = []
    provisional_months = set()
    for line in db.scalars(select(JobLine).where(JobLine.deleted.is_(False))):
        job = line.job
        if job.deleted or not in_period(line.month, period):
            continue
        if client_id and job.client_id != client_id:
            continue
        reg = region_of(job.country, regions)
        if region and reg != region:
            continue
        if owner_id and job.owner_id != owner_id:
            continue
        c = compute_line(line, job, ctx)
        if c["fx_provisional"] and line.currency != "INR":
            provisional_months.add(line.month)
        rows.append({
            "line_id": line.id, "job_id": job.id, "job_number": job.job_number, "month": line.month,
            "client": clients[job.client_id].name if job.client_id in clients else "?",
            "country": job.country, "region": reg, "owner": users[job.owner_id].initials if job.owner_id in users else "—",
            "inspector": inspectors.get(line.inspector_id, "—"), "status": job.status,
            "md": c["man_days"], "revenue": conv(c["base_inr"], line.month), "net": conv(c["net_inr"], line.month),
            "cash_in": conv(c["cash_in_inr"], line.month), "gst": conv(c["gst_inr"], line.month),
            "tds": conv(c["tds_inr"], line.month), "cost": conv(c["cost_inr"], line.month),
        })

    def group(key):
        g = defaultdict(lambda: {"revenue": 0.0, "net": 0.0, "md": 0.0, "jobs": set(), "loss_lines": 0})
        for x in rows:
            a = g[x[key]]
            a["revenue"] += x["revenue"]; a["net"] += x["net"]; a["md"] += x["md"]; a["jobs"].add(x["job_id"])
            a["loss_lines"] += x["net"] < 0
        out = []
        for k, a in g.items():
            out.append({key: k, "revenue": round(a["revenue"], 2), "net": round(a["net"], 2), "md": round(a["md"], 1),
                        "jobs": len(a["jobs"]), "loss_lines": a["loss_lines"],
                        "margin": round(a["net"] / a["revenue"] * 100, 1) if a["revenue"] else None,
                        "net_per_md": round(a["net"] / a["md"]) if a["md"] else None})
        return sorted(out, key=lambda z: -z["revenue"])

    revenue = sum(x["revenue"] for x in rows)
    net = sum(x["net"] for x in rows)
    kpi = {
        "revenue": round(revenue, 2), "net": round(net, 2), "margin": round(net / revenue * 100, 1) if revenue else None,
        "cash_in": round(sum(x["cash_in"] for x in rows), 2), "gst": round(sum(x["gst"] for x in rows), 2),
        "tds": round(sum(x["tds"] for x in rows), 2), "md": round(sum(x["md"] for x in rows), 1),
        "jobs": len({x["job_id"] for x in rows}),
        "active_jobs": len({x["job_id"] for x in rows if x["status"] in ("В работе", "Пауза")}),
    }

    # requests funnel (period by received date, client and region filters apply)
    reqs = []
    for q in db.scalars(select(Request).where(Request.deleted.is_(False))):
        m = q.received_date.strftime("%Y-%m") if q.received_date else None
        if m and not in_period(m, period):
            continue
        if client_id and q.client_id != client_id:
            continue
        if region and region_of(q.country, regions) != region:
            continue
        if owner_id and q.owner_id != owner_id:
            continue
        reqs.append(q)
    status_counts = defaultdict(int)
    for q in reqs:
        status_counts[q.status] += 1
    done, cancelled = status_counts["Выполнено"], status_counts["Отмена"]

    # receivables (client filter only)
    sales = [s for s in db.scalars(select(SalesInvoice).where(SalesInvoice.deleted.is_(False)))
             if not client_id or s.client_id == client_id]
    sales_cur = defaultdict(lambda: {"count": 0, "invoiced": 0.0, "received": 0.0, "outstanding": 0.0})
    for s in sales:
        a = sales_cur[s.currency]
        a["count"] += 1
        a["invoiced"] += float(s.amount)
        a["received"] += float(s.received_amount or 0)
        if s.status != "Paid":
            a["outstanding"] += float(s.amount) - float(s.received_amount or 0)
    tds = list(db.scalars(select(TdsEntry)))

    # payables
    pay = list(db.scalars(select(InspectorInvoice).where(InspectorInvoice.deleted.is_(False))))
    pay_cur = defaultdict(lambda: {"paid": 0.0, "to_pay": 0.0, "open": 0})
    for p in pay:
        a = pay_cur[p.currency]
        if p.paid:
            a["paid"] += float(p.amount)
        else:
            a["to_pay"] += float(p.amount)
            a["open"] += 1

    monthly = group("month")
    monthly.sort(key=lambda z: z["month"])
    return {
        "currency": currency,
        "provisional_months": sorted(provisional_months),
        "kpi": kpi,
        "monthly": monthly,
        "top_clients": group("client")[:10],
        "regions": group("region"),
        "owners": group("owner"),
        "inspectors": [z for z in group("inspector") if z["inspector"] != "—"],
        "loss_lines": sorted([x for x in rows if x["net"] < 0], key=lambda z: z["net"])[:200],
        "active": [x for x in rows if x["status"] in ("В работе", "Пауза")],
        "requests": {
            "total": len(reqs), "by_status": dict(status_counts), "done": done, "cancelled": cancelled,
            "conversion": round(done / len(reqs) * 100, 1) if reqs else None,
            "win_rate": round(done / (done + cancelled) * 100, 1) if done + cancelled else None,
        },
        "sales_by_currency": [{"currency": k, **{kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()}}
                              for k, v in sales_cur.items()],
        "tds": {"expected": round(sum(float(t.amount_inr) for t in tds if t.status != "Зачтён"), 2),
                "credited": round(sum(float(t.amount_inr) for t in tds if t.status == "Зачтён"), 2)},
        "payables_by_currency": [{"currency": k, **{kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()}}
                                 for k, v in pay_cur.items()],
    }
