import logging

from fastapi import FastAPI
from sqlalchemy import select

from . import audit  # noqa: F401  (registers the audit-log listeners)
from .db import Base, SessionLocal, engine
from .models import Country, PaymentMethod
from .routers import auth, dashboard, money, refs, users, work

log = logging.getLogger("ebfi")

app = FastAPI(title="EBFI Ops", docs_url="/api/docs", openapi_url="/api/openapi.json")
for router in (auth.r, users.r, refs.r, work.r, money.r, dashboard.r):
    app.include_router(router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}


DEFAULT_METHODS = ["Bank", "Revolut", "Wise", "PayPal", "Cash"]


@app.on_event("startup")
def startup():
    # Tables are created if missing. Schema changes after launch go through Alembic migrations.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(PaymentMethod).limit(1)):
            db.add_all(PaymentMethod(name=n, rko_percent=0, rko_fixed_inr=0) for n in DEFAULT_METHODS)
            db.commit()
