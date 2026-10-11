"""Build a .mashwright package from a mashup folder: a Mashwright one (mashwright.json) or a creator's
own Melty-format build (recipe.json beside its zips), so a creator can publish the same mashup to the
Mashwright catalog too. Checksums are filled in and the recipe is validated."""

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import List

from . import installer, melty_format
from . import recipe as rcp
from .model import MashwrightError


def pack(folder: str, output: str = "", title: str = "", version: str = "", authors: List[str] = (),
         cover: str = "") -> Path:
    src = Path(folder).expanduser()
    if not src.is_dir():
        raise MashwrightError(f"Not a folder: {src}")
    if (src / rcp.RECIPE_FILE).is_file():
        r = rcp.load(src)
    elif melty_format.looks_like(src):
        r = melty_format.convert(src, title or src.name)
    else:
        raise MashwrightError(f"{src} has no {rcp.RECIPE_FILE} or Melty-format recipe.json")
    if title:
        r["title"] = title
    if version:
        r["version"] = version
    if authors:
        r["authors"] = list(authors)
    files = {}
    for c in r.get("components", []):
        f = src / c["file"]
        if not f.is_file():
            raise MashwrightError(f"Missing component file {c['file']}")
        c["sha256"] = installer.sha256_file(f)
        files[c["file"]] = f
    if cover:
        cp = Path(cover).expanduser()
        if not cp.is_file():
            raise MashwrightError(f"Cover not found: {cp}")
        r["cover"] = "cover" + cp.suffix.lower()
        files[r["cover"]] = cp
    elif r.get("cover") and (src / r["cover"]).is_file():
        files[r["cover"]] = src / r["cover"]
    problems = rcp.validate(r)
    if problems:
        raise MashwrightError("Recipe problems: " + "; ".join(problems))
    out = Path(output).expanduser() if output else src.parent / f"{r['id']}.mashwright"
    with tempfile.NamedTemporaryFile(dir=str(out.parent), suffix=".tmp", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_STORED) as z:
            for name, f in files.items():
                z.write(f, name)
            z.writestr(rcp.RECIPE_FILE, json.dumps(r, indent=2))
        shutil.move(str(tmp_path), str(out))
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return out
