"""Local preview with the in-memory OneDrive: uvicorn tests.fake_app:app (MS_* env vars set to anything)."""
import sys

sys.path.insert(0, "tests")
from fake_graph import FakeGraph  # noqa: E402

from app import sharepoint  # noqa: E402
from app.main import app  # noqa: E402,F401

g = FakeGraph()
y = g.path_folder("Server 2026")
q = g.folder(y["id"], "26.29 TUV R QATAR")
g.folder(q["id"], "26.29-43 Swaminath Germany 17,18,19,20.11.2026")
sharepoint.set_graph(g)
