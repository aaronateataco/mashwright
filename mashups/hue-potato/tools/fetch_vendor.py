"""Download the vgmstream builds Hue Potato bundles (r2117, ISC licence) into _vendor/.

usage: python tools/fetch_vendor.py
"""
import io
import os
import urllib.request
import zipfile

from sheets_lib import ROOT

RELEASE = "https://github.com/vgmstream/vgmstream/releases/download/r2117/"
BUILDS = {"vgmstream-win64.zip": "vgmstream-r2117-win64", "vgmstream-linux.zip": "vgmstream-r2117-linux",
          "vgmstream-mac.zip": "vgmstream-r2117-mac"}


def main() -> None:
    for asset, folder in BUILDS.items():
        dest = os.path.join(ROOT, "_vendor", folder)
        if os.path.isdir(dest) and os.listdir(dest):
            print("have", folder)
            continue
        print("downloading", asset)
        data = urllib.request.urlopen(RELEASE + asset, timeout=120).read()
        os.makedirs(dest, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if info.is_dir() or ".." in info.filename.split("/") or info.filename.startswith("/"):
                    continue
                out = os.path.join(dest, info.filename)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "wb") as f:
                    f.write(z.read(info))
                if folder.endswith(("linux", "mac")) and os.path.basename(out) == "vgmstream-cli":
                    os.chmod(out, 0o755)


if __name__ == "__main__":
    main()
