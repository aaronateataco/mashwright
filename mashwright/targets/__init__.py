"""Non-PC targets: Nintendo Switch (emulator mod folders, Atmosphère SD cards), Android (adb) and
iOS (apps that share their Documents folder). Mashwright only places mod files where the player's own,
already-working setup loads them; it never touches keys, firmware, game dumps or app encryption.
"""

import importlib
import logging
from typing import List

from ..model import Game
from ..platforms import HostEnv

log = logging.getLogger(__name__)

TARGETS = ["switch", "android", "ios", "emulators"]


def module(store: str):
    """The target module for a Game.store (switch/android/ios)."""
    name = "emulators" if store == "emulator" else store
    if name not in TARGETS:
        raise KeyError(store)
    return importlib.import_module(f"{__name__}.{name}")


def detect_all_targets(env: HostEnv) -> List[Game]:
    out: List[Game] = []
    for name in TARGETS:
        try:
            out += module(name).detect(env)
        except Exception as e:
            log.warning("target %s failed: %s", name, e)
    return out
