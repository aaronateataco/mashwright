"""Install and uninstall mashups, journalling every change so a game can be put back exactly.

Journal: <data>/installed/<id>.json, rewritten after every step (a crash mid-install still leaves an
accurate record). Files Mashwright overwrote are copied to <data>/backups/<id>/ first. Uninstall
walks the journal backwards: created files are removed, overwritten ones restored byte-for-byte,
folders Mashwright created are removed if empty, settings are put back.
"""

import configparser
import hashlib
import io
import json
import os
import shutil
import stat
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, List, Optional

from . import recipe as rcp
from .model import Game, MashwrightError, Placement
from .platforms import HostEnv, data_dir

MAX_TOTAL_BYTES = 4 << 30
MAX_ENTRIES = 50000


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def journal_path(env: HostEnv, mashup_id: str) -> Path:
    return data_dir(env) / "installed" / f"{mashup_id}.json"


def backups_dir(env: HostEnv, mashup_id: str) -> Path:
    return data_dir(env) / "backups" / mashup_id


def is_installed(env: HostEnv, mashup_id: str) -> bool:
    return journal_path(env, mashup_id).is_file()


# ---- safe archive reading ---------------------------------------------------------------------

def safe_members(z: zipfile.ZipFile) -> List[zipfile.ZipInfo]:
    """Archive entries, rejecting anything that could escape the destination."""
    infos = z.infolist()
    if len(infos) > MAX_ENTRIES:
        raise MashwrightError("Archive has too many entries")
    total = 0
    for i in infos:
        name = i.filename.replace("\\", "/")
        parts = PurePosixPath(name).parts
        if name.startswith("/") or ".." in parts or (parts and ":" in parts[0]):
            raise MashwrightError(f"Unsafe path in archive: {i.filename}")
        mode = (i.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise MashwrightError(f"Archive contains a symlink: {i.filename}")
        total += i.file_size
        if total > MAX_TOTAL_BYTES:
            raise MashwrightError("Archive expands to more than 4 GiB")
    return infos


# ---- planning ---------------------------------------------------------------------------------

def plan(r: dict, picked: Dict[str, Game], env: HostEnv, backend: str = "") -> List[Placement]:
    ctx = rcp.context(r, picked, env, backend)
    out: List[Placement] = []
    for m in r.get("mappings", []):
        if not rcp.when_matches(m.get("when"), picked, r, env):
            continue
        dest = rcp.resolve(m["to"], ctx)
        if dest is None:
            if m.get("optional"):
                continue
            raise MashwrightError(f"Can't place component {m['component']}: {m['to']} doesn't apply to the chosen games")
        comp = next(c for c in r["components"] if c["id"] == m["component"])
        out.append(Placement(component=m["component"], source=str(m.get("from", "")).strip("/"), dest=dest,
                             extract=bool(comp.get("extract", True)), optional=bool(m.get("optional"))))
    return out


def allowed_roots(r: dict, picked: Dict[str, Game], env: HostEnv, backend: str = "") -> List[Path]:
    ctx = rcp.context(r, picked, env, backend)
    roots = [Path(str(v)) for k, v in ctx.items()
             if k not in ("home",) and not str(v).startswith(("device:", "afc:"))]
    return [p.resolve() for p in roots]


def _inside(path: Path, roots: List[Path]) -> bool:
    rp = path.resolve()
    return any(rp == root or root in rp.parents for root in roots)


# ---- journal ----------------------------------------------------------------------------------

class Journal:
    def __init__(self, env: HostEnv, r: dict, picked: Dict[str, Game]):
        self.env = env
        self.path = journal_path(env, r["id"])
        self.backups = backups_dir(env, r["id"])
        self.data = {"id": r["id"], "title": r.get("title", ""), "version": r.get("version", ""),
                     "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                     "games": {s: g.key for s, g in picked.items()},
                     "device_games": {s: g.to_json() for s, g in picked.items() if g.store in ("android", "ios")},
                     "entries": []}

    def add(self, entry: dict) -> None:
        self.data["entries"].append(entry)
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        tmp.replace(self.path)


# ---- install ----------------------------------------------------------------------------------

def install(r: dict, mashup_dir, picked: Dict[str, Game], env: HostEnv, backend: str = "",
            on_progress: Optional[Callable[[str, float], None]] = None, skip: Optional[List[str]] = None) -> Journal:
    """Install; `skip` lists "component:folder" entries to leave out (another platform's build)."""
    problems = rcp.validate(r)
    if problems:
        raise MashwrightError("Recipe problems: " + "; ".join(problems))
    if is_installed(env, r["id"]):
        raise MashwrightError(f"{r.get('title', r['id'])} is already installed; uninstall it first")
    mashup_dir = Path(mashup_dir)
    placements = plan(r, picked, env, backend)
    roots = allowed_roots(r, picked, env, backend)
    j = Journal(env, r, picked)
    j.save()
    progress = on_progress or (lambda msg, frac: None)
    try:
        for c in r.get("components", []):
            f = mashup_dir / c["file"]
            if not f.is_file():
                raise MashwrightError(f"Component file missing: {c['file']}")
            if c.get("sha256") and sha256_file(f).lower() != c["sha256"].lower():
                raise MashwrightError(f"Component {c['file']} is damaged (checksum mismatch)")
        for n, pl in enumerate(placements):
            progress(f"Placing {pl.component}", n / max(1, len(placements)))
            comp = next(c for c in r["components"] if c["id"] == pl.component)
            folders = [s.split(":", 1)[1].strip("/") + "/" for s in (skip or []) if s.split(":", 1)[0] == pl.component]
            _place(j, mashup_dir / comp["file"], pl, roots, picked, env, folders)
        for s in r.get("settings", []) or []:
            if not rcp.when_matches(s.get("when"), picked, r, env):
                continue
            ctx = rcp.context(r, picked, env, backend)
            file_ = rcp.resolve(s["file"], ctx)
            value = rcp.resolve(str(s["value"]), ctx) if "{" in str(s["value"]) else str(s["value"])
            if file_ is None or value is None:
                if s.get("optional"):
                    continue
                raise MashwrightError(f"Can't resolve setting {s['key']}")
            if s.get("windows_path"):
                value = to_wine_path(value)
            _setting(j, Path(file_), s["section"], s["key"], value, roots)
        progress("Done", 1.0)
        return j
    except BaseException:
        _undo(env, j.data, j.backups, picked_devices=picked)
        try:
            j.path.unlink()
        except OSError:
            pass
        shutil.rmtree(j.backups, ignore_errors=True)
        raise


def to_wine_path(posix: str) -> str:
    """A Linux path as a Windows program under Wine/Proton sees it (Z: is the Linux root)."""
    return "Z:" + posix.replace("/", "\\") if posix.startswith("/") else posix


def _mkdirs(j: Journal, folder: Path) -> None:
    missing = []
    p = folder
    while not p.exists():
        missing.append(p)
        p = p.parent
    for d in reversed(missing):
        d.mkdir()
        j.add({"op": "mkdir", "path": str(d)})


def _write_file(j: Journal, dest: Path, data_src, roots: List[Path], mode: Optional[int] = None) -> None:
    """Write one file (from a path or a file object), backing up anything it replaces."""
    if not _inside(dest.parent if not dest.exists() else dest, roots):
        raise MashwrightError(f"Refusing to write outside the game/app folders: {dest}")
    _mkdirs(j, dest.parent)
    if dest.is_dir():
        raise MashwrightError(f"A folder is in the way: {dest}")
    entry = {"op": "create", "path": str(dest)}
    if dest.exists():
        j.backups.mkdir(parents=True, exist_ok=True)
        backup = j.backups / f"{len(j.data['entries']):05d}_{dest.name}"
        shutil.copy2(dest, backup)
        entry = {"op": "overwrite", "path": str(dest), "backup": str(backup)}
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=".mashwright-")
    try:
        with os.fdopen(fd, "wb") as out:
            if isinstance(data_src, (str, Path)):
                with open(data_src, "rb") as src:
                    shutil.copyfileobj(src, out)
            else:
                shutil.copyfileobj(data_src, out)
        if mode:
            os.chmod(tmp, mode)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    entry["sha256"] = sha256_file(dest)
    j.add(entry)


def _place(j: Journal, archive: Path, pl: Placement, roots: List[Path], picked, env: HostEnv,
           skip_folders: Optional[List[str]] = None) -> None:
    device = pl.dest.startswith(("device:", "afc:"))
    if not pl.extract:
        if device:
            _device_put(j, archive, _join_device(pl.dest, archive.name), picked, env)
        else:
            _write_file(j, Path(pl.dest) / archive.name, archive, roots)
        return
    with zipfile.ZipFile(archive) as z:
        prefix = pl.source.strip("/") + "/" if pl.source else ""
        for info in safe_members(z):
            name = info.filename.replace("\\", "/")
            if info.is_dir() or not name.startswith(prefix) or name == prefix:
                continue
            if any(name.startswith(f) for f in skip_folders or []):
                continue
            rel = name[len(prefix):]
            mode = (info.external_attr >> 16) & 0o777 or None
            if device:
                with tempfile.TemporaryDirectory() as td:
                    local = Path(td) / PurePosixPath(rel).name
                    with z.open(info) as src, open(local, "wb") as out:
                        shutil.copyfileobj(src, out)
                    _device_put(j, local, _join_device(pl.dest, rel), picked, env)
            else:
                with z.open(info) as src:
                    _write_file(j, Path(pl.dest).joinpath(*PurePosixPath(rel).parts), src, roots, mode)


def _join_device(dest: str, rel: str) -> str:
    return dest.rstrip("/") + "/" + rel.lstrip("/") if not dest.endswith(":") else dest + rel.lstrip("/")


def _device_game(picked, store: str) -> Game:
    for g in picked.values():
        if g.store == store:
            return g
    raise MashwrightError(f"No {store} device chosen")


def _device_put(j: Journal, local: Path, dest: str, picked, env: HostEnv) -> None:
    from . import targets
    if dest.startswith("device:"):
        _, serial, path = dest.split(":", 2)
        targets.module("android").place(_device_game(picked, "android"), path, str(local), env)
    else:
        _, udid, bundle, path = dest.split(":", 3)
        targets.module("ios").place(_device_game(picked, "ios"), path, str(local), env)
    j.add({"op": "device", "path": dest})


def _setting(j: Journal, file_: Path, section: str, key: str, value: str, roots: List[Path]) -> None:
    if not _inside(file_.parent if not file_.exists() else file_, roots):
        raise MashwrightError(f"Refusing to change settings outside the game/app folders: {file_}")
    cp = configparser.RawConfigParser()
    cp.optionxform = str
    existed = file_.exists()
    if existed:
        cp.read(file_, encoding="utf-8")
    old = cp.get(section, key) if cp.has_section(section) and cp.has_option(section, key) else None
    if not cp.has_section(section):
        cp.add_section(section)
    cp.set(section, key, _ini_value(value))
    _mkdirs(j, file_.parent)
    buf = io.StringIO()
    cp.write(buf)
    file_.write_text(buf.getvalue(), encoding="utf-8")
    j.add({"op": "setting", "path": str(file_), "section": section, "key": key, "old": old, "file_existed": existed})


def _ini_value(v: str) -> str:
    """Godot's ConfigFile reads strings in quotes; numbers/booleans bare."""
    if v.lower() in ("true", "false") or _is_number(v) or (v.startswith('"') and v.endswith('"')):
        return v
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _is_number(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


# ---- uninstall --------------------------------------------------------------------------------

def _undo(env: HostEnv, data: dict, backups: Path, picked_devices=None) -> List[str]:
    """Reverse the journal entries; returns warnings (files that changed since, etc.)."""
    warnings: List[str] = []
    devices = {}
    for slug, gj in (data.get("device_games") or {}).items():
        devices[gj["store"]] = Game(**{**gj, "install_dir": None})
    if picked_devices:
        for g in picked_devices.values():
            if g.store in ("android", "ios"):
                devices[g.store] = g
    for e in reversed(data.get("entries", [])):
        p = Path(e["path"]) if e["op"] != "device" else None
        try:
            if e["op"] == "create":
                if p.exists():
                    p.unlink()
            elif e["op"] == "overwrite":
                b = Path(e["backup"])
                if b.exists():
                    shutil.copy2(b, p)
                else:
                    warnings.append(f"backup missing for {p}")
            elif e["op"] == "mkdir":
                try:
                    p.rmdir()
                except OSError:
                    warnings.append(f"kept non-empty folder {p}")
            elif e["op"] == "setting":
                _undo_setting(e)
            elif e["op"] == "device":
                from . import targets
                path = e["path"]
                if path.startswith("device:") and "android" in devices:
                    targets.module("android").remove(devices["android"], path.split(":", 2)[2], env)
                elif path.startswith("afc:") and "ios" in devices:
                    targets.module("ios").remove(devices["ios"], path.split(":", 3)[3], env)
        except OSError as ex:
            warnings.append(f"{e['path']}: {ex}")
    return warnings


def _undo_setting(e: dict) -> None:
    p = Path(e["path"])
    if not p.exists():
        return
    if not e.get("file_existed"):
        p.unlink()
        return
    cp = configparser.RawConfigParser()
    cp.optionxform = str
    cp.read(p, encoding="utf-8")
    if e.get("old") is None:
        if cp.has_section(e["section"]):
            cp.remove_option(e["section"], e["key"])
            if not cp.options(e["section"]):
                cp.remove_section(e["section"])
    else:
        cp.set(e["section"], e["key"], e["old"])
    buf = io.StringIO()
    cp.write(buf)
    p.write_text(buf.getvalue(), encoding="utf-8")


def uninstall(env: HostEnv, mashup_id: str) -> List[str]:
    jp = journal_path(env, mashup_id)
    if not jp.is_file():
        raise MashwrightError(f"{mashup_id} is not installed")
    data = json.loads(jp.read_text(encoding="utf-8"))
    warnings = _undo(env, data, backups_dir(env, mashup_id))
    jp.unlink()
    shutil.rmtree(backups_dir(env, mashup_id), ignore_errors=True)
    return warnings


def status(env: HostEnv, mashup_id: str) -> dict:
    jp = journal_path(env, mashup_id)
    if not jp.is_file():
        return {"installed": False}
    data = json.loads(jp.read_text(encoding="utf-8"))
    changed = []
    for e in data.get("entries", []):
        if e["op"] in ("create", "overwrite"):
            p = Path(e["path"])
            if not p.exists() or sha256_file(p) != e.get("sha256"):
                changed.append(str(p))
    return {"installed": True, "version": data.get("version"), "games": data.get("games", {}),
            "files": sum(e["op"] in ("create", "overwrite") for e in data.get("entries", [])),
            "changed": changed, "installed_at": data.get("installed_at")}
