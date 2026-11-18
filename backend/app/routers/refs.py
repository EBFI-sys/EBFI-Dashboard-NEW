from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..calc import DEFAULTS, Context, get_setting, snapshot_month
from ..db import get_db
from ..models import Client, Country, FxRate, Inspector, MonthClose, PaymentMethod, Setting, User, Vendor
from ..security import decrypt, encrypt, need
from .crud import make_crud, to_dict

r = APIRouter()

r.include_router(make_crud(Country, "/countries", order_by=Country.name, search=["name"]))
r.include_router(make_crud(Vendor, "/vendors", order_by=Vendor.name, search=["name", "country"]))
r.include_router(make_crud(PaymentMethod, "/payment-methods", order_by=PaymentMethod.name))
r.include_router(make_crud(Client, "/clients", order_by=Client.name, search=["name", "legal_name", "gstin"]))
r.include_router(make_crud(FxRate, "/fx-rates", order_by=[FxRate.month.desc(), FxRate.currency],
                           write_right="settings"))


def _insp_ser(o: Inspector, db):
    d = to_dict(o, {"bank_details_enc"})
    d["bank_details"] = decrypt(o.bank_details_enc)
    return d


def _insp_save(o: Inspector, data: dict, db, user, created):
    if "bank_details" in data:
        o.bank_details_enc = encrypt(data["bank_details"])


r.include_router(make_crud(Inspector, "/inspectors", order_by=Inspector.name, search=["name", "country", "specialization"],
                           serialize=_insp_ser, before_save=_insp_save))


# ---------------------------------------------------------------- settings and month close
@r.get("/settings")
def get_settings(db: Session = Depends(get_db), _=Depends(need("read"))):
    return {k: get_setting(db, k) for k in DEFAULTS}


@r.put("/settings")
def put_settings(data: dict, db: Session = Depends(get_db), _=Depends(need("settings"))):
    for k, v in data.items():
        if k not in DEFAULTS:
            continue
        row = db.get(Setting, k) or Setting(key=k, value=str(v))
        row.value = str(v)
        db.add(row)
    db.commit()
    return {k: get_setting(db, k) for k in DEFAULTS}


@r.get("/months")
def months(db: Session = Depends(get_db), _=Depends(need("read"))):
    names = {u.id: u.initials for u in db.scalars(select(User))}
    return [{"month": m.month, "closed_at": m.closed_at.isoformat(), "closed_by": names.get(m.closed_by)}
            for m in db.scalars(select(MonthClose).order_by(MonthClose.month.desc()))]


@r.post("/months/{month}/close")
def close_month(month: str, db: Session = Depends(get_db), user: User = Depends(need("close_month"))):
    if db.get(MonthClose, month):
        raise HTTPException(400, "Месяц уже закрыт")
    ctx = Context(db)
    try:
        n = snapshot_month(db, month, ctx)
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    db.add(MonthClose(month=month, closed_by=user.id))
    db.commit()
    return {"month": month, "lines_frozen": n}


@r.post("/months/{month}/reopen")
def reopen_month(month: str, db: Session = Depends(get_db), _=Depends(need("users"))):
    m = db.get(MonthClose, month)
    if not m:
        raise HTTPException(404, "Месяц не закрыт")
    db.delete(m)
    db.commit()
    return {"ok": True}
