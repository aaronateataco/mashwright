"""iOS games on the player's own iPhone/iPad, through libimobiledevice. Only apps that share their
Documents folder (iTunes/Finder file sharing) can take files, and only there. No jailbreak, no
decryption, no re-signing. Needs Linux or macOS with libimobiledevice and ifuse."""

import logging
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Dict, List

from ..model import Game, MashwrightError
from ..platforms import HostEnv

log = logging.getLogger(__name__)

STORE = "ios"


def _require(env: HostEnv) -> None:
    if env.os == "windows":
        raise MashwrightError("iOS needs Linux or macOS with libimobiledevice and ifuse "
                             "(Fedora: sudo dnf install libimobiledevice-utils ifuse).")
    for tool in ("idevice_id", "ifuse"):
        if not env.which(tool):
            raise MashwrightError(f"{tool} not found (Fedora: sudo dnf install libimobiledevice-utils ifuse).")


def devices(env: HostEnv) -> List[str]:
    if env.os == "windows" or not env.which("idevice_id"):
        return []
    code, text = env.run(["idevice_id", "-l"], 15.0)
    return [l.strip() for l in text.splitlines() if l.strip()] if code == 0 else []


def apps(env: HostEnv, udid: str) -> Dict[str, str]:
    """bundle id -> name of user apps."""
    if not env.which("ideviceinstaller"):
        return {}
    out: Dict[str, str] = {}
    for cmd in (["ideviceinstaller", "-u", udid, "list", "--user"], ["ideviceinstaller", "-u", udid, "-l", "-o", "list_user"]):
        code, text = env.run(cmd, 30.0)
        if code != 0:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.lower().startswith(("total", "cfbundleidentifier")):
                continue
            parts = [p.strip().strip('"') for p in (line.split(",") if "," in line else line.split(" - ", 1))]
            if parts and "." in parts[0]:
                out[parts[0]] = parts[-1] if len(parts) > 1 else parts[0]
        if out:
            break
    return out


def detect(env: HostEnv) -> List[Game]:
    return []


def find(env: HostEnv, bundle: str) -> List[Game]:
    out = []
    for udid in devices(env):
        names = apps(env, udid)
        if bundle in names:
            out.append(Game(key=f"ios:{udid}:{bundle}", store=STORE, store_id=bundle, title=names[bundle],
                            install_dir=None, platform="ios", runner="device", extra={"udid": udid}))
    return out


def _safe_rel(rel: str) -> PurePosixPath:
    p = PurePosixPath(rel.lstrip("/"))
    if ".." in p.parts:
        raise MashwrightError(f"Bad path for the app's Documents folder: {rel}")
    return p


def _with_documents(game: Game, env: HostEnv, fn):
    _require(env)
    mnt = Path(tempfile.mkdtemp(prefix="mashwright-ios-"))
    code, text = env.run(["ifuse", "-u", game.extra["udid"], "--documents", game.store_id, str(mnt)], 30.0)
    if code != 0:
        mnt.rmdir()
        raise MashwrightError(f"{game.title} doesn't share its Documents folder (or the device is locked): {text.strip()[-200:]}")
    try:
        return fn(mnt)
    finally:
        env.run(["fusermount", "-u", str(mnt)] if env.os == "linux" else ["umount", str(mnt)], 30.0)
        try:
            mnt.rmdir()
        except OSError:
            pass


def place(game: Game, rel_path: str, local_file: str, env: HostEnv) -> None:
    rel = _safe_rel(rel_path)

    def go(mnt: Path):
        dest = mnt.joinpath(*rel.parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_file, dest)
    _with_documents(game, env, go)


def remove(game: Game, rel_path: str, env: HostEnv) -> None:
    rel = _safe_rel(rel_path)
    _with_documents(game, env, lambda mnt: mnt.joinpath(*rel.parts).unlink() if mnt.joinpath(*rel.parts).exists() else None)


def exists(game: Game, rel_path: str, env: HostEnv) -> bool:
    rel = _safe_rel(rel_path)
    return bool(_with_documents(game, env, lambda mnt: mnt.joinpath(*rel.parts).exists()))
