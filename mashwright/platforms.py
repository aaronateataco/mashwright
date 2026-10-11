"""The host Mashwright runs on: OS, home, environment, and injectable helpers.

Every detector takes a HostEnv instead of reading os.environ / sys.platform itself, so tests can
point it at a fake directory tree and fake command output.
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Mapping, Optional, Tuple


def default_run(cmd: List[str], timeout: float = 20.0) -> Tuple[int, str]:
    """Run a command and return (exit code, stdout+stderr text). Never raises."""
    try:
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, **kwargs)
        return p.returncode, p.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def _windows_reg(hive: str, key: str, value: str) -> Optional[str]:
    try:
        import winreg  # type: ignore
    except ImportError:
        return None
    hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
    for view in (0, getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0)):
        try:
            with winreg.OpenKey(hives[hive], key, 0, winreg.KEY_READ | view) as k:
                v, _t = winreg.QueryValueEx(k, value)
                return str(v)
        except OSError:
            continue
    return None


def _windows_reg_subkeys(hive: str, key: str) -> List[str]:
    try:
        import winreg  # type: ignore
    except ImportError:
        return []
    hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
    for view in (0, getattr(winreg, "KEY_WOW64_32KEY", 0), getattr(winreg, "KEY_WOW64_64KEY", 0)):
        try:
            with winreg.OpenKey(hives[hive], key, 0, winreg.KEY_READ | view) as k:
                out = []
                i = 0
                while True:
                    try:
                        out.append(winreg.EnumKey(k, i))
                    except OSError:
                        break
                    i += 1
                return out
        except OSError:
            continue
    return []


@dataclass(frozen=True)
class HostEnv:
    os: str                     # "windows" | "linux" | "macos"
    home: Path
    environ: Mapping[str, str]
    # (hive "HKCU"/"HKLM", key path, value name) -> str | None. None on non-Windows hosts and in tests.
    reg: Optional[Callable[[str, str, str], Optional[str]]] = None
    # (hive, key path) -> list of subkey names.
    reg_subkeys: Optional[Callable[[str, str], List[str]]] = None
    run: Callable[[List[str], float], Tuple[int, str]] = default_run
    which: Callable[[str], Optional[str]] = shutil.which
    # Extra roots to scan for removable volumes (SD cards); tests set this.
    volumes: Optional[Tuple[Path, ...]] = None

    def env(self, name: str, default: str = "") -> str:
        return self.environ.get(name, default) or default


def host_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def current() -> HostEnv:
    o = host_os()
    return HostEnv(
        os=o,
        home=Path.home(),
        environ=dict(os.environ),
        reg=_windows_reg if o == "windows" else None,
        reg_subkeys=_windows_reg_subkeys if o == "windows" else None,
    )


def _xdg(env: HostEnv, var: str, fallback: str) -> Path:
    v = env.env(var)
    return Path(v) if v else env.home / fallback


def data_dir(env: HostEnv) -> Path:
    """Where Mashwright keeps its library, journals and backups."""
    if env.os == "windows":
        return Path(env.env("APPDATA", str(env.home / "AppData" / "Roaming"))) / "Mashwright"
    if env.os == "macos":
        return env.home / "Library" / "Application Support" / "Mashwright"
    return _xdg(env, "XDG_DATA_HOME", ".local/share") / "mashwright"


def config_dir(env: HostEnv) -> Path:
    if env.os == "windows":
        return Path(env.env("APPDATA", str(env.home / "AppData" / "Roaming"))) / "Mashwright"
    if env.os == "macos":
        return env.home / "Library" / "Application Support" / "Mashwright"
    return _xdg(env, "XDG_CONFIG_HOME", ".config") / "mashwright"


def appdata_dir(env: HostEnv) -> Path:
    """The per-user app data folder a native game on this host would use."""
    if env.os == "windows":
        return Path(env.env("APPDATA", str(env.home / "AppData" / "Roaming")))
    if env.os == "macos":
        return env.home / "Library" / "Application Support"
    return _xdg(env, "XDG_DATA_HOME", ".local/share")


def xdg_config_home(env: HostEnv) -> Path:
    return _xdg(env, "XDG_CONFIG_HOME", ".config")


def removable_volumes(env: HostEnv) -> List[Path]:
    """Mounted volumes that might be an SD card (Switch Atmosphère card etc.)."""
    if env.volumes is not None:
        return list(env.volumes)
    out: List[Path] = []
    try:
        if env.os == "windows":
            for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
                p = Path(f"{letter}:/")
                if p.exists():
                    out.append(p)
        elif env.os == "macos":
            vols = Path("/Volumes")
            if vols.is_dir():
                out += [p for p in vols.iterdir() if p.is_dir()]
        else:
            user = env.env("USER") or env.home.name
            for base in (Path("/run/media") / user, Path("/media") / user, Path("/media"), Path("/mnt")):
                if base.is_dir():
                    out += [p for p in base.iterdir() if p.is_dir()]
    except OSError:
        pass
    return out
