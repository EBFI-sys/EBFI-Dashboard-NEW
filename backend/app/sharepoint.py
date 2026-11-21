"""Files on Microsoft 365 (the admin's OneDrive, «My files → EBFI»), through Microsoft Graph.

The app signs in as itself (Entra app «EBFI ERP», permission Sites.Selected, write access to that one OneDrive only).
Layout it keeps:

    EBFI/
      Server 2026/
        26.29 TUV R QATAR/                                 client folder, found by its code «26.29 »
          26.29-43 Swaminath Germany 17,18,19,20.11.2026/  one folder per job, renamed when the job changes
            Inspection Documents/
            Inspection Deliverables/
        _Cancelled/                                        jobs deleted or sent back to requests
      Incoming Invoice Register/2026-11/<inspector>/<jobs> — <invoice no>.pdf     invoices from inspectors
      Outgoing Invoice Register/2026-11/<client>/<EBFI-2627-300>.pdf             our invoices to clients

Everything here is best effort: a failure never blocks saving a job or an invoice; it is shown on the job card
with a «Повторить» button.
"""
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import settings

log = logging.getLogger("ebfi.sharepoint")
GRAPH = "https://graph.microsoft.com/v1.0"
JOB_SUBFOLDERS = ("Inspection Documents", "Inspection Deliverables")
INCOMING, OUTGOING, CANCELLED = "Incoming Invoice Register", "Outgoing Invoice Register", "_Cancelled"
BAD = re.compile(r'["*:<>?/\\|#%]')  # characters OneDrive does not allow in names


class GraphError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status


def enabled() -> bool:
    return bool(settings.ms_tenant_id and settings.ms_client_id and settings.ms_client_secret and settings.ms_site_id)


def clean(name: str, limit: int = 200) -> str:
    """A name OneDrive accepts: no forbidden characters, no trailing dots or spaces."""
    n = " ".join(BAD.sub(" ", name or "").split()).strip(" .")
    return n[:limit].rstrip(" .") or "—"


class Graph:
    """Tiny Microsoft Graph client: app token, JSON calls, uploads. One instance per process (token cached)."""

    def __init__(self):
        self._token: str | None = None
        self._exp = 0.0
        self._drive: str | None = None

    # ---- transport
    def token(self) -> str:
        if self._token and time.time() < self._exp - 120:
            return self._token
        body = urllib.parse.urlencode({
            "client_id": settings.ms_client_id, "client_secret": settings.ms_client_secret,
            "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials",
        }).encode()
        url = f"https://login.microsoftonline.com/{settings.ms_tenant_id}/oauth2/v2.0/token"
        data = self._send(urllib.request.Request(url, data=body, method="POST",
                                                 headers={"Content-Type": "application/x-www-form-urlencoded"}))
        self._token, self._exp = data["access_token"], time.time() + int(data.get("expires_in", 3600))
        return self._token

    @staticmethod
    def _send(req: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("error", {})
                msg = msg.get("message") if isinstance(msg, dict) else str(msg)
            except Exception:  # noqa: BLE001
                msg = e.reason
            raise GraphError(e.code, msg or "ошибка Microsoft Graph") from None
        except urllib.error.URLError as e:
            raise GraphError(0, f"нет связи с Microsoft: {e.reason}") from None

    def call(self, method: str, path: str, body=None, raw: bytes | None = None, content_type: str | None = None) -> dict:
        url = path if path.startswith("https://") else GRAPH + path
        headers = {"Authorization": f"Bearer {self.token()}"}
        data = None
        if raw is not None:
            data, headers["Content-Type"] = raw, content_type or "application/octet-stream"
        elif body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        return self._send(urllib.request.Request(url, data=data, method=method, headers=headers))

    # ---- drive items
    def drive(self) -> str:
        if not self._drive:
            self._drive = self.call("GET", f"/sites/{settings.ms_site_id}/drive?$select=id")["id"]
        return self._drive

    def item(self, path: str) -> dict | None:
        """Item at a path from the drive root, or None."""
        q = urllib.parse.quote(path.strip("/"))
        try:
            return self.call("GET", f"/drives/{self.drive()}/root:/{q}")
        except GraphError as e:
            if e.status == 404:
                return None
            raise

    def get(self, item_id: str) -> dict | None:
        try:
            return self.call("GET", f"/drives/{self.drive()}/items/{item_id}")
        except GraphError as e:
            if e.status == 404:
                return None
            raise

    def children(self, item_id: str) -> list[dict]:
        out, url = [], f"/drives/{self.drive()}/items/{item_id}/children?$top=999"
        while url:
            page = self.call("GET", url)
            out += page.get("value", [])
            url = page.get("@odata.nextLink")
        return out

    def folder(self, parent_id: str, name: str) -> dict:
        """Child folder `name`, created when missing."""
        name = clean(name)
        for c in self.children(parent_id):
            if "folder" in c and c["name"].lower() == name.lower():
                return c
        try:
            return self.call("POST", f"/drives/{self.drive()}/items/{parent_id}/children",
                             {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"})
        except GraphError as e:
            if e.status == 409:  # created meanwhile
                return next(c for c in self.children(parent_id) if c["name"].lower() == name.lower())
            raise

    def path_folder(self, *parts: str) -> dict:
        """Folder at EBFI/<parts…>, every level created when missing."""
        root = self.item(settings.ms_root) or self.call(
            "POST", f"/drives/{self.drive()}/root/children", {"name": settings.ms_root, "folder": {}})
        cur = root
        for p in parts:
            cur = self.folder(cur["id"], p)
        return cur

    def update(self, item_id: str, name: str | None = None, parent_id: str | None = None) -> dict:
        body: dict = {"@microsoft.graph.conflictBehavior": "rename"}
        if name:
            body["name"] = clean(name)
        if parent_id:
            body["parentReference"] = {"id": parent_id}
        return self.call("PATCH", f"/drives/{self.drive()}/items/{item_id}", body)

    def upload(self, parent_id: str, name: str, content: bytes, mime: str | None = None) -> dict:
        """Upload a file; an existing file with that name gets a « 1» suffix rather than being overwritten."""
        name = clean(name)
        if len(content) <= 4 * 1024 * 1024:
            q = urllib.parse.quote(name)
            return self.call("PUT", f"/drives/{self.drive()}/items/{parent_id}:/{q}:/content"
                                    "?@microsoft.graph.conflictBehavior=rename", raw=content, content_type=mime)
        sess = self.call("POST", f"/drives/{self.drive()}/items/{parent_id}:/{urllib.parse.quote(name)}:/createUploadSession",
                         {"item": {"@microsoft.graph.conflictBehavior": "rename"}})
        url, step, total, res = sess["uploadUrl"], 5 * 1024 * 1024, len(content), {}
        for start in range(0, total, step):
            chunk = content[start:start + step]
            req = urllib.request.Request(url, data=chunk, method="PUT", headers={
                "Content-Length": str(len(chunk)), "Content-Range": f"bytes {start}-{start + len(chunk) - 1}/{total}"})
            res = self._send(req)  # the upload URL is pre-authorised: no bearer token
        return res


_graph: Graph | None = None


def graph() -> Graph:
    global _graph
    if _graph is None:
        _graph = Graph()
    return _graph


def set_graph(g):  # tests
    global _graph
    _graph = g
