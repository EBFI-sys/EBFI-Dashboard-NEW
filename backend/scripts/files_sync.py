"""OneDrive link-up, run once after connecting Microsoft 365 (and again any time, it is safe to repeat).

    docker compose exec api python -m scripts.files_sync --check            # connection test
    docker compose exec api python -m scripts.files_sync --numbers          # job-number queues from server folders
    docker compose exec api python -m scripts.files_sync --link             # folders for jobs from November 2026 on
"""
import argparse

from sqlalchemy import select

from app import files, sharepoint
from app.config import settings
from app.db import SessionLocal
from app.models import Job, JobLine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--numbers", action="store_true")
    ap.add_argument("--link", action="store_true")
    ap.add_argument("--since", default="2026-11", help="только работы с этого месяца (ГГГГ-ММ)")
    a = ap.parse_args()
    if not sharepoint.enabled():
        raise SystemExit("Нет настроек Microsoft 365: заполните MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET, MS_SITE_ID в .env")
    g = sharepoint.graph()
    if a.check or not (a.numbers or a.link):
        root = g.item(settings.ms_root)
        print("Связь с OneDrive: OK")
        print("Папка", settings.ms_root, ":", root.get("webUrl") if root else "не найдена — будет создана")
        if root:
            print("Внутри:", ", ".join(c["name"] for c in g.children(root["id"])))
    with SessionLocal() as db:
        if a.numbers:
            found = files.sync_numbers(db)
            print(f"Очереди номеров по папкам на сервере: {len(found)}")
            for k, v in sorted(found.items()):
                print(f"  {k[7:].replace(':', '.')}-{v}")
        if a.link:
            jobs = [j for j in db.scalars(select(Job).where(Job.deleted.is_(False)))
                    if files.NUM.match(j.job_number or "") and
                    any(not l.deleted and l.month >= a.since for l in j.lines)]
            ok = bad = 0
            for j in sorted(jobs, key=lambda x: x.job_number):
                files.ensure_job_folder(db, j)
                if j.sp_error:
                    bad += 1
                    print("  ✗", j.job_number, j.sp_error)
                else:
                    ok += 1
            print(f"Папки работ: готово {ok}, ошибок {bad}")


if __name__ == "__main__":
    main()
