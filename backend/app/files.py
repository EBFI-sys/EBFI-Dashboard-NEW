"""Job folders and invoice files on OneDrive: what goes where (see app/sharepoint.py for the layout)."""
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import sharepoint as sp
from .dates import format_dates, parse_dates
from .models import Client, Inspector, InspectorInvoice, Job, SalesInvoice, Setting

log = logging.getLogger("ebfi.files")
NUM = re.compile(r"^(\d{2})\.(\d{2})-(\d{1,4})$")


def _first_name(name: str | None) -> str:
    return (name or "").split()[0] if name else ""


def job_folder_name(job: Job, db: Session) -> str:
    """«26.29-43 Swaminath Germany 17,18,19,20.11.2026», like the folders the team already makes by hand."""
    lines = [l for l in job.lines if not l.deleted]
    ids = list(dict.fromkeys(l.inspector_id for l in lines if l.inspector_id))
    names = {i.id: i.name for i in db.scalars(select(Inspector).where(Inspector.id.in_(ids)))} if ids else {}
    who = " & ".join(_first_name(names.get(i)) for i in ids if names.get(i))
    dates = sorted({d for l in lines for d in parse_dates(l.dates_text, l.month)})
    when = format_dates(dates) if dates else ""
    return sp.clean(" ".join(x for x in (job.job_number, who, job.country or "", when) if x))


def _client_folder(g: "sp.Graph", job: Job, db: Session) -> dict:
    yy, code = NUM.match(job.job_number).group(1, 2)
    year = g.path_folder(f"Server 20{yy}")
    prefix = f"{yy}.{code}"
    for c in g.children(year["id"]):
        if "folder" in c and (c["name"] == prefix or c["name"].startswith(prefix + " ")):
            return c
    client = db.get(Client, job.client_id)
    label = (client.sp_folder or client.name) if client else ""
    return g.folder(year["id"], f"{prefix} {label}".strip())


def ensure_job_folder(db: Session, job: Job) -> None:
    """Create (or find, or rename) the job's folder with its two subfolders. Records any error on the job."""
    if not sp.enabled() or not NUM.match(job.job_number or ""):
        return
    try:
        g = sp.graph()
        name = job_folder_name(job, db)
        item = g.get(job.sp_folder_id) if job.sp_folder_id else None
        found = False
        if not item:
            parent = _client_folder(g, job, db)
            item = next((c for c in g.children(parent["id"]) if "folder" in c and
                         (c["name"] == job.job_number or c["name"].startswith(job.job_number + " "))), None)
            found = item is not None  # a folder the team made by hand: linked as it is, renamed only on later changes
            item = item or g.folder(parent["id"], name)
        if item["name"] != name and not found:
            item = g.update(item["id"], name=name)
        for sub in sp.JOB_SUBFOLDERS:
            g.folder(item["id"], sub)
        job.sp_folder_id, job.sp_folder_url, job.sp_error = item["id"], item.get("webUrl"), None
    except Exception as e:  # noqa: BLE001 - files never block the job itself
        log.warning("job folder %s: %s", job.job_number, e)
        job.sp_error = f"Папка на сервере не создана: {e}"
    db.commit()


def archive_job_folder(db: Session, job: Job) -> None:
    """A deleted or returned job: its folder goes to Server YYYY/_Cancelled (files are never deleted)."""
    if not sp.enabled() or not job.sp_folder_id:
        return
    try:
        g = sp.graph()
        yy = job.job_number[:2]
        dest = g.path_folder(f"Server 20{yy}", sp.CANCELLED)
        g.update(job.sp_folder_id, parent_id=dest["id"])
    except Exception as e:  # noqa: BLE001
        log.warning("archive %s: %s", job.job_number, e)


def job_files(job: Job) -> dict:
    g = sp.graph()
    out = {}
    for sub in g.children(job.sp_folder_id):
        if "folder" in sub:
            out[sub["name"]] = {"id": sub["id"], "url": sub.get("webUrl"), "files": [
                {"name": f["name"], "size": f.get("size"), "url": f.get("webUrl"), "modified": f.get("lastModifiedDateTime"),
                 "by": ((f.get("lastModifiedBy") or {}).get("user") or {}).get("displayName"), "folder": "folder" in f}
                for f in sorted(g.children(sub["id"]), key=lambda x: x["name"].lower())]}
    return out


def upload_to_job(job: Job, subfolder: str, name: str, content: bytes, mime: str | None) -> dict:
    if subfolder not in sp.JOB_SUBFOLDERS:
        raise ValueError("Папка: Inspection Documents или Inspection Deliverables")
    g = sp.graph()
    target = g.folder(job.sp_folder_id, subfolder)
    return g.upload(target["id"], name, content, mime)


def _ext(filename: str) -> str:
    m = re.search(r"(\.[A-Za-z0-9]{1,5})$", filename or "")
    return m.group(1).lower() if m else ".pdf"


def upload_incoming(db: Session, inv: InspectorInvoice, filename: str, content: bytes, mime: str | None) -> dict:
    """Incoming Invoice Register / YYYY-MM / <inspector> / «<jobs> — <invoice no>.pdf»."""
    g = sp.graph()
    insp = db.get(Inspector, inv.inspector_id)
    month = (inv.invoice_date.strftime("%Y-%m") if inv.invoice_date else "Без даты")
    folder = g.path_folder(sp.INCOMING, month, insp.name if insp else "Без инспектора")
    jobs = ", ".join(j.job_number for j in inv.jobs) or "без работы"
    item = g.upload(folder["id"], f"{jobs} — {inv.number or 'счёт ' + str(inv.id)}{_ext(filename)}", content, mime)
    inv.sp_file_id, inv.sp_file_url = item.get("id"), item.get("webUrl")
    return item


def upload_outgoing(db: Session, inv: SalesInvoice, filename: str, content: bytes, mime: str | None) -> dict:
    """Outgoing Invoice Register / YYYY-MM / <client> / «EBFI-2627-300.pdf»."""
    g = sp.graph()
    client = db.get(Client, inv.client_id)
    month = inv.date.strftime("%Y-%m") if inv.date else "Без даты"
    folder = g.path_folder(sp.OUTGOING, month, client.name if client else "Без клиента")
    item = g.upload(folder["id"], f"{inv.number}{_ext(filename)}", content, mime)
    inv.sp_file_id, inv.sp_file_url = item.get("id"), item.get("webUrl")
    return item


def server_max(yy: str, code: str) -> int:
    """Highest job number of this client code in Server 20YY, read live (folders made by hand count too)."""
    if not sp.enabled():
        return 0
    try:
        g = sp.graph()
        year = g.item(f"{sp.settings.ms_root}/Server 20{yy}")
        if not year:
            return 0
        best, prefix = 0, f"{yy}.{code}"
        for parent in g.children(year["id"]):
            if "folder" in parent and (parent["name"] == prefix or parent["name"].startswith(prefix + " ")
                                       or parent["name"] == sp.CANCELLED):
                for c in g.children(parent["id"]):
                    m = re.match(rf"^{re.escape(prefix)}-(\d{{1,4}})\b", c["name"])
                    if m:
                        best = max(best, int(m[1]))
        return best
    except Exception as e:  # noqa: BLE001 - the number still comes from the ERP's own queue
        log.warning("server_max %s.%s: %s", yy, code, e)
        return 0


def sync_numbers(db: Session) -> dict[str, int]:
    """Read the job numbers already used on the server (folder names «26.29-43 …») into the number queues."""
    g = sp.graph()
    root = g.item(sp.settings.ms_root)
    found: dict[str, int] = {}
    for year in g.children(root["id"]) if root else []:
        if "folder" not in year or not re.fullmatch(r"Server 20\d\d", year["name"]):
            continue
        for client in g.children(year["id"]):
            if "folder" not in client:
                continue
            for job in g.children(client["id"]):
                m = re.match(r"^(\d{2})\.(\d{2})-(\d{1,4})\b", job["name"])
                if m:
                    k = f"jobseq:{m[1]}:{m[2]}"
                    found[k] = max(found.get(k, 0), int(m[3]))
    for k, v in found.items():
        row = db.get(Setting, k) or Setting(key=k, value="0")
        if not row.value.isdigit() or int(row.value) < v:
            row.value = str(v)
        db.add(row)
    db.commit()
    return found
