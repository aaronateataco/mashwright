"""The operations the CLI and the web UI share (one place that ties stores, library and installer)."""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from . import binaries, installer, library, launcher
from . import recipe as rcp
from . import stores, targets
from .model import Game, MashwrightError
from .platforms import HostEnv

log = logging.getLogger(__name__)


class App:
    def __init__(self, env: HostEnv):
        self.env = env
        self.games: List[Game] = []
        self.rescan()

    def rescan(self) -> List[Game]:
        self.games = stores.detect_all(self.env) + targets.detect_all_targets(self.env)
        return self.games

    def game(self, key: str) -> Optional[Game]:
        return next((g for g in self.games if g.key == key), None)

    def mashups(self) -> List[dict]:
        out = []
        for r in library.list_all(self.env):
            cands = rcp.candidates(r, self.games, self.env)
            picked, missing = rcp.choose(r, self.games, self.env)
            st = installer.status(self.env, r["id"])
            out.append({
                "recipe": {k: v for k, v in r.items() if not k.startswith("_")},
                "candidates": {s: [g.to_json() for g in gs] for s, gs in cands.items()},
                "missing": missing,
                "warnings": rcp.version_problems(r, picked),
                "status": st,
                "ready": not missing,
                "fit": self.fit(r, picked),
                "desktop": self.desktop_state(r) if r.get("gnome_extension") else None,
            })
        return out

    def install(self, mashup_id: str, choices: Optional[Dict[str, str]] = None, backend: str = "",
                progress=None) -> dict:
        r = self._recipe(mashup_id)
        picked, missing = rcp.choose(r, self.games, self.env, choices)
        if missing:
            raise MashwrightError("Not installed: " + ", ".join(missing))
        if installer.is_installed(self.env, mashup_id):
            installer.uninstall(self.env, mashup_id)
        fit = self.fit(r, picked)
        if fit["status"] == "blocked":
            raise MashwrightError("; ".join(fit["notes"]))
        j = installer.install(r, r["_dir"], picked, self.env, backend, progress, skip=fit["skip"])
        if r.get("gnome_extension"):
            self._gnome_extension(r["gnome_extension"], True)
        return {"files": sum(e["op"] in ("create", "overwrite") for e in j.data["entries"])}

    def fit(self, r: dict, picked: Dict[str, Game]) -> dict:
        """Binary platforms inside the components vs. the chosen game (cached per file version)."""
        d = Path(r["_dir"])
        key = (r["id"], tuple(sorted((c["file"], (d / c["file"]).stat().st_mtime) for c in r.get("components", [])
                                     if (d / c["file"]).is_file())))
        cache = self.__dict__.setdefault("_bin_cache", {})
        if key not in cache:
            cache[key] = binaries.analyze(r, d)
        primary = picked.get(rcp.primary_slug(r))
        return binaries.fit(r, cache[key], primary, self.env.os)

    def inspect(self, mashup_id: str, choices: Optional[Dict[str, str]] = None) -> dict:
        r = self._recipe(mashup_id)
        picked, _missing = rcp.choose(r, self.games, self.env, choices)
        return self.fit(r, picked)

    def catalog(self, force: bool = False) -> List[dict]:
        from . import catalog
        have = {m["id"]: m.get("version") for m in library.list_all(self.env)}
        out = []
        for e in catalog.fetch(self.env, force):
            e = dict(e)
            e["in_library"] = e["id"] in have
            e["update"] = e["in_library"] and have[e["id"]] != e.get("version")
            out.append(e)
        return out

    def get_from_catalog(self, mashup_id: str, install: bool = True, progress=None) -> dict:
        from . import catalog
        r = catalog.download(self.env, mashup_id, progress)
        if install:
            self.rescan()
            picked, missing = rcp.choose(self._recipe(r["id"]), self.games, self.env)
            if not missing:
                return {"recipe": r["id"], **self.install(r["id"], progress=progress)}
            return {"recipe": r["id"], "missing": missing}
        return {"recipe": r["id"]}

    def cover_path(self, mashup_id: str) -> Optional[str]:
        r = library.get(self.env, mashup_id)
        if not r or not r.get("cover"):
            return None
        p = (Path(r["_dir"]) / r["cover"]).resolve()
        return str(p) if Path(r["_dir"]).resolve() in p.parents and p.is_file() else None

    def uninstall(self, mashup_id: str) -> List[str]:
        r = library.get(self.env, mashup_id)
        if r and r.get("gnome_extension"):
            self._gnome_extension(r["gnome_extension"], False)
        return installer.uninstall(self.env, mashup_id)

    def _enabled_extensions(self) -> List[str]:
        code, cur = self.env.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], 10)
        if code != 0:
            return []
        return [x.strip().strip("'") for x in cur.strip().lstrip("@as").strip().strip("[]").split(",") if x.strip()]

    def desktop_state(self, r: dict) -> dict:
        uuid = r["gnome_extension"]
        return {"extension": uuid, "enabled": uuid in self._enabled_extensions(),
                "installed": installer.is_installed(self.env, r["id"])}

    def set_desktop(self, mashup_id: str, on: bool) -> dict:
        r = self._recipe(mashup_id)
        if not r.get("gnome_extension"):
            raise MashwrightError("This mashup isn't a desktop mashup")
        if not installer.is_installed(self.env, mashup_id):
            raise MashwrightError("Install it first")
        self._gnome_extension(r["gnome_extension"], on)
        if not on:
            items = [x for x in self._enabled_extensions() if x != r["gnome_extension"]]
            self.env.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions",
                          "[" + ", ".join(f"'{x}'" for x in items) + "]"], 10)
        return self.desktop_state(r)

    def desktop_prefs(self, mashup_id: str) -> str:
        r = self._recipe(mashup_id)
        tool = self.env.which("gnome-extensions")
        if not r.get("gnome_extension") or not tool:
            raise MashwrightError("No preferences to open")
        launcher._spawn([tool, "prefs", r["gnome_extension"]])
        return "Opening its preferences"

    def _gnome_extension(self, uuid: str, on: bool) -> None:
        """Turn a desktop mashup's GNOME Shell extension on or off (GNOME's own command)."""
        tool = self.env.which("gnome-extensions")
        if self.env.os != "linux" or not tool:
            return
        code, out = self.env.run([tool, "enable" if on else "disable", uuid], 20)
        if code != 0 and on:
            # A brand-new extension is only seen by GNOME Shell after logging back in; ask GNOME to
            # turn it on then, the same way the Extensions app does.
            code2, cur = self.env.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"], 10)
            if code2 == 0 and uuid not in cur:
                items = [x.strip().strip("'") for x in cur.strip().lstrip("@as").strip().strip("[]").split(",") if x.strip()]
                items.append(uuid)
                self.env.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions",
                              "[" + ", ".join(f"'{x}'" for x in items) + "]"], 10)

    def launch(self, mashup_id: str) -> str:
        r = self._recipe(mashup_id)
        st = installer.status(self.env, mashup_id)
        if not st["installed"]:
            raise MashwrightError("Install it first")
        if (r.get("launch") or {}).get("kind") == "desktop":
            return (r.get("launch") or {}).get("message") or "It's on your desktop"
        slug = (r.get("launch") or {}).get("game") or rcp.primary_slug(r)
        key = st["games"].get(slug)
        g = self.game(key) if key else None
        if g is None:
            raise MashwrightError(f"{slug} is no longer installed")
        return launcher.launch(g, self.env, (r.get("launch") or {}).get("args"))

    def import_path(self, path: str) -> dict:
        r = library.import_path(self.env, path)
        return {k: v for k, v in r.items() if not k.startswith("_")}

    def remove(self, mashup_id: str) -> None:
        library.remove(self.env, mashup_id)

    def _recipe(self, mashup_id: str) -> dict:
        r = library.get(self.env, mashup_id)
        if r is None:
            raise MashwrightError(f"No mashup called {mashup_id} in your library")
        return r
