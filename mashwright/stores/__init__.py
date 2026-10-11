"""Game stores: each module exposes detect(env) -> list[Game] and never raises."""

import importlib
import logging
from typing import Dict, List

from ..model import Game, slugify
from ..platforms import HostEnv

log = logging.getLogger(__name__)

DETECTORS = ["steam", "epic", "gog", "heroic", "lutris", "itch", "custom"]

# Recipe slug -> store keys known to be that game (title slugs are matched too).
KNOWN_GAMES: Dict[str, List[str]] = {
    "brotato": ["steam:1942280"],
    "hue": ["steam:383270"],
    "hollow-knight": ["steam:367520"],
    "stardew-valley": ["steam:413150"],
    "undertale": ["steam:391540"],
    "ultrakill": ["steam:1229490"],
    "skyrim-special-edition": ["steam:489830"],
    "terraria": ["steam:105600"],
}

_REVERSE = {key: slug for slug, keys in KNOWN_GAMES.items() for key in keys}


def detect_all(env: HostEnv) -> List[Game]:
    """Every installed game from every store module, de-duplicated by key, with slugs filled."""
    games: Dict[str, Game] = {}
    for name in DETECTORS:
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except Exception as e:
            log.warning("store %s unavailable: %s", name, e)
            continue
        try:
            found = mod.detect(env)
        except Exception as e:
            log.warning("store %s failed: %s", name, e)
            continue
        for g in found:
            games.setdefault(g.key, g)
    for g in games.values():
        add_slugs(g)
    return sorted(games.values(), key=lambda g: (g.title.lower(), g.key))


def add_slugs(g: Game) -> None:
    for s in ([_REVERSE[g.key]] if g.key in _REVERSE else []) + [slugify(g.title)]:
        if s not in g.slugs:
            g.slugs.append(s)


def find_games(games: List[Game], slug: str) -> List[Game]:
    """Installed games that satisfy a recipe slug (known ids first, then title matches)."""
    exact = [g for g in games if g.key in KNOWN_GAMES.get(slug, [])]
    rest = [g for g in games if g not in exact and slug in g.slugs]
    return exact + rest
