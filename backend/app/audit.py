"""Writes who changed what into audit_log on every flush."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from .db import current_user_id
from .models import AuditLog

SKIP = {"updated_at", "created_at", "password_hash", "totp_secret", "failed_logins", "locked_until"}
MASK = {"bank_details_enc"}


def _v(x):
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, (date, datetime)):
        return x.isoformat()
    return x


@event.listens_for(Session, "before_flush")
def _collect(session: Session, ctx, instances):
    pending = session.info.setdefault("audit_pending", [])
    for obj in session.new:
        if isinstance(obj, AuditLog):
            continue
        pending.append(("insert", obj, None))
    for obj in session.dirty:
        if isinstance(obj, AuditLog) or not session.is_modified(obj):
            continue
        changes = {}
        for attr in inspect(obj).mapper.column_attrs:
            key = attr.key
            if key in SKIP:
                continue
            hist = inspect(obj).attrs[key].history
            if hist.has_changes():
                old = hist.deleted[0] if hist.deleted else None
                new = hist.added[0] if hist.added else None
                if key in MASK:
                    old, new = "***", "*** (изменено)"
                changes[key] = [_v(old), _v(new)]
        if changes:
            action = "delete" if changes.get("deleted") == [False, True] else "update"
            pending.append((action, obj, changes))
    for obj in session.deleted:
        if not isinstance(obj, AuditLog):
            pending.append(("delete", obj, {}))


@event.listens_for(Session, "after_flush")
def _write(session: Session, ctx):
    pending = session.info.pop("audit_pending", [])
    for action, obj, changes in pending:
        if changes is None:  # insert: record the new values
            changes = {}
            for attr in inspect(obj).mapper.column_attrs:
                if attr.key in SKIP:
                    continue
                val = getattr(obj, attr.key)
                if val is not None:
                    changes[attr.key] = "***" if attr.key in MASK else _v(val)
        rid = getattr(obj, "id", None)
        session.connection().execute(AuditLog.__table__.insert().values(
            user_id=session.info.get("user_id") or current_user_id.get(), table_name=obj.__tablename__,
            record_id=rid if isinstance(rid, int) else None, action=action, changes=changes))
