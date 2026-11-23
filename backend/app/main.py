import logging

from fastapi import FastAPI
from sqlalchemy import select

from . import audit  # noqa: F401  (registers the audit-log listeners)
from .db import Base, SessionLocal, engine
from .migrate import upgrade
from . import invoice_rules
from .models import Client, Country, PaymentMethod
from . import scheduler
from .routers import auth, credit, dashboard, money, my, refs, users, work

log = logging.getLogger("ebfi")

app = FastAPI(title="EBFI Ops", docs_url="/api/docs", openapi_url="/api/openapi.json")
for router in (auth.r, users.r, refs.r, work.r, money.r, dashboard.r, my.r, credit.r):
    app.include_router(router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}


DEFAULT_METHODS = ["Bank", "Revolut", "Wise", "PayPal", "Cash"]


@app.on_event("startup")
def startup():
    # Tables are created if missing; new columns of existing tables are added by app/migrate.py.
    Base.metadata.create_all(engine)
    upgrade(engine)
    with SessionLocal() as db:
        try:  # a data fix must never stop the app from starting
            n = work.fill_from_dates(db)
            if n:
                log.warning("Filled MD from dates in %s lines", n)
        except Exception:
            db.rollback()
            log.exception("fill_from_dates failed, skipped")
        # each client gets its Word invoice template once, by name; the admin can change it in «Справочники → Клиент»
        for c in db.scalars(select(Client).where(Client.invoice_template.is_(None))):
            c.invoice_template = invoice_rules.guess(c.name) or ""
        db.commit()
        if not db.scalar(select(PaymentMethod).limit(1)):
            db.add_all(PaymentMethod(name=n, rko_percent=0, rko_fixed_inr=0) for n in DEFAULT_METHODS)
            db.commit()
    scheduler.start()
