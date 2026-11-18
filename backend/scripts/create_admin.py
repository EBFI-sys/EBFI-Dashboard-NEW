"""Create the first admin and the team accounts.

    docker compose exec api python -m scripts.create_admin

Prints one temporary password per user; each person changes it after the first login.
"""
import secrets

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password

TEAM = [
    # name, email, initials, role, old «Чья» letters
    ("Maksym Bykhovchenko", "m.bykhovchenko@ebfi.net", "MB", "admin", "М"),
    ("Liutsina Rafikova", "liutsina.rafikova@ebfi.in", "LR", "manager", "Лю"),
    ("Svetlana Vixninsh", "s.vixninsh@ebfi.in", "SV", "manager", "С"),
    ("Leonid Matveev", "l.matveev@ebfi.in", "LM", "manager", "Л"),
]
ARCHIVED = ["Д", "А", "Т"]  # former coordinators: kept for history, cannot log in


def main():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for name, email, ini, role, legacy in TEAM:
            u = db.scalar(select(User).where(User.initials == ini))
            if u:
                print(f"{ini}: уже есть ({u.email})")
                continue
            pw = secrets.token_urlsafe(9)
            db.add(User(name=name, email=email, initials=ini, role=role, legacy_letters=legacy,
                        password_hash=hash_password(pw)))
            print(f"{ini}  {email:35s}  временный пароль: {pw}")
        for letter in ARCHIVED:
            if not db.scalar(select(User).where(User.initials == letter)):
                db.add(User(name=f"Архив «{letter}»", email=f"archived-{ord(letter)}@local", initials=letter,
                            role="archived", active=False, legacy_letters=letter))
        db.commit()


if __name__ == "__main__":
    main()
