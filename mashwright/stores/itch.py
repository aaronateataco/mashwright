"""itch.io app: installed games from butler's database (best effort; the schema changes between
versions, so every query is defensive)."""

import json
import logging
import sqlite3
from pathlib import Path
from typing import List

from ..model import Game
from ..platforms import HostEnv, xdg_config_home

log = logging.getLogger(__name__)

STORE = "itch"


def database(env: HostEnv) -> Path:
    if env.os == "windows":
        return Path(env.env("APPDATA", str(env.home / "AppData" / "Roaming"))) / "itch" / "db" / "butler.db"
    if env.os == "macos":
        return env.home / "Library" / "Application Support" / "itch" / "db" / "butler.db"
    return xdg_config_home(env) / "itch" / "db" / "butler.db"


def detect(env: HostEnv) -> List[Game]:
    db = database(env)
    if not db.is_file():
        return []
    out: List[Game] = []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            locs = {}
            try:
                for lid, path in con.execute("SELECT id, path FROM install_locations"):
                    locs[lid] = path
            except sqlite3.Error:
                pass
            try:
                rows = con.execute("SELECT c.id, c.game_id, c.install_folder_name, c.install_location_id, g.title "
                                   "FROM caves c LEFT JOIN games g ON g.id = c.game_id").fetchall()
            except sqlite3.Error:
                rows = []
            for cave, gid, folder, loc, title in rows:
                base = locs.get(loc)
                if not base or not folder:
                    continue
                path = Path(base) / "apps" / folder
                if not path.is_dir():
                    path = Path(base) / folder
                if not path.is_dir():
                    continue
                out.append(Game(key=f"itch:{gid}", store=STORE, store_id=str(gid), title=title or folder,
                                install_dir=path, platform=env.os, launch={"url": f"itch://caves/{cave}/launch"}))
        finally:
            con.close()
    except sqlite3.Error as e:
        log.warning("itch db unreadable: %s", e)
    return out
