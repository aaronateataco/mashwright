"""Preflight: lay every sheet's rows and columns over each other before a build.

Lists every unfilled cell, every reference between sheets that does not resolve, every Brotato
hook that is not in the decompiled game, every Hue asset not verified against the real files,
and every tuning id / text key the code uses that no sheet defines. Exit code 1 if anything fails.

usage: python tools/preflight.py [--release]   (--release also requires every tests row passed)
"""
import hashlib
import json
import os
import re
import sys

from sheets_lib import MOD_DIR, ROOT, SHEETS_DIR, load_all, rows_by_id

DECOMP = os.environ.get("BROTATO_DECOMP", r"C:\Users\Aaron\BrotatoDecomp")

problems = []


def fail(where: str, msg: str) -> None:
    problems.append(f"{where}: {msg}")


def unfilled(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def check_cells(sheets: dict) -> None:
    for name, sheet in sheets.items():
        ids = set()
        for i, row in enumerate(sheet["rows"]):
            rid = row.get("id", f"row{i}")
            if rid in ids:
                fail(f"{name}.{rid}", "duplicate id")
            ids.add(rid)
            for col in sheet["columns"]:
                if col not in row:
                    fail(f"{name}.{rid}", f"missing column {col}")
                elif unfilled(row[col]):
                    fail(f"{name}.{rid}.{col}", "unfilled")
            for col in row:
                if col not in sheet["columns"]:
                    fail(f"{name}.{rid}", f"column {col} not declared in sheet")


def ref(sheets, where, value, target, kinds=None, allow_none=False):
    if allow_none and value == "none":
        return
    rows = rows_by_id(sheets[target])
    if value not in rows:
        fail(where, f"{value!r} is not a {target} row")
        return
    if kinds and rows[value].get("kind") not in kinds:
        fail(where, f"{value!r} is a {rows[value].get('kind')}, needs {kinds}")


def brotato_file(res_path: str) -> str:
    return os.path.join(DECOMP, res_path.replace("res://", "").replace("/", os.sep))


_stat_keys = None


def brotato_keys() -> set:
    global _stat_keys
    if _stat_keys is None:
        text = open(os.path.join(DECOMP, "singletons", "keys.gd"), encoding="utf-8").read()
        _stat_keys = set(re.findall(r'generate_hash\("([a-z0-9_]+)"\)', text))
    return _stat_keys


def script_members(res_path: str, seen=None) -> set:
    """Functions and variables declared in a Brotato script and its parents."""
    seen = seen or set()
    path = brotato_file(res_path)
    if res_path in seen or not os.path.exists(path):
        return set()
    seen.add(res_path)
    text = open(path, encoding="utf-8").read()
    members = set(re.findall(r"^(?:static\s+)?func\s+(\w+)", text, re.M))
    members |= set(re.findall(r"^signal\s+(\w+)", text, re.M))
    members |= set(re.findall(r"^(?:export\s*(?:\([^)]*\))?\s*)?(?:onready\s+)?var\s+(\w+)", text, re.M))
    m = re.search(r'^extends\s+"(res://[^"]+)"', text, re.M)
    parent = m.group(1) if m else None
    if not parent:
        m = re.search(r"^extends\s+(\w+)", text, re.M)
        if m:
            parent = class_path(m.group(1))
    if parent:
        members |= script_members(parent, seen)
    return members


_class_paths = None


def class_path(class_name: str):
    global _class_paths
    if _class_paths is None:
        _class_paths = {}
        for root, _d, files in os.walk(DECOMP):
            for f in files:
                if f.endswith(".gd"):
                    p = os.path.join(root, f)
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        head = fh.read(400)
                    m = re.search(r"^class_name\s+(\w+)", head, re.M)
                    if m:
                        rel = os.path.relpath(p, DECOMP).replace(os.sep, "/")
                        _class_paths[m.group(1)] = "res://" + rel
    return _class_paths.get(class_name)


def check_refs(s: dict) -> None:
    for r in s["colours"]["rows"]:
        w = f"colours.{r['id']}"
        ref(s, w + ".symbol", r["symbol"], "hue_assets", ["sprite"])
        ref(s, w + ".chime", r["chime"], "hue_assets", ["audio"])
        ref(s, w + ".letter_vo", r["letter_vo"], "hue_assets", ["audio"])
        ref(s, w + ".name_key", r["name_key"], "strings")
        if len(r["rgb"]) != 3:
            fail(w + ".rgb", "needs 3 numbers")
    idx = sorted(r["wheel_index"] for r in s["colours"]["rows"])
    if idx != list(range(len(idx))):
        fail("colours.wheel_index", f"must be 0..{len(idx) - 1} once each, got {idx}")
    if not any(r["unlock_wave"] == 0 for r in s["colours"]["rows"]):
        fail("colours.unlock_wave", "no starting colour (unlock_wave 0)")

    waves = []
    for r in s["regions"]["rows"]:
        w = f"regions.{r['id']}"
        ref(s, w + ".icon", r["icon"], "hue_assets", ["sprite"])
        ref(s, w + ".music", r["music"], "hue_assets", ["audio"])
        ref(s, w + ".name_key", r["name_key"], "strings")
        waves += list(range(r["wave_from"], r["wave_to"] + 1))
    if sorted(waves) != list(range(1, 21)):
        fail("regions", "wave spans must cover waves 1-20 exactly once")

    for r in s["hazards"]["rows"]:
        w = f"hazards.{r['id']}"
        ref(s, w + ".name_key", r["name_key"], "strings")
        ref(s, w + ".hint_key", r["hint_key"], "strings")
        for col in ("asset", "asset2", "asset3"):
            ref(s, w + "." + col, r[col], "hue_assets", ["sprite", "texture"], allow_none=(col != "asset"))
        ref(s, w + ".start_sound", r["start_sound"], "sounds")
        ref(s, w + ".hit_sound", r["hit_sound"], "sounds")
        if r["count_per_waves"] <= 0 or r["interval_s"] <= 0:
            fail(w, "count_per_waves and interval_s must be positive")

    moments = set()
    for r in s["letters"]["rows"]:
        w = f"letters.{r['id']}"
        ref(s, w + ".asset", r["asset"], "hue_assets", ["audio"])
        if (r["wave"], r["order"]) in moments:
            fail(w, f"two letters share wave {r['wave']} order {r['order']}")
        moments.add((r["wave"], r["order"]))
        if not 0 <= r["wave"] <= 20 or r["lines"] < 1:
            fail(w, "wave must be 0-20 and lines at least 1")

    effects = rows_by_id(s["effects"])
    for r in s["character"]["rows"]:
        w = f"character.{r['id']}"
        ref(s, w + ".name_key", r["name_key"], "strings")
        for lid in r["layers"] + r["icon_layers"]:
            ref(s, w + ".layers", lid, "layers")
        for eid in r["effects"]:
            ref(s, w + ".effects", eid, "effects")
            if eid in effects and effects[eid]["owner"] != r["id"]:
                fail(w + ".effects", f"{eid} belongs to {effects[eid]['owner']}")
        for wp in r["starting_weapons"]:
            if not os.path.exists(brotato_file(wp)):
                fail(w + ".starting_weapons", f"{wp} not in Brotato")
        for t in r["wanted_tags"]:
            if t not in brotato_keys():
                fail(w + ".wanted_tags", f"{t} is not a Brotato key")

    for r in s["character"]["rows"]:
        ref(s, f"character.{r['id']}.signature_weapon", r["signature_weapon"], "weapons")
    tiers = []
    for r in s["weapons"]["rows"]:
        w = f"weapons.{r['id']}"
        ref(s, w + ".name_key", r["name_key"], "strings")
        ref(s, w + ".text_key", r["text_key"], "strings")
        ref(s, w + ".upgrades_into", r["upgrades_into"], "weapons", allow_none=True)
        for col in ("beam_asset", "emitter_asset", "emitter_mask_asset"):
            ref(s, w + "." + col, r[col], "hue_assets", ["sprite", "texture"])
        if not isinstance(r["emitters"], int) or r["emitters"] < 3:
            fail(w + ".emitters", "a ring needs at least 3 laser cannons")
        for pair in r["scaling_stats"]:
            if len(pair) != 2 or pair[0] not in brotato_keys():
                fail(w + ".scaling_stats", f"{pair} is not [Brotato stat key, ratio]")
        tiers.append(r["tier"])
    if sorted(tiers) != list(range(len(tiers))):
        fail("weapons.tier", f"tiers must be 0..{len(tiers) - 1}, got {tiers}")

    for r in s["layers"]["rows"]:
        w = f"layers.{r['id']}"
        ref(s, w + ".asset", r["asset"], "hue_assets", ["sprite", "texture"])
        ref(s, w + ".dead_asset", r["dead_asset"], "hue_assets", ["sprite", "texture"], allow_none=True)
        if r["position"] not in ("OTHER", "ABOVE_HEAD", "HAT", "FOREHEAD", "EYES", "NOSE", "MOUTH", "BACK", "NECK", "TORSO", "SKIN"):
            fail(w + ".position", f"{r['position']} is not an ItemAppearanceData.Position")

    owners = set(rows_by_id(s["character"])) | set(rows_by_id(s["items"]))
    for r in s["effects"]["rows"]:
        w = f"effects.{r['id']}"
        if r["owner"] not in owners:
            fail(w + ".owner", f"{r['owner']} is not a character or item")
        if r["kind"] == "stat":
            if r["key"] not in brotato_keys():
                fail(w + ".key", f"{r['key']} is not a Brotato stat key")
            if r["text_key"] != "none":
                ref(s, w + ".text_key", r["text_key"], "strings")
        elif r["kind"] == "text":
            if r["key"] != "none":
                fail(w + ".key", "text effects must use key none")
            ref(s, w + ".text_key", r["text_key"], "strings")
        else:
            fail(w + ".kind", f"unknown kind {r['kind']}")
        if r["effect_sign"] not in ("POSITIVE", "NEGATIVE", "NEUTRAL", "FROM_VALUE"):
            fail(w + ".effect_sign", r["effect_sign"])

    for r in s["items"]["rows"]:
        w = f"items.{r['id']}"
        ref(s, w + ".name_key", r["name_key"], "strings")
        ref(s, w + ".icon", r["icon"], "hue_assets", ["sprite", "texture"])
        ref(s, w + ".icon2", r["icon2"], "hue_assets", ["sprite", "texture"], allow_none=True)
        ref(s, w + ".synergy", r["synergy"], "synergies", allow_none=True)
        for eid in r["effects"]:
            ref(s, w + ".effects", eid, "effects")
            if eid in effects and effects[eid]["owner"] != r["id"]:
                fail(w + ".effects", f"{eid} belongs to {effects[eid]['owner']}")
        for t in r["tags"]:
            if t not in brotato_keys():
                fail(w + ".tags", f"{t} is not a Brotato key")
        if r["tier"] not in (0, 1, 2, 3):
            fail(w + ".tier", "Brotato tiers are 0-3")

    items = rows_by_id(s["items"])
    for r in s["synergies"]["rows"]:
        w = f"synergies.{r['id']}"
        ref(s, w + ".item", r["item"], "items")
        ref(s, w + ".text_key", r["text_key"], "strings")
        if r["item"] in items and items[r["item"]]["synergy"] != r["id"]:
            fail(w, f"item {r['item']} points at {items[r['item']]['synergy']}")
        if r["trigger"] not in ("fragment_collected", "colour_switched"):
            fail(w + ".trigger", r["trigger"])
        if r["action"] not in ("heal_percent_max_hp", "materials_per_revealed", "slow_revealed_percent", "heal_flat"):
            fail(w + ".action", r["action"])
        if r["item"] in items and not any(effects.get(e, {}).get("text_key") == r["text_key"] for e in items[r["item"]]["effects"]):
            fail(w, "the item has no effect line showing this synergy's text")

    for r in s["sounds"]["rows"]:
        w = f"sounds.{r['id']}"
        for a in r["assets"]:
            ref(s, w + ".assets", a, "hue_assets", ["audio"])
        ref(s, w + ".volume_tuning", r["volume_tuning"], "tuning")
        ref(s, w + ".max_length_tuning", r["max_length_tuning"], "tuning")
        if r["bus"] not in ("Sound", "Music", "Master"):
            fail(w + ".bus", r["bus"])

    main_gd = os.path.join(MOD_DIR, "mod_main.gd")
    mapped = set()
    if os.path.exists(main_gd):
        block = re.search(r"const INPUT_CONSTANTS = \{(.*?)\n\}", open(main_gd, encoding="utf-8").read(), re.S)
        mapped = set(re.findall(r'"([A-Z0-9_]+)"\s*:', block.group(1))) if block else set()
    for r in s["input"]["rows"]:
        w = f"input.{r['id']}"
        ref(s, w + ".label_key", r["label_key"], "strings")
        for name in r["keys"] + r["mouse_buttons"] + r["joy_buttons"]:
            if name not in mapped:
                fail(w, f"{name} has no entry in mod_main.gd INPUT_CONSTANTS")
        for k in r["keys"]:
            if not re.fullmatch(r"KEY_[A-Z0-9_]+", k):
                fail(w + ".keys", k)
        for b in r["mouse_buttons"]:
            if not re.fullmatch(r"BUTTON_[A-Z_]+", b):
                fail(w + ".mouse_buttons", b)
        for b in r["joy_buttons"]:
            if not re.fullmatch(r"JOY_[A-Z0-9_]+", b):
                fail(w + ".joy_buttons", b)

    for r in s["enemy_rules"]["rows"]:
        if r["match"] not in ("boss", "loot", "charmed", "default"):
            fail(f"enemy_rules.{r['id']}.match", r["match"])

    for r in s["hooks"]["rows"]:
        w = f"hooks.{r['id']}"
        if r["kind"] in ("extension", "call"):
            if not os.path.exists(brotato_file(r["target"])):
                fail(w + ".target", f"{r['target']} not in Brotato")
                continue
            have = script_members(r["target"])
            for m in r["members"]:
                if m not in have:
                    fail(w + ".members", f"{m} not found in {r['target']} or its parents")
        base = ROOT if r["our_file"].startswith("boot/") else MOD_DIR
        if not os.path.exists(os.path.join(base, r["our_file"])):
            fail(w + ".our_file", f"{r['our_file']} not written yet")

    for r in s["package"]["rows"]:
        if not os.path.exists(os.path.join(ROOT, r["source"])):
            fail(f"package.{r['id']}.source", f"{r['source']} missing")


def check_assets_verified(s: dict) -> None:
    path = os.path.join(ROOT, "build", "hue_assets_verified.json")
    if not os.path.exists(path):
        fail("hue_assets", "never verified against Hue (run tools/verify_hue_assets.py)")
        return
    data = json.load(open(path, encoding="utf-8"))
    sheet_hash = hashlib.sha256(open(os.path.join(SHEETS_DIR, "hue_assets.json"), "rb").read()).hexdigest()
    if data["sheet_hash"] != sheet_hash:
        fail("hue_assets", "sheet changed since last verification (rerun tools/verify_hue_assets.py)")
    for row in s["hue_assets"]["rows"]:
        res = data["results"].get(row["id"])
        if res != "ok":
            fail(f"hue_assets.{row['id']}", f"not verified: {res}")


def check_code_uses(s: dict) -> None:
    """Every tuning id and text key in the code must come from a sheet; every tuning row must be used."""
    tuning = set(rows_by_id(s["tuning"]))
    strings = set(rows_by_id(s["strings"]))
    options = set(rows_by_id(s["options"]))
    used_t, used_s, used_o = set(), set(), set()
    for root, _d, files in os.walk(MOD_DIR):
        for f in files:
            if f.endswith(".gd") and "generated" not in root:
                text = open(os.path.join(root, f), encoding="utf-8").read()
                for t in re.findall(r'\b(?:T|tuning)\("([a-z0-9_]+)"\)', text):
                    used_t.add(t)
                    if t not in tuning:
                        fail(f"code {f}", f'T("{t}") has no tuning row')
                for o in re.findall(r'\bopt\("([a-z0-9_]+)"\)', text):
                    used_o.add(o)
                    if o not in options:
                        fail(f"code {f}", f'opt("{o}") has no options row')
                for k in re.findall(r'"(HUE_[A-Z0-9_]+)"', text):
                    used_s.add(k)
                    if k not in strings:
                        fail(f"code {f}", f"{k} has no strings row")
    sheet_keys = set()
    for name in ("colours", "regions", "character", "effects", "items", "weapons", "synergies", "input", "hazards"):
        for row in s[name]["rows"]:
            for col in ("name_key", "text_key", "label_key", "hint_key"):
                if col in row and row[col] != "none":
                    sheet_keys.add(row[col])
    # Tuning rows can also be read through another sheet (a sound's volume/length tuning).
    for row in s["sounds"]["rows"]:
        used_t.add(row["volume_tuning"])
        used_t.add(row["max_length_tuning"])
    for t in tuning - used_t:
        fail(f"tuning.{t}", "never read by the code")
    for o in options - used_o:
        fail(f"options.{o}", "never read by the code")
    for k in strings - used_s - sheet_keys:
        fail(f"strings.{k}", "never used")


def check_tests(s: dict) -> None:
    for r in s["tests"]["rows"]:
        if r["result"] != "passed":
            fail(f"tests.{r['id']}", f"result {r['result']}")
    for r in s["package"]["rows"]:
        for col in ("license", "credit"):
            if r[col] == "ask-owner":
                fail(f"package.{r['id']}.{col}", "the owner hasn't chosen yet")


def main() -> None:
    release = "--release" in sys.argv
    sheets = load_all()
    check_cells(sheets)
    check_refs(sheets)
    check_assets_verified(sheets)
    if os.path.isdir(MOD_DIR):
        check_code_uses(sheets)
    if release:
        check_tests(sheets)
    total_cells = sum(len(sh["rows"]) * len(sh["columns"]) for sh in sheets.values())
    print(f"preflight: {len(sheets)} sheets, {sum(len(sh['rows']) for sh in sheets.values())} rows, {total_cells} cells")
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("clean")


if __name__ == "__main__":
    main()
