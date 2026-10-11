"""Android games over adb (USB debugging on the player's own device). Mod files are pushed into
shared storage folders a game reads (its Android/data or Android/media folder, or /sdcard paths it
documents). Nothing is rooted, patched or re-signed."""

import logging
import posixpath
import shlex
from typing import Dict, List

from ..model import Game, MashwrightError
from ..platforms import HostEnv

log = logging.getLogger(__name__)

STORE = "android"
ALLOWED_PREFIXES = ("/sdcard/", "/storage/emulated/0/")


def _adb(env: HostEnv) -> str:
    adb = env.which("adb")
    if not adb:
        raise MashwrightError("adb not found. Install Android platform tools "
                             "(Fedora: sudo dnf install android-tools) and enable USB debugging.")
    return adb


def devices(env: HostEnv) -> List[str]:
    if not env.which("adb"):
        return []
    code, text = env.run([_adb(env), "devices"], 15.0)
    if code != 0:
        return []
    out = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            out.append(parts[0])
    return out


def packages(env: HostEnv, serial: str) -> List[str]:
    code, text = env.run([_adb(env), "-s", serial, "shell", "pm", "list", "packages"], 20.0)
    if code != 0:
        return []
    return sorted({l.strip()[len("package:"):] for l in text.splitlines() if l.strip().startswith("package:")})


def detect(env: HostEnv) -> List[Game]:
    """Connected devices only (as placeholders); games are looked up per recipe with find()."""
    return []


def find(env: HostEnv, package: str) -> List[Game]:
    out = []
    for serial in devices(env):
        if package in packages(env, serial):
            out.append(Game(key=f"android:{serial}:{package}", store=STORE, store_id=package, title=package,
                            install_dir=None, platform="android", runner="device",
                            launch={"package": package}, extra={"serial": serial}))
    return out


def _check_path(path: str) -> str:
    p = posixpath.normpath(path)
    if not p.startswith(ALLOWED_PREFIXES) or ".." in p.split("/"):
        raise MashwrightError(f"Refusing to write outside shared storage on the device: {path}")
    return p


def place(game: Game, device_path: str, local_file: str, env: HostEnv) -> None:
    dest = _check_path(device_path)
    serial = game.extra["serial"]
    code, _ = env.run([_adb(env), "-s", serial, "shell", "mkdir", "-p", shlex.quote(posixpath.dirname(dest))], 20.0)
    code, text = env.run([_adb(env), "-s", serial, "push", local_file, dest], 300.0)
    if code != 0:
        hint = (" Android 11+ blocks other apps' Android/data folders over adb on some devices; "
                "use the mod folder the game documents instead.") if "/Android/data/" in dest else ""
        raise MashwrightError(f"adb push to {dest} failed: {text.strip()[-200:]}.{hint}")


def remove(game: Game, device_path: str, env: HostEnv) -> None:
    dest = _check_path(device_path)
    env.run([_adb(env), "-s", game.extra["serial"], "shell", "rm", "-f", shlex.quote(dest)], 20.0)


def exists(game: Game, device_path: str, env: HostEnv) -> bool:
    dest = _check_path(device_path)
    code, _ = env.run([_adb(env), "-s", game.extra["serial"], "shell", "ls", shlex.quote(dest)], 20.0)
    return code == 0


def placeholders(game: Game) -> Dict[str, str]:
    pkg = game.store_id
    return {"android_data": f"/sdcard/Android/data/{pkg}/files", "android_media": f"/sdcard/Android/media/{pkg}",
            "sdcard": "/sdcard"}
