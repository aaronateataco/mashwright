"""Epic Games Store detector: reads the Epic launcher's own install manifests (``*.item`` JSON).

Windows: ``%PROGRAMDATA%\\Epic\\EpicGamesLauncher\\Data\\Manifests``
macOS:   ``~/Library/Application Support/Epic/EpicGamesLauncher/Data/Manifests``

There is no Epic launcher on Linux; Epic games there are found through Heroic (``heroic.py``).
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from ..model import Game, slugify
from ..platforms import HostEnv

log = logging.getLogger(__name__)

STORE = "epic"

# Manifests in these categories (without "games") are engine plugins, DLC and other non-games.
_NON_GAME_CATEGORIES = {"plugins", "engines", "addons"}


def manifest_dirs(env: HostEnv) -> List[Path]:
    """Folders where the Epic launcher keeps one ``.item`` manifest per installed app."""
    if env.os == "windows":
        programdata = env.env("PROGRAMDATA") or env.env("ALLUSERSPROFILE") or "C:\\ProgramData"
        return [Path(programdata) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"]
    if env.os == "macos":
        return [env.home / "Library" / "Application Support" / "Epic" / "EpicGamesLauncher"
                / "Data" / "Manifests"]
    return []


def launch_url(app_name: str, namespace: str = "", item_id: str = "") -> str:
    """The launcher URL that starts an installed Epic app."""
    if namespace and item_id:
        ident = "%3A".join(quote(part, safe="") for part in (namespace, item_id, app_name))
    else:
        ident = quote(app_name, safe="")
    return f"com.epicgames.launcher://apps/{ident}?action=launch&silent=true"


def _read_json(path: Path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return json.load(f)


def _is_game(data: Dict) -> bool:
    """False for DLC, engine plugins and half-finished installs."""
    if data.get("bIsIncompleteInstall"):
        return False
    app_name = str(data.get("AppName") or "")
    main_app = str(data.get("MainGameAppName") or "")
    if main_app and main_app != app_name:
        return False  # DLC / add-on of another game
    cats = data.get("AppCategories")
    if isinstance(cats, list):
        cats = {str(c).lower() for c in cats}
        if "games" not in cats and cats & _NON_GAME_CATEGORIES:
            return False
    return True


def parse_manifest(data: Dict, env: HostEnv, source: Optional[Path] = None) -> Optional[Game]:
    """Turn one manifest's JSON into a Game, or None if it is not a usable installed game."""
    if not isinstance(data, dict) or not _is_game(data):
        return None
    app_name = str(data.get("AppName") or "").strip()
    location = str(data.get("InstallLocation") or "").strip()
    if not app_name or not location:
        return None
    install_dir = Path(location)
    if not install_dir.is_dir():
        log.debug("epic: %s install folder missing: %s", app_name, install_dir)
        return None
    title = str(data.get("DisplayName") or "").strip() or app_name
    namespace = str(data.get("CatalogNamespace") or "").strip()
    item_id = str(data.get("CatalogItemId") or "").strip()
    extra = {"app_name": app_name, "catalog_namespace": namespace, "catalog_item_id": item_id}
    exe = str(data.get("LaunchExecutable") or "").strip()
    if exe:
        extra["exe"] = str(install_dir / exe)
    if source is not None:
        extra["manifest"] = str(source)
    return Game(
        key=f"{STORE}:{app_name}",
        store=STORE,
        store_id=app_name,
        title=title,
        install_dir=install_dir,
        platform=env.os,  # the launcher only installs builds for the host it runs on
        runner="native",
        launch={"url": launch_url(app_name, namespace, item_id), "app_name": app_name},
        extra=extra,
        slugs=[slugify(title)],
        version=str(data.get("AppVersionString") or ""),
    )


def _detect(env: HostEnv) -> List[Game]:
    games: Dict[str, Game] = {}
    for folder in manifest_dirs(env):
        if not folder.is_dir():
            continue
        for item in sorted(folder.glob("*.item")):
            try:
                game = parse_manifest(_read_json(item), env, item)
            except (OSError, ValueError) as e:
                log.warning("epic: skipping unreadable manifest %s: %s", item, e)
                continue
            if game and game.key not in games:
                games[game.key] = game
    return list(games.values())


def detect(env: HostEnv) -> List[Game]:
    """Installed Epic Games Store games on this host. Never raises."""
    try:
        return _detect(env)
    except Exception as e:  # a detector must never take the app down
        log.warning("epic: detection failed: %s", e)
        return []
