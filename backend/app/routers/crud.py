"""Generic list / get / create / update / soft-delete endpoints for simple tables."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Text, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import need

READONLY = {"id", "created_at", "updated_at", "deleted"}


def to_dict(obj, hide: set[str] = frozenset()) -> dict:
    out = {}
    for col in obj.__table__.columns:
        if col.key in hide:
            continue
        v = getattr(obj, col.key)
        if isinstance(v, Decimal):
            v = float(v)
        elif isinstance(v, (date, datetime)):
            v = v.isoformat()
        out[col.key] = v
    return out


def coerce(col, value):
    if value == "" or value is None:
        return None
    t = col.type
    try:
        if isinstance(t, Boolean):
            return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "да")
        if isinstance(t, Integer):
            return int(value)
        if isinstance(t, Numeric):
            return Decimal(str(value).replace(",", ".").replace(" ", ""))
        if isinstance(t, Date):
            return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
        if isinstance(t, (String, Text)):
            return str(value).strip()
    except (ValueError, InvalidOperation):
        raise HTTPException(422, f"Неверное значение в поле {col.key}: {value}")
    return value


def apply(obj, data: dict, extra_readonly: set[str] = frozenset()):
    cols = {c.key: c for c in obj.__table__.columns}
    for k, v in data.items():
        if k in READONLY or k in extra_readonly or k not in cols:
            continue
        val = coerce(cols[k], v)
        if val is None and not cols[k].nullable and cols[k].default is None:
            raise HTTPException(422, f"Поле {k} обязательно")
        setattr(obj, k, val)


def make_crud(model, prefix: str, *, order_by=None, search: list[str] = (), hide: set[str] = frozenset(),
              readonly: set[str] = frozenset(), write_right: str = "write",
              serialize: Callable | None = None, before_save: Callable | None = None,
              after_save: Callable | None = None, delete_right: str = "delete",
              before_delete: Callable | None = None) -> APIRouter:
    r = APIRouter(prefix=prefix)
    ser = serialize or (lambda o, db: to_dict(o, hide))
    has_deleted = hasattr(model, "deleted")

    @r.get("")
    def list_(request: Request, db: Session = Depends(get_db), user: User = Depends(need("read"))):
        stmt = select(model)
        if has_deleted:
            stmt = stmt.where(model.deleted.is_(False))
        cols = {c.key: c for c in model.__table__.columns}
        for k, v in request.query_params.items():
            if k == "q" and v and search:
                stmt = stmt.where(or_(*[getattr(model, s).ilike(f"%{v}%") for s in search]))
            elif k in cols and v != "":
                stmt = stmt.where(getattr(model, k) == coerce(cols[k], v))
        if order_by is not None:
            stmt = stmt.order_by(*order_by) if isinstance(order_by, (list, tuple)) else stmt.order_by(order_by)
        return [ser(o, db) for o in db.scalars(stmt.limit(10000))]

    @r.get("/{item_id}")
    def get_(item_id: int, db: Session = Depends(get_db), user: User = Depends(need("read"))):
        obj = db.get(model, item_id)
        if not obj or (has_deleted and obj.deleted):
            raise HTTPException(404, "Не найдено")
        return ser(obj, db)

    @r.post("")
    def create(data: dict, db: Session = Depends(get_db), user: User = Depends(need(write_right))):
        obj = model()
        apply(obj, data, readonly)
        if before_save:
            before_save(obj, data, db, user, True)
        db.add(obj)
        _commit(db)
        if after_save:
            after_save(obj, db)
            _commit(db)
        db.refresh(obj)
        return ser(obj, db)

    @r.patch("/{item_id}")
    def update(item_id: int, data: dict, db: Session = Depends(get_db), user: User = Depends(need(write_right))):
        obj = db.get(model, item_id)
        if not obj or (has_deleted and obj.deleted):
            raise HTTPException(404, "Не найдено")
        apply(obj, data, readonly)
        if before_save:
            before_save(obj, data, db, user, False)
        _commit(db)
        if after_save:
            after_save(obj, db)
            _commit(db)
        db.refresh(obj)
        return ser(obj, db)

    @r.delete("/{item_id}")
    def delete(item_id: int, db: Session = Depends(get_db), user: User = Depends(need(delete_right))):
        obj = db.get(model, item_id)
        if not obj:
            raise HTTPException(404, "Не найдено")
        if before_delete:
            before_delete(obj, db)
        if has_deleted:
            obj.deleted = True  # soft delete: the row stays in the database
        else:
            db.delete(obj)
        _commit(db)
        return {"ok": True}

    return r


def _commit(db: Session):
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        msg = str(e.orig).split("DETAIL:")[-1].strip() if e.orig else "конфликт данных"
        raise HTTPException(409, f"Такая запись уже есть или нарушена связь: {msg}")
