from pathlib import Path
import json
import unittest
import zipfile

from helpers import fake_env, tree_hash, write
from mashwright import installer, library
from mashwright import recipe as rcp
from mashwright.targets import emulators


class MeltyFormatTest(unittest.TestCase):
    def test_import_melty_format_folder(self):
        env = fake_env("linux")
        pkg = env.home / "Some Mashup"
        write(pkg / "recipe.json", json.dumps({
            "schemaVersion": 1, "mode": "installed",
            "games": [{"slug": "brotato", "role": "primary", "version": ">=1.1.15"}, {"slug": "custom-hue", "role": "secondary"}],
            "components": [{"id": "main", "fileName": "Mod.zip", "kind": "main", "required": True}],
            "mappings": [{"component": "main", "from": "", "to": "{game}/mods"}],
            "launch": {"kind": "game"}, "notes": {"firstLaunch": "Have fun"}}))
        with zipfile.ZipFile(pkg / "Mod.zip", "w") as z:
            z.writestr("a.txt", "a")
        r = library.import_path(env, pkg)
        self.assertEqual(r["id"], "some-mashup")
        self.assertEqual([g["slug"] for g in r["games"]], ["brotato", "hue"])
        self.assertEqual(rcp.validate(r), [])


class EmulatorTest(unittest.TestCase):
    def test_dolphin_texture_pack_round_trip(self):
        env = fake_env("linux")
        root = env.home / ".var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu"
        write(root / "Load/Textures/GALE01/existing.png", data=b"old")
        before = tree_hash(root)
        mdir = env.home / "m"
        mdir.mkdir()
        with zipfile.ZipFile(mdir / "tex.zip", "w") as z:
            z.writestr("tex1_64x64_abc.png", "new")
            z.writestr("existing.png", "replaced")
        r = {"mashwright": 1, "id": "melee-hd", "title": "Melee HD", "version": "1",
             "games": [{"slug": "melee", "role": "primary", "emulator": {"system": "gamecube", "id": "GALE01"}}],
             "components": [{"id": "tex", "file": "tex.zip", "extract": True}],
             "mappings": [{"component": "tex", "to": "{emu_mod}"}]}
        self.assertEqual(rcp.validate(r), [])
        picked, missing = rcp.choose(r, [], env)
        self.assertEqual(missing, [])
        self.assertEqual(picked["melee"].runner, "emulator:Dolphin")
        installer.install(r, mdir, picked, env)
        self.assertEqual((root / "Load/Textures/GALE01/existing.png").read_text(), "replaced")
        self.assertTrue((root / "Load/Textures/GALE01/tex1_64x64_abc.png").is_file())
        installer.uninstall(env, "melee-hd")
        self.assertEqual(tree_hash(root), before)

    def test_cemu_graphic_pack_path_and_missing_emulator(self):
        env = fake_env("linux")
        (env.home / ".local/share/Cemu").mkdir(parents=True)
        g = emulators.game_for(env, {"system": "wiiu", "id": "00050000101C9500", "title": "BotW"})
        self.assertTrue(Path(emulators.paths(g, "my-pack")["emu_mod"]).as_posix().endswith("Cemu/graphicPacks/my-pack"))
        self.assertIsNone(emulators.game_for(env, {"system": "ps2", "id": "SLUS-20062"}))


if __name__ == "__main__":
    unittest.main()
