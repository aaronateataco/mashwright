"""The local mashup library: <data>/mashups/<id>/ holds mashwright.json and its component files."""

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional

from . import installer
from . import recipe as rcp
from .model import MashwrightError
from .platforms import HostEnv, data_dir


def root(env: HostEnv) -> Path:
    return data_dir(env) / "mashups"


def import_path(env: HostEnv, path) -> dict:
    """Add a mashup from a .mashwright/.zip archive or a folder. Returns its recipe."""
    src = Path(path).expanduser()
    if not src.exists():
        raise MashwrightError(f"Not found: {src}")
    with tempfile.TemporaryDirectory(prefix="mashwright-import-") as td:
        stage = Path(td) / "m"
        if src.is_dir():
            shutil.copytree(src, stage)
        else:
            try:
                with zipfile.ZipFile(src) as z:
                    infos = installer.safe_members(z)
                    stage.mkdir()
                    for i in infos:
                        if i.is_dir():
                            continue
                        dest = stage.joinpath(*i.filename.replace("\\", "/").split("/"))
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(i) as s, open(dest, "wb") as d:
                            shutil.copyfileobj(s, d)
            except zipfile.BadZipFile:
                raise MashwrightError(f"{src.name} is not a Mashwright package")
            # A package may wrap everything in one top folder.
            inner = [p for p in stage.iterdir()]
            if not (stage / rcp.RECIPE_FILE).exists() and len(inner) == 1 and inner[0].is_dir():
                stage = inner[0]
        if not (stage / rcp.RECIPE_FILE).exists():
            from . import melty_format
            if not melty_format.looks_like(stage):
                raise MashwrightError(f"{src.name} has no {rcp.RECIPE_FILE} (or Melty-format recipe.json)")
            melty_format.write_converted(stage, title=src.stem if src.is_file() else src.name)
        r = rcp.load(stage)
        problems = rcp.validate(r)
        if problems:
            raise MashwrightError("This mashup's recipe has problems: " + "; ".join(problems))
        for c in r.get("components", []):
            f = stage / c["file"]
            if not f.is_file():
                raise MashwrightError(f"Package is missing {c['file']}")
            if c.get("sha256") and installer.sha256_file(f).lower() != c["sha256"].lower():
                raise MashwrightError(f"{c['file']} is damaged (checksum mismatch)")
        dest = root(env) / r["id"]
        if installer.is_installed(env, r["id"]):
            raise MashwrightError(f"{r['title']} is installed; uninstall it before importing a new copy")
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, dest)
        return r


def list_all(env: HostEnv) -> List[dict]:
    out = []
    if root(env).is_dir():
        for d in sorted(root(env).iterdir()):
            if (d / rcp.RECIPE_FILE).is_file():
                try:
                    r = rcp.load(d)
                    r["_dir"] = str(d)
                    out.append(r)
                except MashwrightError:
                    continue
    return out


def get(env: HostEnv, mashup_id: str) -> Optional[dict]:
    d = root(env) / mashup_id
    if not (d / rcp.RECIPE_FILE).is_file():
        return None
    r = rcp.load(d)
    r["_dir"] = str(d)
    return r


def remove(env: HostEnv, mashup_id: str) -> None:
    if installer.is_installed(env, mashup_id):
        raise MashwrightError("Uninstall it from your games first")
    d = root(env) / mashup_id
    if d.is_dir():
        shutil.rmtree(d)
