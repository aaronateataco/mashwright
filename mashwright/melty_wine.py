"""Run the official Melty app on Linux through Wine, the way Lutris or Bottles run any Windows app.

Mashwright doesn't ship, change or look inside Melty: it downloads the official installer from
melty.gg (the same link as the site's Download button), installs it into a Wine prefix of its own,
and starts it. Melty then works as it does on Windows, signing in and talking to Melty itself.
Mashwright also:
  - shows Melty your Linux Steam libraries (a small Steam folder inside the prefix whose
    libraryfolders.vdf lists your real libraries by their Wine paths, and the matching registry keys),
  - forwards melty:// links (sign-in, invites) from your desktop to it,
  - adds an app-menu entry.
Melty is a product of Stella Montis Inc.; Melty doesn't support Linux, and this isn't affiliated
with or endorsed by them.
"""

import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import List, Optional

from . import __version__
from .model import MashwrightError
from .platforms import HostEnv, data_dir

log = logging.getLogger(__name__)

INSTALLER_URL = "https://melty.gg/api/desktop/download"
# A self-contained 64-bit Wine (no 32-bit system libraries needed), used when the system has none.
PORTABLE_WINE_URL = ("https://github.com/Kron4ek/Wine-Builds/releases/download/11.19/"
                     "wine-11.19-staging-amd64-wow64.tar.xz")
PORTABLE_WINE_DIR = "wine-11.19-staging-amd64-wow64"
APP_ID = "io.github.mashwright.MeltyWine"
UA = f"Mashwright/{__version__}"


def home(env: HostEnv) -> Path:
    return data_dir(env) / "melty-wine"


def prefix(env: HostEnv) -> Path:
    return home(env) / "prefix"


def melty_exe(env: HostEnv) -> Path:
    user = env.env("USER") or env.home.name
    return prefix(env) / "drive_c" / "users" / user / "AppData" / "Local" / "Programs" / "melty" / "Melty.exe"


def wine(env: HostEnv) -> Optional[str]:
    """System Wine, or the portable one Mashwright downloaded."""
    portable = home(env) / PORTABLE_WINE_DIR / "bin" / "wine"
    if portable.is_file():
        return str(portable)
    return env.which("wine")


def _wine_env(env: HostEnv) -> dict:
    e = dict(os.environ)
    e.update({"WINEPREFIX": str(prefix(env)), "WINEDEBUG": "-all", "WINEDLLOVERRIDES": "mscoree,mshtml="})
    return e


def status(env: HostEnv) -> dict:
    return {"supported": env.os == "linux", "wine": wine(env), "installed": melty_exe(env).is_file(),
            "prefix": str(prefix(env)), "handler": (_apps_dir(env) / f"{APP_ID}.desktop").is_file()}


def _download(url: str, dest: Path, progress, label: str, lo: float, hi: float) -> None:
    if not url.startswith("https://"):
        raise MashwrightError("Only https downloads are allowed")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as out:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    progress(label, lo + (hi - lo) * done / total)
    except OSError as e:
        raise MashwrightError(f"Download failed ({url}): {e}")


def _get_portable_wine(env: HostEnv, progress) -> str:
    target = home(env)
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(target)) as td:
        tar = Path(td) / "wine.tar.xz"
        _download(PORTABLE_WINE_URL, tar, progress, "Downloading Wine", 0.02, 0.3)
        progress("Unpacking Wine", 0.32)
        with tarfile.open(tar) as t:
            root = target.resolve()
            for m in t.getmembers():
                dest = (target / m.name).resolve()
                if root not in dest.parents and dest != root:
                    raise MashwrightError("Unsafe path in the Wine archive")
                if m.issym() or m.islnk():
                    link = (dest.parent / m.linkname).resolve()
                    if root not in link.parents:
                        raise MashwrightError("Unsafe link in the Wine archive")
            t.extractall(target)
    return str(target / PORTABLE_WINE_DIR / "bin" / "wine")


def _run(env: HostEnv, args: List[str], timeout: float) -> int:
    try:
        return subprocess.run(args, env=_wine_env(env), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        return 124
    except OSError as e:
        raise MashwrightError(f"Couldn't run Wine: {e}")


def setup(env: HostEnv, progress=None) -> dict:
    """Get Wine if needed, install the official Melty app into Mashwright's prefix, and link it up."""
    progress = progress or (lambda m, f: None)
    if env.os != "linux":
        raise MashwrightError("Melty runs natively on Windows; this helper is for Linux")
    w = wine(env) or _get_portable_wine(env, progress)
    if not melty_exe(env).is_file():
        progress("Preparing Wine", 0.35)
        prefix(env).mkdir(parents=True, exist_ok=True)
        _run(env, [str(Path(w).with_name("wineboot")), "-i"], 300)
        installer = home(env) / "Melty-Setup.exe"
        _download(INSTALLER_URL, installer, progress, "Downloading Melty from melty.gg", 0.4, 0.7)
        with open(installer, "rb") as f:
            if f.read(2) != b"MZ":
                raise MashwrightError("melty.gg didn't return a Windows installer")
        progress("Installing Melty", 0.75)
        _run(env, [w, str(installer), "/S"], 600)
        if not melty_exe(env).is_file():
            raise MashwrightError("Melty's installer didn't finish; try again, or check Wine works")
    progress("Showing Melty your Steam games", 0.9)
    link_steam(env)
    desktop_integration(env)
    progress("Melty is ready", 1.0)
    return status(env)


def map_libraries(env: HostEnv, libs) -> list:
    """(library, Windows path) pairs. Libraries outside your home folder get their own drive letter
    (G: onwards, like a Windows games drive): mount names such as "usb-Disk-0:0-part1" contain
    characters Windows programs can't use in a path."""
    dosdevices = prefix(env) / "dosdevices"
    dosdevices.mkdir(parents=True, exist_ok=True)
    letters = iter("ghijklmnopqrstuvwxy")
    out = []
    for lib in libs:
        lib = Path(lib)
        if env.home in lib.parents and ":" not in str(lib):
            out.append((lib, to_wine_path(lib)))
            continue
        # Map the drive the library sits on (its mount point), so it reads like Windows: G:\SteamLibrary.
        target, rest = lib, ""
        if lib.parent != lib and os.path.ismount(str(lib.parent)) and ":" not in lib.name:
            target, rest = lib.parent, lib.name
        existing = None
        for d in dosdevices.iterdir():
            if d.is_symlink() and len(d.name) == 2 and d.name[1] == ":" and d.name[0] in "ghijklmnopqrstuvwxy" \
                    and Path(os.readlink(d)) in (target, lib):
                if Path(os.readlink(d)) != target:
                    d.unlink()
                    continue
                existing = d.name
        if existing is None:
            for letter in letters:
                d = dosdevices / f"{letter}:"
                if not d.exists() and not d.is_symlink():
                    d.symlink_to(target)
                    existing = d.name
                    break
        out.append((lib, existing.upper() + "\\" + rest if existing else to_wine_path(lib)))
    return out


def to_wine_path(p) -> str:
    return "Z:" + str(p).replace("/", "\\")


def link_steam(env: HostEnv) -> None:
    """A Steam folder inside the prefix listing your real Linux Steam libraries by their Wine paths."""
    from .stores import steam
    libs = steam.libraries(env)
    if not libs:
        return
    shadow = prefix(env) / "drive_c" / "Program Files (x86)" / "Steam"
    (shadow / "steamapps").mkdir(parents=True, exist_ok=True)
    lines = ['"libraryfolders"', "{"]
    for i, (lib, win) in enumerate(map_libraries(env, libs)):
        lines += [f'\t"{i}"', "\t{", f'\t\t"path"\t\t"{win}"'.replace("\\", "\\\\"), "\t}"]
    lines.append("}")
    (shadow / "steamapps" / "libraryfolders.vdf").write_text("\n".join(lines) + "\n", encoding="utf-8")
    w = wine(env)
    if not w:
        return
    reg = str(Path(w).with_name("wine"))
    for key, name, value in (
            (r"HKCU\Software\Valve\Steam", "SteamPath", "c:/program files (x86)/steam"),
            (r"HKCU\Software\Valve\Steam", "SteamExe", "c:/program files (x86)/steam/steam.exe"),
            (r"HKLM\Software\Wow6432Node\Valve\Steam", "InstallPath", r"C:\Program Files (x86)\Steam"),
            (r"HKLM\Software\Valve\Steam", "InstallPath", r"C:\Program Files (x86)\Steam")):
        _run(env, [reg, "reg", "add", key, "/v", name, "/t", "REG_SZ", "/d", value, "/f"], 60)


def _apps_dir(env: HostEnv) -> Path:
    base = Path(env.env("XDG_DATA_HOME")) if env.env("XDG_DATA_HOME") else env.home / ".local" / "share"
    return base / "applications"


def desktop_integration(env: HostEnv) -> None:
    """App-menu entry for Melty (via Wine) that also handles melty:// links."""
    import sys
    entry = _apps_dir(env) / f"{APP_ID}.desktop"
    entry.parent.mkdir(parents=True, exist_ok=True)
    main = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0].endswith("mashwright.py") else None
    exe = f'python3 "{main}"' if main else "mashwright"
    entry.write_text(
        "[Desktop Entry]\nType=Application\nName=Melty (via Wine)\n"
        "Comment=The official Melty app, run with Wine by Mashwright\n"
        f"Exec={exe} melty open %u\nIcon=wine\nTerminal=false\nCategories=Game;\n"
        "MimeType=x-scheme-handler/melty;\nNoDisplay=false\n", encoding="utf-8")
    if env.which("update-desktop-database"):
        env.run(["update-desktop-database", str(entry.parent)], 20)
    if env.which("xdg-mime"):
        env.run(["xdg-mime", "default", entry.name, "x-scheme-handler/melty"], 20)


def open_melty(env: HostEnv, url: str = "") -> str:
    if not melty_exe(env).is_file():
        raise MashwrightError("Set up Melty first (mashwright melty setup)")
    w = wine(env)
    if not w:
        raise MashwrightError("Wine is missing; run mashwright melty setup again")
    args = [w, str(melty_exe(env))]
    if url:
        if not url.startswith("melty://"):
            raise MashwrightError("Only melty:// links are passed to Melty")
        args.append(url)
    subprocess.Popen(args, env=_wine_env(env), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return "Opening Melty"


def remove(env: HostEnv) -> None:
    entry = _apps_dir(env) / f"{APP_ID}.desktop"
    if entry.exists():
        entry.unlink()
    if prefix(env).exists():
        w = wine(env)
        if w:
            _run(env, [str(Path(w).with_name("wineserver")), "-k"], 30)
        shutil.rmtree(prefix(env), ignore_errors=True)
