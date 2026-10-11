import hashlib
import os
import tempfile
from pathlib import Path

from mashwright.platforms import HostEnv


def fake_env(os_name="linux", home=None, environ=None, reg=None, reg_subkeys=None, run=None, which=None, volumes=()):
    home = Path(home or tempfile.mkdtemp(prefix="pw-home-"))
    return HostEnv(os=os_name, home=home, environ=environ or {"HOME": str(home)}, reg=reg, reg_subkeys=reg_subkeys,
                   run=run or (lambda cmd, timeout=0: (127, "")), which=which or (lambda n: None),
                   volumes=tuple(volumes))


def write(path: Path, text="", data=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if data is not None:
        path.write_bytes(data)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def tree_hash(root: Path) -> dict:
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for d in dirs:
            out[os.path.relpath(os.path.join(dirpath, d), root) + "/"] = "dir"
        for f in files:
            p = os.path.join(dirpath, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def steam_manifest(lib: Path, appid: str, name: str, installdir: str, flags=4, buildid="123"):
    write(lib / "steamapps" / f"appmanifest_{appid}.acf",
          f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n\t"StateFlags"\t\t"{flags}"\n'
          f'\t"installdir"\t\t"{installdir}"\n\t"buildid"\t\t"{buildid}"\n}}\n')
