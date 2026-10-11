"""Open mashup packages made in Melty's recipe format (a recipe.json beside its component zips),
such as the files a creator builds for their own mashup. Mashwright converts the recipe to its own
format and installs it with its own installer.

This only reads files you already have. Mashwright doesn't scrape, download from or sign in to
Melty, whose terms forbid scraping and have players install Melty mashups through Melty.
"""

import json
import re
from pathlib import Path
from typing import Optional

from .model import MashwrightError, is_slug, slugify

MELTY_RECIPE = "recipe.json"
PLACEHOLDER_MAP = {"{game}": "{game}", "{appdata}": "{appdata}", "{home}": "{home}"}


def looks_like(folder: Path) -> bool:
    p = folder / MELTY_RECIPE
    if not p.is_file():
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(d, dict) and "schemaVersion" in d and isinstance(d.get("components"), list)


def _slug(s: str) -> str:
    # Melty marks games outside its catalog as "custom-<name>".
    s = re.sub(r"^custom-", "", s or "")
    return s if is_slug(s) else slugify(s)


def convert(folder: Path, title: Optional[str] = None) -> dict:
    """A Mashwright recipe for the Melty-format package in `folder`."""
    try:
        m = json.loads((folder / MELTY_RECIPE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise MashwrightError(f"Can't read {MELTY_RECIPE}: {e}")
    games = []
    for i, g in enumerate(m.get("games") or []):
        entry = {"slug": _slug(str(g.get("slug", ""))), "role": g.get("role") or ("primary" if i == 0 else "secondary")}
        if g.get("version"):
            entry["version"] = str(g["version"])
        if g.get("optional"):
            entry["optional"] = True
        games.append(entry)
    if games and not any(g["role"] == "primary" for g in games):
        games[0]["role"] = "primary"
    components = []
    for c in m.get("components") or []:
        name = c.get("fileName") or c.get("file")
        if not name or not c.get("id"):
            continue
        components.append({"id": c["id"], "file": name, "label": c.get("label", ""), "extract": True,
                           "optional": not c.get("required", True)})
    mappings = []
    for mp in m.get("mappings") or []:
        to = str(mp.get("to", ""))
        if not to.startswith("{"):
            raise MashwrightError(f"Unsupported destination in {MELTY_RECIPE}: {to}")
        mappings.append({"component": mp.get("component"), "from": mp.get("from", ""), "to": to})
    name = title or (m.get("title") if isinstance(m.get("title"), str) else None) or folder.name
    notes = m.get("notes") or {}
    return {
        "mashwright": 1,
        "id": slugify(m.get("id") or name),
        "title": name,
        "version": str(m.get("version") or "1.0"),
        "description": notes.get("firstLaunch", ""),
        "source": "melty-format package",
        "games": games,
        "components": components,
        "mappings": mappings,
        "launch": {"game": next((g["slug"] for g in games if g["role"] == "primary"), games[0]["slug"] if games else "")},
        "notes": notes,
    }


def write_converted(folder: Path, title: Optional[str] = None) -> dict:
    r = convert(folder, title)
    (folder / "mashwright.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
    return r
