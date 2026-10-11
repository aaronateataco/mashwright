"""Write the argument files for Melty's package checks from build/packages.json and recipe.json.

usage: python tools/melty_args.py <out_dir>
Writes inspect_<component>.json, validate.json and oneclick.json.
"""
import json
import os
import sys
import zipfile

from sheets_lib import ROOT

SAYS = (
    "Hue Potato: Hue (the game) joins Brotato as a playable potato wearing Hue's own hair, ear and eyes. "
    "Hue's colour wheel: hold it to slow time to Hue's 0.1x and pick a colour; enemies and enemy bullets of the "
    "background colour vanish (can't hurt you, can't be hurt). Colours are earned by wave like in Hue (Aqua and "
    "Purple, then a fragment every other wave), each fragment plays Mum's voice letter with Hue's subtitles. "
    "Hue's Laser Ring weapon: Hue's laser cannons orbit the potato, their beams forming a spinning fence; a beam of the background colour vanishes. Waves travel through Hue's regions with Hue's map icons and music; Mum's intro, region and ending letters are read too. Hue's laser gates and skull boulders appear in later waves (switch to their colour to pass), trees become Hue's coloured crates, and Dr Grey appears for the final wave. Six Hue items in the shop with Hue icons. "
    "Reads all Hue art, music, sounds and text from the player's own Hue install at runtime; nothing from Hue ships. "
    "Single player only; it has no online multiplayer. Bundles vgmstream to decode Hue's audio, and a small boot "
    "script plus override.cfg because Brotato's Steam build only loads Workshop mods."
)


def main() -> None:
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    pk = json.load(open(os.path.join(ROOT, "build", "packages.json"), encoding="utf-8"))
    recipe = json.load(open(os.path.join(ROOT, "recipe.json"), encoding="utf-8"))
    entries = {comp: pk[comp]["entries"] for comp in pk}
    for comp in pk:
        files = {}
        with zipfile.ZipFile(os.path.join(ROOT, "build", pk[comp]["file"])) as z:
            for name in z.namelist():
                if name.endswith(("manifest.json", "README.md", "override.cfg", "huepotato_boot.gd", "THIRD_PARTY.txt", "COPYING")):
                    files[name] = z.read(name).decode("utf-8", "replace")[:6000]
        args = {"fileName": pk[comp]["file"], "entries": pk[comp]["entries"], "files": files,
                "gameSlugs": ["brotato", "custom-hue"], "says": SAYS}
        json.dump(args, open(os.path.join(out, f"inspect_{comp}.json"), "w", encoding="utf-8"))
    json.dump({"recipe": recipe, "entries": entries, "says": SAYS}, open(os.path.join(out, "validate.json"), "w", encoding="utf-8"))
    json.dump({"recipe": recipe, "entries": entries, "says": SAYS}, open(os.path.join(out, "oneclick.json"), "w", encoding="utf-8"))
    print("wrote", out)


if __name__ == "__main__":
    main()
