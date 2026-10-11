"""Mashwright recipes (mashwright.json): what a mashup needs and where its files go.

See SPEC.md for the format. This module loads and validates recipes, picks installed games for
each slug, and resolves the {placeholders} in mapping destinations.
"""

import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple

from .model import Game, MashwrightError, is_slug
from .platforms import HostEnv, appdata_dir, data_dir

RECIPE_FILE = "mashwright.json"
PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)(?::([a-z0-9-]+))?\}")
KNOWN_PLACEHOLDERS = {"game", "appdata", "home", "data", "switch_mod", "android_data", "android_media", "sdcard",
                      "ios_documents", "proton_prefix", "proton_appdata", "emu_root", "emu_mod"}
TARGET_KEYS = {"switch_title": "switch", "android_package": "android", "ios_bundle": "ios"}


def load(path) -> dict:
    """A recipe from a mashup folder, a mashwright.json file, or a .mashwright/.zip archive."""
    p = Path(path)
    try:
        if p.is_dir():
            return json.loads((p / RECIPE_FILE).read_text(encoding="utf-8"))
        if p.suffix.lower() in (".mashwright", ".zip"):
            with zipfile.ZipFile(p) as z:
                return json.loads(z.read(RECIPE_FILE).decode("utf-8"))
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as e:
        raise MashwrightError(f"Can't read a Mashwright recipe from {p}: {e}")


# ---- versions ---------------------------------------------------------------------------------

def _vtuple(v: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4]) or (0,)


def version_ok(version: str, constraint: str) -> Optional[bool]:
    """True/False against constraints like ">=1.1.15, <2"; None when the version is unknown."""
    if not constraint:
        return True
    if not version or not re.search(r"\d", version):
        return None
    have = _vtuple(version)
    for part in constraint.split(","):
        m = re.match(r"\s*(>=|<=|==|=|>|<|\^|~)?\s*([0-9][0-9.]*)\s*$", part)
        if not m:
            continue
        op, want = m.group(1) or "==", _vtuple(m.group(2))
        n = max(len(have), len(want))
        a, b = have + (0,) * (n - len(have)), want + (0,) * (n - len(want))
        ok = {">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b, "==": a[:len(want)] == want,
              "=": a[:len(want)] == want, "^": a >= b and a[0] == b[0], "~": a >= b and a[:2] == b[:2]}[op]
        if not ok:
            return False
    return True


# ---- validation -------------------------------------------------------------------------------

def validate(r: dict) -> List[str]:
    problems: List[str] = []
    if not isinstance(r, dict):
        return ["recipe is not a JSON object"]
    if r.get("mashwright") != 1:
        problems.append('"mashwright" must be 1')
    if not is_slug(str(r.get("id", ""))):
        problems.append('"id" must be a slug (a-z, 0-9, dashes)')
    for key in ("title", "version"):
        if not isinstance(r.get(key), str) or not r.get(key):
            problems.append(f'"{key}" is required')
    games = r.get("games")
    if not isinstance(games, list) or not games:
        problems.append('"games" must list at least one game')
        games = []
    slugs = set()
    primaries = 0
    for i, g in enumerate(games):
        if not isinstance(g, dict) or not is_slug(str(g.get("slug", ""))):
            problems.append(f"games[{i}] needs a slug")
            continue
        slugs.add(g["slug"])
        primaries += g.get("role") == "primary"
    if games and primaries != 1:
        problems.append("exactly one game must have role \"primary\"")
    comps = r.get("components", [])
    ids = set()
    for i, c in enumerate(comps if isinstance(comps, list) else []):
        if not isinstance(c, dict) or not c.get("id") or not c.get("file"):
            problems.append(f"components[{i}] needs id and file")
            continue
        if "/" in c["file"] or "\\" in c["file"] or c["file"] in (".", ".."):
            problems.append(f"components[{i}].file must be a plain file name")
        ids.add(c["id"])
    for i, m in enumerate(r.get("mappings", []) or []):
        if not isinstance(m, dict) or m.get("component") not in ids:
            problems.append(f"mappings[{i}] refers to an unknown component")
            continue
        to = str(m.get("to", ""))
        for name, arg in PLACEHOLDER_RE.findall(to):
            if name not in KNOWN_PLACEHOLDERS:
                problems.append(f"mappings[{i}].to uses unknown placeholder {{{name}}}")
            elif arg and arg not in slugs:
                problems.append(f"mappings[{i}].to refers to game {arg!r} not in games")
        if not PLACEHOLDER_RE.match(to):
            problems.append(f"mappings[{i}].to must start with a placeholder like {{game}}")
        if ".." in PurePosixPath(to.replace("\\", "/")).parts or ".." in PurePosixPath(str(m.get("from", ""))).parts:
            problems.append(f"mappings[{i}] may not use '..'")
    for i, s in enumerate(r.get("settings", []) or []):
        if not isinstance(s, dict) or not all(s.get(k) for k in ("file", "section", "key")) or "value" not in s:
            problems.append(f"settings[{i}] needs file, section, key and value")
    cover = r.get("cover")
    if cover is not None and (not isinstance(cover, str) or "/" in cover or "\\" in cover
                              or not cover.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))):
        problems.append('"cover" must be an image file name in the package (jpg, png or webp)')
    launch = r.get("launch") or {}
    if launch.get("game") and launch["game"] not in slugs:
        problems.append("launch.game must be one of the recipe's games")
    return problems


def primary_slug(r: dict) -> str:
    for g in r.get("games", []):
        if g.get("role") == "primary":
            return g["slug"]
    return r["games"][0]["slug"]


# ---- choosing games ---------------------------------------------------------------------------

def candidates(r: dict, games: List[Game], env: HostEnv) -> Dict[str, List[Game]]:
    """For each recipe slug, installed games that satisfy it (PC stores, then device targets)."""
    from .stores import find_games
    out: Dict[str, List[Game]] = {}
    for g in r.get("games", []):
        slug = g["slug"]
        found = find_games(games, slug)
        for key, target in TARGET_KEYS.items():
            if g.get(key):
                from . import targets
                mod = targets.module(target)
                if target == "switch":
                    sg = mod.game_for_title(env, g[key], g.get("title", ""))
                    found += [sg] if sg else []
                else:
                    found += mod.find(env, g[key])
        if isinstance(g.get("emulator"), dict):
            from .targets import emulators
            eg = emulators.game_for(env, g["emulator"])
            found += [eg] if eg else []
        plats = g.get("platforms")
        if plats:
            found = [x for x in found if x.platform in plats or x.runner in plats]
        out[slug] = found
    return out


def choose(r: dict, games: List[Game], env: HostEnv, choices: Optional[Dict[str, str]] = None
           ) -> Tuple[Dict[str, Game], List[str]]:
    """Pick one game per slug (user choice by key, else the first match). Returns (games, missing)."""
    choices = choices or {}
    picked: Dict[str, Game] = {}
    missing: List[str] = []
    for slug, found in candidates(r, games, env).items():
        entry = next(g for g in r["games"] if g["slug"] == slug)
        want = choices.get(slug)
        g = next((x for x in found if x.key == want), None) if want else (found[0] if found else None)
        if g is None:
            if not entry.get("optional"):
                missing.append(slug)
            continue
        picked[slug] = g
    return picked, missing


def version_problems(r: dict, picked: Dict[str, Game]) -> List[str]:
    out = []
    for entry in r.get("games", []):
        g = picked.get(entry["slug"])
        if g and entry.get("version") and version_ok(g.version, entry["version"]) is False:
            out.append(f"{g.title} {g.version} doesn't meet {entry['version']}")
    return out


# ---- placeholders -----------------------------------------------------------------------------

def proton_drive_c(g: Game) -> Optional[Path]:
    pfx = g.extra.get("prefix")
    return Path(pfx) / "drive_c" if pfx and g.runner == "proton" else None


def context(r: dict, picked: Dict[str, Game], env: HostEnv, backend: str = "") -> Dict[str, object]:
    """Values for every placeholder this install can resolve."""
    primary = picked.get(primary_slug(r))
    ctx: Dict[str, object] = {"home": env.home, "data": data_dir(env) / "mashups" / r["id"] / "data",
                              "appdata": appdata_dir(env)}
    for slug, g in picked.items():
        if g.install_dir:
            ctx[f"game:{slug}"] = g.install_dir
    if primary is not None:
        if primary.install_dir:
            ctx["game"] = primary.install_dir
        drive_c = proton_drive_c(primary)
        if drive_c:
            ctx["proton_prefix"] = drive_c
            ctx["proton_appdata"] = drive_c / "users" / "steamuser" / "AppData" / "Roaming"
            ctx["appdata"] = ctx["proton_appdata"]   # a Windows game under Proton keeps its data there
        if primary.store == "switch":
            from .targets import switch
            roots = primary.extra.get("mod_roots", [])
            kind = backend or (roots[0]["kind"] if roots else "")
            if kind:
                ctx["switch_mod"] = switch.mod_root(primary, kind, r["id"])
        elif primary.store == "android":
            serial = primary.extra["serial"]
            from .targets import android
            for k, v in android.placeholders(primary).items():
                ctx[k] = f"device:{serial}:{v}"
        elif primary.store == "emulator":
            from .targets import emulators
            ctx.update(emulators.paths(primary, r["id"], backend))
        elif primary.store == "ios":
            ctx["ios_documents"] = f"afc:{primary.extra['udid']}:{primary.store_id}:"
    return ctx


def resolve(text: str, ctx: Dict[str, object]) -> Optional[str]:
    """Replace placeholders; None when one can't be resolved for this install."""
    missing = []

    def sub(m):
        key = m.group(1) + (":" + m.group(2) if m.group(2) else "")
        if key not in ctx:
            missing.append(key)
            return ""
        return str(ctx[key])
    out = PLACEHOLDER_RE.sub(sub, text)
    if missing:
        return None
    if out.startswith(("device:", "afc:")):
        return out.replace("\\", "/")
    return str(Path(out))


def when_matches(when: Optional[dict], picked: Dict[str, Game], r: dict, env: HostEnv) -> bool:
    if not when:
        return True
    primary = picked.get(primary_slug(r))
    facts = {"host": env.os, "platform": primary.platform if primary else "", "runner": primary.runner if primary else "",
             "store": primary.store if primary else ""}
    for k, v in when.items():
        vals = v if isinstance(v, list) else [v]
        if facts.get(k) not in vals:
            return False
    return True
