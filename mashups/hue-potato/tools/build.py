"""Build the three release packages from the project (after gen.py and a clean preflight).

  build/HuePotato-Mod.zip          main:  holds HueBrotato-HuePotato.zip (the Godot Mod Loader zip) -> {game}/mods
  build/HuePotato-Boot.zip         boot:  override.cfg, mods/huepotato_boot.gd -> {game}
  build/HuePotato-vgmstream.zip    tools: huepotato-vgmstream/ -> {game}/mods

usage: python tools/build.py [--dev-install <Brotato dir>]
  --dev-install lays the same files into a local Brotato folder for testing.
"""
import hashlib
import json
import os
import shutil
import sys
import zipfile

from sheets_lib import ROOT

BUILD = os.path.join(ROOT, "build")
MOD_ID = "HueBrotato-HuePotato"


def add_tree(z: zipfile.ZipFile, src: str, prefix: str) -> None:
    for root, _dirs, files in os.walk(src):
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, src).replace(os.sep, "/")
            z.write(full, prefix + rel)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build() -> dict:
    os.makedirs(BUILD, exist_ok=True)
    out = {}

    main = os.path.join(BUILD, MOD_ID + ".zip")
    with zipfile.ZipFile(main, "w", zipfile.ZIP_DEFLATED) as z:
        add_tree(z, os.path.join(ROOT, "mod", "mods-unpacked", MOD_ID), f"mods-unpacked/{MOD_ID}/")
        z.write(os.path.join(ROOT, "README.md"), f"mods-unpacked/{MOD_ID}/README.md")
    # Melty extracts every archive it installs, and Godot Mod Loader needs the mod as a zip in
    # mods/, so the release carries the mod zip inside an outer zip.
    outer = os.path.join(BUILD, "HuePotato-Mod.zip")
    with zipfile.ZipFile(outer, "w", zipfile.ZIP_STORED) as z:
        z.write(main, MOD_ID + ".zip")
    out["main"] = outer

    boot = os.path.join(BUILD, "HuePotato-Boot.zip")
    with zipfile.ZipFile(boot, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(ROOT, "boot", "override.cfg"), "override.cfg")
        z.write(os.path.join(ROOT, "boot", "huepotato_boot.gd"), "mods/huepotato_boot.gd")
    out["boot"] = boot

    tools = os.path.join(BUILD, "HuePotato-vgmstream.zip")
    with zipfile.ZipFile(tools, "w", zipfile.ZIP_DEFLATED) as z:
        add_tree(z, os.path.join(ROOT, "_vendor", "vgmstream-r2117-win64"), "huepotato-vgmstream/")
        add_tree(z, os.path.join(ROOT, "_vendor", "vgmstream-r2117-linux"), "huepotato-vgmstream/linux/")
        add_tree(z, os.path.join(ROOT, "_vendor", "vgmstream-r2117-mac"), "huepotato-vgmstream/macos/")
        z.write(os.path.join(ROOT, "THIRD_PARTY.txt"), "huepotato-vgmstream/THIRD_PARTY.txt")
    out["tools"] = tools

    manifest = {}
    for comp, path in out.items():
        with zipfile.ZipFile(path) as z:
            entries = [{"path": i.filename, "size": i.file_size} for i in z.infolist() if not i.is_dir()]
        manifest[comp] = {"file": os.path.basename(path), "size": os.path.getsize(path), "sha256": sha256(path), "entries": entries}
        print(f"{comp:6} {os.path.basename(path):32} {os.path.getsize(path):>10} bytes  {len(entries)} files")
    with open(os.path.join(BUILD, "packages.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    return out


def dev_install(game: str, out: dict) -> None:
    mods = os.path.join(game, "mods")
    os.makedirs(mods, exist_ok=True)
    for comp, dest in (("main", mods), ("boot", game), ("tools", mods)):
        with zipfile.ZipFile(out[comp]) as z:
            z.extractall(dest)
    print("dev-installed into", game)


if __name__ == "__main__":
    built = build()
    if "--dev-install" in sys.argv:
        dev_install(sys.argv[sys.argv.index("--dev-install") + 1], built)
