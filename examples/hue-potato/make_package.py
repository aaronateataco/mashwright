#!/usr/bin/env python3
"""Build hue-potato.mashwright from Hue Potato's release packages.

usage: python3 make_package.py [path/to/HuePotato/build] [out.mashwright]
Run HuePotato/tools/build.py first. Fills in each component's sha256.
"""
import hashlib
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
build = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "mashups", "hue-potato", "build")
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "hue-potato.mashwright")
recipe = json.load(open(os.path.join(HERE, "mashwright.json"), encoding="utf-8"))
with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
    for c in recipe["components"]:
        src = os.path.join(build, c["file"])
        if not os.path.isfile(src):
            sys.exit(f"missing {src}: run HuePotato/tools/build.py first")
        c["sha256"] = hashlib.sha256(open(src, "rb").read()).hexdigest()
        z.write(src, c["file"])
    if recipe.get("cover"):
        cover = os.path.join(HERE, recipe["cover"])
        if not os.path.isfile(cover):
            sys.exit(f"missing cover image {cover}")
        z.write(cover, recipe["cover"])
    z.writestr("mashwright.json", json.dumps(recipe, indent=2))
print("wrote", out)
