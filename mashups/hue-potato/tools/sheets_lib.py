"""Shared helpers for the design sheets (sheets/*.json)."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEETS_DIR = os.path.join(ROOT, "sheets")
MOD_DIR = os.path.join(ROOT, "mod", "mods-unpacked", "HueBrotato-HuePotato")

# Order matters only for the generated file's readability.
SHEET_NAMES = [
    "hue_assets", "colours", "regions", "character", "layers", "effects", "items", "weapons",
    "synergies", "tuning", "options", "input", "sounds", "enemy_rules", "hazards", "letters", "hooks", "strings",
    "package", "tests",
]


def load_sheet(name: str) -> dict:
    with open(os.path.join(SHEETS_DIR, name + ".json"), encoding="utf-8") as f:
        sheet = json.load(f)
    assert sheet["sheet"] == name, f"{name}.json declares sheet {sheet['sheet']!r}"
    return sheet


def load_all() -> dict:
    return {name: load_sheet(name) for name in SHEET_NAMES}


def rows_by_id(sheet: dict) -> dict:
    return {row["id"]: row for row in sheet["rows"]}
