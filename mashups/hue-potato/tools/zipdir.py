"""Zip a folder's contents with forward-slash paths (Godot's zip reader needs them).

usage: python zipdir.py <src_dir> <out_zip>
"""
import os
import sys
import zipfile


def main() -> None:
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(src):
            for name in sorted(files):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, src).replace(os.sep, "/")
                z.write(full, rel)
    print(out, os.path.getsize(out))


if __name__ == "__main__":
    main()
