"""Start a game the way its store or platform expects."""

import os
import subprocess
from pathlib import Path
from typing import Callable, List, Optional

from .model import Game, MashwrightError
from .platforms import HostEnv


def open_url(url: str, env: HostEnv, opener: Optional[Callable[[List[str]], None]] = None) -> None:
    """Hand a URL (steam://, heroic://, lutris:...) to the desktop."""
    if env.os == "windows" and opener is None:
        os.startfile(url)  # type: ignore[attr-defined]
        return
    if env.os == "macos":
        cmd = ["open", url]
    else:
        cmd = ["xdg-open", url] if env.which("xdg-open") else ["gio", "open", url]
    (opener or _spawn)(cmd)


def _spawn(cmd: List[str], cwd: Optional[str] = None) -> None:
    try:
        subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=os.name != "nt")
    except OSError as e:
        raise MashwrightError(f"Couldn't start {cmd[0]}: {e}")


def launch(game: Game, env: HostEnv, args: Optional[List[str]] = None,
           opener: Optional[Callable[[List[str]], None]] = None) -> str:
    """Start the game; returns a short description of what was done."""
    spawn = opener or _spawn
    if game.store == "android":
        pkg = game.launch.get("package") or game.store_id
        spawn(["adb", "-s", game.extra["serial"], "shell", "monkey", "-p", pkg,
               "-c", "android.intent.category.LAUNCHER", "1"])
        return f"Starting {pkg} on the device"
    if game.store == "ios":
        raise MashwrightError(f"Open {game.title} on your iPhone/iPad to play")
    if game.store == "emulator":
        from .targets import emulators
        cmds = emulators.commands(env, game.extra.get("system", ""))
        if not cmds:
            raise MashwrightError(f"Start {game.title} from your emulator")
        spawn(cmds[0])
        return "Started the emulator: pick the game there"
    if game.store == "switch":
        from .targets import switch
        cmds = switch.emulator_commands(env)
        if not cmds:
            raise MashwrightError("Start the game from your emulator, or put the SD card back in your Switch")
        spawn(cmds[0])
        return "Started the emulator: pick the game there"
    url = game.launch.get("url")
    if url:
        open_url(url, env, opener)
        return f"Opened {url}"
    exe = game.launch.get("exe")
    if exe and game.install_dir:
        path = Path(game.install_dir) / exe
        cmd = [str(path)] + list(args or [])
        if game.platform == "windows" and env.os != "windows":
            if not env.which("wine"):
                raise MashwrightError("This is a Windows game: install Wine, or add it to Steam/Heroic/Lutris to use Proton")
            cmd = ["wine"] + cmd
        elif env.os == "macos" and path.suffix == ".app":
            cmd = ["open", str(path)]
        spawn(cmd) if opener else _spawn(cmd, cwd=str(game.install_dir))
        return f"Started {path.name}"
    raise MashwrightError(f"Don't know how to start {game.title}; start it from its launcher")
