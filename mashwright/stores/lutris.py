"""Lutris (Linux): installed games from its sqlite database (~/.local/share/lutris/pga.db, also the
Flatpak location)."""

import logging
import sqlite3
from pathlib import Path
from typing import List

from ..model import Game
from ..platforms import HostEnv

log = logging.getLogger(__name__)

STORE = "lutris"


def databases(env: HostEnv) -> List[Path]:
    if env.os != "linux":
        return []
    data = Path(env.env("XDG_DATA_HOME")) if env.env("XDG_DATA_HOME") else env.home / ".local" / "share"
    cands = [data / "lutris" / "pga.db",
             env.home / ".var" / "app" / "net.lutris.Lutris" / "data" / "lutris" / "pga.db"]
    return [p for p in cands if p.is_file()]


def detect(env: HostEnv) -> List[Game]:
    out: List[Game] = []
    for db in databases(env):
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                cols = {r[1] for r in con.execute("PRAGMA table_info(games)")}
                if not {"id", "name", "directory"} <= cols:
                    continue
                want = ["id", "name", "directory"] + [c for c in ("slug", "runner", "installed") if c in cols]
                for row in con.execute(f"SELECT {', '.join(want)} FROM games"):
                    r = dict(zip(want, row))
                    if "installed" in r and not r["installed"]:
                        continue
                    d = r.get("directory")
                    if not d or not Path(d).is_dir():
                        continue
                    runner = (r.get("runner") or "").lower()
                    platform = "windows" if runner == "wine" else "linux"
                    out.append(Game(key=f"lutris:{r['id']}", store=STORE, store_id=str(r["id"]),
                                    title=r["name"] or str(r["id"]), install_dir=Path(d), platform=platform,
                                    runner="wine" if runner == "wine" else "native",
                                    launch={"url": f"lutris:rungameid/{r['id']}"},
                                    extra={"lutris_slug": r.get("slug") or ""}))
            finally:
                con.close()
        except sqlite3.Error as e:
            log.warning("lutris db %s unreadable: %s", db, e)
    return out
