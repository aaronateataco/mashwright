"""Check every hue_assets row against the real Hue install (dev machine only; nothing is copied).

Writes build/hue_assets_verified.json: {sheet_hash, hue_data, results: {id: "ok" | error}}.
usage: python -I tools/verify_hue_assets.py <Hue_Data dir>
"""
import hashlib
import json
import os
import sys
import types

# UnityPy imports astc_encoder, whose DLL does not load on this PC; Hue has no ASTC textures.
_stub = types.ModuleType("astc_encoder")
for _n in ("ASTCConfig", "ASTCContext", "ASTCImage", "ASTCProfile", "ASTCSwizzle", "ASTCType",
           "ASTCConfigFlags", "ASTCQualityPreset"):
    setattr(_stub, _n, object)
sys.modules["astc_encoder"] = _stub

import UnityPy  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sheets_lib import ROOT, SHEETS_DIR, load_sheet  # noqa: E402


def check_row(env_cache: dict, hue_data: str, row: dict) -> str:
    path = os.path.join(hue_data, row["file"])
    if not os.path.exists(path):
        return f"missing file {row['file']}"
    if path not in env_cache:
        env_cache[path] = UnityPy.load(path)
    env = env_cache[path]
    sf = next(iter(env.files.values()))
    obj = sf.objects.get(row["path_id"])
    if obj is None:
        return f"no object {row['path_id']} in {row['file']}"
    if obj.class_id != row["class_id"]:
        return f"class {obj.class_id} != {row['class_id']}"
    data = obj.read()
    if data.m_Name != row["unity_name"]:
        return f"name {data.m_Name!r} != {row['unity_name']!r}"
    kind = row["kind"]
    if kind == "texture":
        size = f"{data.m_Width}x{data.m_Height}"
    elif kind == "sprite":
        r = data.m_RD.textureRect
        size = f"{round(r.width)}x{round(r.height)}"
    elif kind == "audio":
        size = f"{data.m_Length:.1f}"
    elif kind == "text":
        script = data.m_Script
        size = str(len(script.encode("utf-8", "surrogateescape")) if isinstance(script, str) else len(script))
    else:
        return f"unknown kind {kind}"
    if size != row["size"]:
        return f"size {size} != {row['size']}"
    return "ok"


def main() -> None:
    hue_data = sys.argv[1]
    sheet_path = os.path.join(SHEETS_DIR, "hue_assets.json")
    sheet_hash = hashlib.sha256(open(sheet_path, "rb").read()).hexdigest()
    sheet = load_sheet("hue_assets")
    cache = {}
    results = {}
    for row in sheet["rows"]:
        try:
            results[row["id"]] = check_row(cache, hue_data, row)
        except Exception as e:  # report, don't stop: the preflight lists every failure
            results[row["id"]] = f"error {e!r}"
    out = os.path.join(ROOT, "build", "hue_assets_verified.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"sheet_hash": sheet_hash, "hue_data": hue_data, "results": results}, f, indent=1)
    bad = {k: v for k, v in results.items() if v != "ok"}
    print(f"{len(results) - len(bad)}/{len(results)} hue assets verified")
    for k, v in bad.items():
        print(" ", k, v)


if __name__ == "__main__":
    main()
