#!/usr/bin/env python3
"""Mashwright: an open-source launcher for game mashups and mods.

    python3 mashwright.py            open the Mashwright window (local web UI)
    python3 mashwright.py list       games found and mashups in your library
    python3 mashwright.py import <file.mashwright | folder>
    python3 mashwright.py install <id> [--game slug=key ...] [--backend ryujinx|yuzu|atmosphere]
    python3 mashwright.py uninstall <id>
    python3 mashwright.py launch <id>
    python3 mashwright.py status <id>
    python3 mashwright.py doctor     what Mashwright can see on this computer
"""

import argparse
import sys

if sys.version_info < (3, 9):
    sys.exit("Mashwright needs Python 3.9 or newer.")

from mashwright import __version__, platforms  # noqa: E402
from mashwright.model import MashwrightError  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mashwright", description="Launcher for game mashups and mods.")
    ap.add_argument("--version", action="version", version=f"Mashwright {__version__}")
    sub = ap.add_subparsers(dest="cmd")
    ui = sub.add_parser("ui", help="open the Mashwright window (default)")
    ui.add_argument("--no-browser", action="store_true", help="only start the server")
    ui.add_argument("--port", type=int, default=0)
    sub.add_parser("list", help="games found and mashups in your library")
    p = sub.add_parser("import", help="add a .mashwright package or a mashup folder")
    p.add_argument("path")
    p = sub.add_parser("install", help="install a mashup into its games")
    p.add_argument("id")
    p.add_argument("--game", action="append", default=[], metavar="SLUG=KEY", help="pick which installed copy to use")
    p.add_argument("--backend", default="", help="Switch: ryujinx, yuzu or atmosphere")
    for name, hlp in (("uninstall", "take a mashup back out"), ("launch", "start a mashup's game"),
                      ("status", "is it installed, have files changed"), ("remove", "delete from your library")):
        sub.add_parser(name, help=hlp).add_argument("id")
    p = sub.add_parser("inspect", help="which platforms a mashup's binaries are for, and how it fits your game")
    p.add_argument("id")
    p.add_argument("--game", action="append", default=[], metavar="SLUG=KEY")
    p = sub.add_parser("catalog", help="mashups in your online catalogs")
    p.add_argument("--refresh", action="store_true")
    p = sub.add_parser("get", help="download a mashup from your catalogs and install it")
    p.add_argument("id")
    p.add_argument("--no-install", action="store_true")
    sub.add_parser("doctor", help="what Mashwright can see on this computer")
    args = ap.parse_args(argv)
    env = platforms.current()
    try:
        return run(args, env)
    except MashwrightError as e:
        print(f"mashwright: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def run(args, env) -> int:
    cmd = args.cmd or "ui"
    if cmd == "ui":
        from mashwright import server
        server.serve(env, open_browser=not getattr(args, "no_browser", False), port=getattr(args, "port", 0))
        return 0
    if cmd == "doctor":
        return doctor(env)
    from mashwright.app import App
    app = App(env)
    if cmd == "list":
        print("Games:")
        for g in app.games:
            extra = "" if g.runner == "native" else f" [{g.runner}]"
            print(f"  {g.key:28} {g.title}{extra}  {g.install_dir or ''}")
        print("\nMashups:")
        for m in app.mashups():
            r = m["recipe"]
            state = "installed" if m["status"]["installed"] else ("ready" if m["ready"] else "needs " + ", ".join(m["missing"]))
            print(f"  {r['id']:28} {r['title']} {r['version']}  ({state})")
        return 0
    if cmd == "import":
        r = app.import_path(args.path)
        print(f"Added {r['title']} {r['version']} ({r['id']})")
        return 0
    if cmd == "install":
        choices = dict(c.split("=", 1) for c in args.game if "=" in c)
        res = app.install(args.id, choices, args.backend,
                          progress=lambda msg, frac: print(f"  {int(frac * 100):3d}% {msg}"))
        print(f"Installed {args.id} ({res['files']} files)")
        return 0
    if cmd == "uninstall":
        for w in app.uninstall(args.id):
            print("  note:", w)
        print(f"Uninstalled {args.id}; the game is back as it was")
        return 0
    if cmd == "launch":
        print(app.launch(args.id))
        return 0
    if cmd == "catalog":
        from mashwright import catalog
        print("Catalogs:", ", ".join(catalog.catalog_urls(env)) or "none configured")
        for e in app.catalog(args.refresh):
            mark = "update available" if e["update"] else ("in your library" if e["in_library"] else "")
            print(f"  {e['id']:24} {e['title']} {e.get('version', '')}  {mark}")
        return 0
    if cmd == "get":
        res = app.get_from_catalog(args.id, not args.no_install,
                                   progress=lambda msg, frac: print(f"  {int(frac * 100):3d}% {msg}"))
        if res.get("missing"):
            print(f"Added {res['recipe']}; install it once you have: {', '.join(res['missing'])}")
        else:
            print(f"Got {res['recipe']}" + ("" if args.no_install else " and installed it"))
        return 0
    if cmd == "inspect":
        fit = app.inspect(args.id, dict(c.split("=", 1) for c in args.game if "=" in c))
        print(f"Fits a {fit['target']} game: {fit['status']}")
        for cid, c in fit["components"].items():
            print(f"  {cid:10} {c['kind']:8} {', '.join(c['platforms']) or 'no binaries'}"
                  + (f"  (per-OS folders: {c['os_folders']})" if c["os_folders"] else ""))
        for n in fit["notes"]:
            print("  note:", n)
        for s in fit["skip"]:
            print("  leaves out:", s)
        for a in fit["advice"]:
            print("  advice:", a)
        return 0
    if cmd == "status":
        from mashwright import installer
        st = installer.status(env, args.id)
        if not st["installed"]:
            print(f"{args.id} is not installed")
        else:
            print(f"{args.id} {st['version']} installed {st['installed_at']}: {st['files']} files")
            for c in st["changed"]:
                print("  changed since install:", c)
        return 0
    if cmd == "remove":
        app.remove(args.id)
        print(f"Removed {args.id} from your library")
        return 0
    return 2


def doctor(env) -> int:
    from mashwright import platforms as pf
    from mashwright.stores import steam, heroic, lutris
    from mashwright.targets import switch
    print(f"Mashwright {__version__} on {env.os} (Python {sys.version.split()[0]})")
    print(f"  data folder:   {pf.data_dir(env)}")
    print(f"  steam roots:   {', '.join(map(str, steam.roots(env))) or 'none'}")
    print(f"  steam libs:    {', '.join(map(str, steam.libraries(env))) or 'none'}")
    print(f"  heroic:        {', '.join(map(str, heroic.config_roots(env))) or 'none'}")
    print(f"  lutris:        {', '.join(map(str, lutris.databases(env))) or 'none'}")
    print(f"  switch:        {', '.join(b['name'] for b in switch.backends(env)) or 'no emulator or Atmosphère card'}")
    from mashwright.targets import emulators
    emus = [f"{emulators.SYSTEM_NAMES[s]}: {e['name']}" for s in emulators.SYSTEM_NAMES for e in emulators.installed(env, s)]
    print(f"  emulators:     {', '.join(dict.fromkeys(emus)) or 'none found'}")
    for tool, why in (("adb", "Android"), ("ideviceinstaller", "iOS app list"), ("ifuse", "iOS files"),
                      ("xdg-open", "opening store links")):
        if env.os == "windows" and tool in ("ifuse", "xdg-open"):
            continue
        print(f"  {tool:14} {'found' if env.which(tool) else 'not found'}  ({why})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
