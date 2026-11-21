"""In-memory stand-in for Microsoft Graph used by the local tests (graph.microsoft.com is not reachable here)."""
import itertools

from app import sharepoint as sp


class FakeGraph:
    def __init__(self):
        self.ids = itertools.count(1)
        self.items = {"root": {"id": "root", "name": "", "parent": None, "folder": {}}}

    def _new(self, parent, name, folder=True, content=None):
        i = str(next(self.ids))
        it = {"id": i, "name": name, "parent": parent, "webUrl": f"https://od/{i}/{name}"}
        if folder:
            it["folder"] = {}
        else:
            it["size"] = len(content or b"")
        self.items[i] = it
        return it

    def drive(self):
        return "d"

    def item(self, path):
        cur = self.items["root"]
        for part in path.strip("/").split("/"):
            cur = next((c for c in self.children(cur["id"]) if c["name"] == part), None)
            if not cur:
                return None
        return cur

    def get(self, i):
        return self.items.get(i)

    def children(self, i):
        return [x for x in self.items.values() if x["parent"] == i]

    def folder(self, parent, name):
        name = sp.clean(name)
        return next((c for c in self.children(parent) if c["name"].lower() == name.lower()), None) or self._new(parent, name)

    def path_folder(self, *parts):
        cur = self.folder("root", sp.settings.ms_root)
        for p in parts:
            cur = self.folder(cur["id"], p)
        return cur

    def update(self, i, name=None, parent_id=None):
        it = self.items[i]
        if name:
            it["name"] = sp.clean(name)
        if parent_id:
            it["parent"] = parent_id
        it["webUrl"] = f"https://od/{i}/{it['name']}"
        return it

    def upload(self, parent, name, content, mime=None):
        return self._new(parent, sp.clean(name), folder=False, content=content)

    def tree(self, i="root", depth=0):
        out = []
        for c in sorted(self.children(i), key=lambda x: x["name"]):
            out.append("  " * depth + c["name"] + ("/" if "folder" in c else ""))
            out += self.tree(c["id"], depth + 1)
        return out
