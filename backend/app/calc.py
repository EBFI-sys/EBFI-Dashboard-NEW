"""P&L arithmetic for one job line — the formulas agreed in the spec (18 Nov 2026).

    B          = (quantity × client rate + client overtime) × FX            invoice base, INR
    GST        = B × gst_rate        (Indian clients only, pass-through, not revenue)
    TDS        = B × tds_rate        (Indian clients only, goes to the TDS register, not a cost)
    WHT        = B × wht_rate        (clients marked «WHT», 5%: withheld by the client, not a cost either)
    Cash in    = B + GST − TDS − WHT
    Admin      = B × admin_rate
    Contractor = (quantity × inspector rate + inspector overtime) × FX of the inspector currency
                 (the inspector may be paid in another currency than the client is billed in)
    RKO        = payment-method fee (0 until the payment-method list is filled)
    Net profit = B − Admin − Contractor − RKO
    Margin     = Net profit ÷ B
"""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Client, FxRate, Job, JobLine, MonthClose, PaymentMethod, Setting

DEFAULTS = {"gst_rate": "0.18", "tds_rate": "0.10", "admin_rate": "0.18", "company_state": "Maharashtra", "sales_invoice_last": "", "wht_rate": "0.05"}
D0 = Decimal("0")


def get_setting(db: Session, key: str) -> str:
    row = db.get(Setting, key)
    return row.value if row else DEFAULTS[key]


@dataclass
class Fx:
    rate: Decimal | None
    provisional: bool
    source_month: str | None


class Context:
    """Caches settings, FX rates and closed months for one request."""

    def __init__(self, db: Session):
        self.db = db
        self.gst = Decimal(get_setting(db, "gst_rate"))
        self.tds = Decimal(get_setting(db, "tds_rate"))
        self.admin = Decimal(get_setting(db, "admin_rate"))
        self.wht = Decimal(get_setting(db, "wht_rate"))
        self.rates: dict[tuple[str, str], Decimal] = {
            (r.month, r.currency): Decimal(r.rate) for r in db.scalars(select(FxRate))
        }
        self.closed = {m.month for m in db.scalars(select(MonthClose))}
        self.methods = {p.id: p for p in db.scalars(select(PaymentMethod))}
        self._clients: dict[int, Client] = {}

    def client(self, client_id: int) -> Client | None:
        if client_id not in self._clients:
            self._clients[client_id] = self.db.get(Client, client_id)
        return self._clients[client_id]

    def fx(self, month: str, currency: str) -> Fx:
        if currency == "INR":
            return Fx(Decimal(1), False, month)
        if (month, currency) in self.rates:
            return Fx(self.rates[(month, currency)], False, month)
        earlier = sorted(m for (m, c) in self.rates if c == currency and m < month)
        if earlier:  # provisional: last fixed month before this one
            return Fx(self.rates[(earlier[-1], currency)], True, earlier[-1])
        return Fx(None, True, None)


def _f(x) -> float:
    return float(round(Decimal(x), 2))


def compute_line(line: JobLine, job: Job, ctx: Context) -> dict:
    """Return the computed P&L figures for one line (all INR)."""
    closed = line.month in ctx.closed and line.snap_fx is not None
    icur = line.inspector_currency or line.currency
    if closed:
        fx = Fx(Decimal(line.snap_fx), False, line.month)
        fxi = Fx(Decimal(line.snap_fx_insp), False, line.month) if line.snap_fx_insp is not None else fx
        gst_r, tds_r, adm_r = Decimal(line.snap_gst), Decimal(line.snap_tds), Decimal(line.snap_admin)
        indian = bool(line.snap_indian)
        wht_r = Decimal(line.snap_wht or 0)
    else:
        fx = ctx.fx(line.month, line.currency)
        fxi = ctx.fx(line.month, icur)
        gst_r, tds_r, adm_r = ctx.gst, ctx.tds, ctx.admin
        client = ctx.client(job.client_id)
        indian = bool(client and client.is_indian)
        wht_r = ctx.wht if client and client.wht else D0

    qty = Decimal(line.quantity or 0)
    amount_cur = qty * Decimal(line.client_rate or 0) + Decimal(line.overtime_client or 0)
    sub_cur = D0 if line.no_subcontractor else qty * Decimal(line.inspector_rate or 0) + Decimal(line.overtime_inspector or 0)
    out = {
        "amount_currency": _f(amount_cur),
        "cost_currency": _f(sub_cur),
        "inspector_currency": icur,
        "fx_insp": float(fxi.rate) if fxi.rate is not None else None,
        "fx": float(fx.rate) if fx.rate is not None else None,
        "fx_provisional": fx.provisional or (icur != line.currency and fxi.provisional),
        "fx_source_month": fx.source_month,
        "is_indian": indian,
        "man_days": _f(qty) if line.unit == "day" else 0.0,
        "closed": closed,
    }
    if fx.rate is None or fxi.rate is None:  # no rate for this currency at all yet
        out.update(base_inr=None, gst_inr=None, tds_inr=None, wht_inr=None, cash_in_inr=None, admin_inr=None,
                   cost_inr=None, rko_inr=None, net_inr=None, margin=None)
        return out

    b = amount_cur * fx.rate
    sub = sub_cur * fxi.rate
    gst = b * gst_r if indian else D0
    tds = b * tds_r if indian else D0
    wht = b * wht_r
    admin = b * adm_r
    if closed and line.snap_rko_inr is not None:
        rko = Decimal(line.snap_rko_inr)
    elif line.rko_override_inr is not None:
        rko = Decimal(line.rko_override_inr)
    else:
        pm = ctx.methods.get(line.payment_method_id) if line.payment_method_id else None
        rko = (sub * Decimal(pm.rko_percent or 0) / 100 + Decimal(pm.rko_fixed_inr or 0)) if pm and sub else D0
    net = b - admin - sub - rko
    out.update(
        base_inr=_f(b), gst_inr=_f(gst), tds_inr=_f(tds), wht_inr=_f(wht), cash_in_inr=_f(b + gst - tds - wht),
        admin_inr=_f(admin), cost_inr=_f(sub), rko_inr=_f(rko), net_inr=_f(net),
        margin=float(round(net / b * 100, 1)) if b else None,
    )
    return out


def snapshot_month(db: Session, month: str, ctx: Context) -> int:
    """Freeze FX and tax rates into every line of the month. Returns the number of lines."""
    n = 0
    for line in db.scalars(select(JobLine).where(JobLine.month == month, JobLine.deleted.is_(False))):
        job = db.get(Job, line.job_id)
        fx = ctx.fx(month, line.currency)
        if fx.rate is None or fx.provisional:
            raise ValueError(f"Нет зафиксированного курса {line.currency} за {month}")
        icur = line.inspector_currency or line.currency
        fxi = ctx.fx(month, icur)
        if fxi.rate is None or fxi.provisional:
            raise ValueError(f"Нет зафиксированного курса {icur} за {month}")
        client = ctx.client(job.client_id)
        live = compute_line(line, job, ctx)
        line.snap_fx = fx.rate
        line.snap_fx_insp = fxi.rate
        line.snap_gst, line.snap_tds, line.snap_admin = ctx.gst, ctx.tds, ctx.admin
        line.snap_indian = bool(client and client.is_indian)
        line.snap_wht = ctx.wht if client and client.wht else Decimal(0)
        line.snap_rko_inr = Decimal(str(live["rko_inr"] or 0))
        n += 1
    return n
