#!/usr/bin/env python3
"""Add or update a mashup in catalog/index.json from its .mashwright package.

usage: python3 tools/catalog_entry.py PACKAGE.mashwright PACKAGE_URL [--cover-url URL] [--melty URL] [--homepage URL]

PACKAGE_URL is where players download it (normally a GitHub Release asset). The entry's title,
version, authors, description and games come from the package's own mashwright.json.
"""
import argparse
import hashlib
import json
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "..", "catalog", "index.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("package_url")
    ap.add_argument("--cover-url", default="")
    ap.add_argument("--melty", default="")
    ap.add_argument("--homepage", default="")
    a = ap.parse_args()
    data = open(a.package, "rb").read()
    with zipfile.ZipFile(a.package) as z:
        r = json.loads(z.read("mashwright.json"))
    entry = {"id": r["id"], "title": r["title"], "version": r["version"], "authors": r.get("authors", []),
             "description": r.get("description", ""),
             "games": [{"slug": g["slug"], "title": g.get("title") or g["slug"].replace("-", " ").title()} for g in r["games"]],
             "package_url": a.package_url, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    if a.cover_url:
        entry["cover_url"] = a.cover_url
    if a.homepage:
        entry["homepage"] = a.homepage
    if a.melty:
        entry["links"] = {"melty": a.melty}
    idx = json.load(open(INDEX)) if os.path.exists(INDEX) else {"mashwright_catalog": 1, "name": "Mashwright catalog", "mashups": []}
    idx["mashups"] = [m for m in idx["mashups"] if m["id"] != entry["id"]] + [entry]
    idx["mashups"].sort(key=lambda m: m["title"].lower())
    with open(INDEX, "w") as f:
        json.dump(idx, f, indent=2)
        f.write("\n")
    print("catalog:", entry["id"], entry["version"], entry["sha256"][:12])


if __name__ == "__main__":
    main()
