#!/usr/bin/env python3
"""Build DogDesk: the GNOME extension zip (as GNOME's own `gnome-extensions pack` would lay it out)
and the dogdesk.mashwright package.

usage: python3 tools/build.py
"""
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXT = os.path.join(ROOT, "dogdesk@aaronateataco.github.io")
PKG = os.path.join(ROOT, "package")

subprocess.run(["glib-compile-schemas", os.path.join(EXT, "schemas")], check=True)
zpath = os.path.join(PKG, "dogdesk-extension.zip")
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    for dirpath, _dirs, files in os.walk(EXT):
        for f in sorted(files):
            full = os.path.join(dirpath, f)
            z.write(full, os.path.relpath(full, EXT))
print("wrote", zpath)
mw = os.path.join(ROOT, "..", "..", "mashwright.py")
out = os.path.join(ROOT, "build", "dogdesk.mashwright")
os.makedirs(os.path.dirname(out), exist_ok=True)
subprocess.run([sys.executable, mw, "pack", PKG, "-o", out], check=True)
