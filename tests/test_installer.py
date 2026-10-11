import io
import json
import shutil
import unittest
import zipfile
from pathlib import Path

from helpers import fake_env, tree_hash, write
from mashwright import installer, library
from mashwright import recipe as rcp
from mashwright.model import Game, MashwrightError


def make_zip(path: Path, files: dict):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path


def base_recipe(**over):
    r = {"mashwright": 1, "id": "demo", "title": "Demo", "version": "1.0",
         "games": [{"slug": "brotato", "role": "primary", "version": ">=1.1"}],
         "components": [{"id": "main", "file": "main.zip", "extract": True},
                        {"id": "raw", "file": "inner.zip", "extract": False}],
         "mappings": [{"component": "main", "from": "", "to": "{game}"},
                      {"component": "raw", "to": "{game}/mods"}]}
    r.update(over)
    return r


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.env = fake_env("linux")
        self.game_dir = self.env.home / "lib/Brotato"
        write(self.game_dir / "Brotato.x86_64", data=b"\x7fELFgame")
        write(self.game_dir / "override.cfg", "original")
        self.mdir = self.env.home / "mashup"
        self.mdir.mkdir()
        make_zip(self.mdir / "main.zip", {"override.cfg": "ours", "mods/boot.gd": "boot", "mods/sub/x.txt": "x"})
        make_zip(self.mdir / "inner.zip", {"a": "b"})
        self.game = Game(key="steam:1942280", store="steam", store_id="1942280", title="Brotato",
                         install_dir=self.game_dir, platform="linux", version="1.1.15")

    def test_round_trip_restores_game_exactly(self):
        before = tree_hash(self.game_dir)
        r = base_recipe()
        installer.install(r, self.mdir, {"brotato": self.game}, self.env)
        self.assertEqual((self.game_dir / "override.cfg").read_text(), "ours")
        self.assertTrue((self.game_dir / "mods/inner.zip").is_file())
        self.assertTrue((self.game_dir / "mods/sub/x.txt").is_file())
        self.assertTrue(installer.status(self.env, "demo")["installed"])
        with self.assertRaises(MashwrightError):
            installer.install(r, self.mdir, {"brotato": self.game}, self.env)
        installer.uninstall(self.env, "demo")
        self.assertEqual(tree_hash(self.game_dir), before)
        self.assertFalse(installer.is_installed(self.env, "demo"))

    def test_zip_slip_rejected_and_rolled_back(self):
        before = tree_hash(self.game_dir)
        make_zip(self.mdir / "main.zip", {"ok.txt": "1", "../../escape.txt": "x"})
        with self.assertRaises(MashwrightError):
            installer.install(base_recipe(), self.mdir, {"brotato": self.game}, self.env)
        self.assertEqual(tree_hash(self.game_dir), before)
        self.assertFalse((self.env.home / "escape.txt").exists())
        self.assertFalse(installer.is_installed(self.env, "demo"))

    def test_failure_midway_rolls_back(self):
        before = tree_hash(self.game_dir)
        r = base_recipe()
        r["components"][1]["sha256"] = "0" * 64   # checked before writing
        with self.assertRaises(MashwrightError):
            installer.install(r, self.mdir, {"brotato": self.game}, self.env)
        self.assertEqual(tree_hash(self.game_dir), before)

    def test_settings_written_and_restored(self):
        cfg = self.env.home / ".local/share/Brotato/huepotato.cfg"
        write(cfg, "[options]\nhue_music=false\n")
        r = base_recipe(settings=[{"file": "{appdata}/Brotato/huepotato.cfg", "section": "hue", "key": "data_dir",
                                   "value": "{home}/Hue/Hue_Data"}])
        installer.install(r, self.mdir, {"brotato": self.game}, self.env)
        text = cfg.read_text()
        self.assertIn("data_dir", text)
        self.assertIn('"', text)
        installer.uninstall(self.env, "demo")
        self.assertNotIn("data_dir", cfg.read_text())
        self.assertIn("hue_music", cfg.read_text())

    def test_proton_appdata_points_into_prefix(self):
        g = Game(key="steam:1", store="steam", store_id="1", title="G", install_dir=self.game_dir,
                 platform="windows", runner="proton", extra={"prefix": str(self.env.home / "pfx")})
        ctx = rcp.context(base_recipe(), {"brotato": g}, self.env)
        self.assertTrue(Path(ctx["appdata"]).as_posix().endswith("pfx/drive_c/users/steamuser/AppData/Roaming"))

    def test_library_import_and_versions(self):
        pkg = self.env.home / "demo.mashwright"
        with zipfile.ZipFile(pkg, "w") as z:
            z.writestr("mashwright.json", json.dumps(base_recipe()))
            z.write(self.mdir / "main.zip", "main.zip")
            z.write(self.mdir / "inner.zip", "inner.zip")
        r = library.import_path(self.env, pkg)
        self.assertEqual(r["id"], "demo")
        self.assertEqual([m["id"] for m in library.list_all(self.env)], ["demo"])
        self.assertTrue(rcp.version_ok("1.1.15.4", ">=1.1.15"))
        self.assertFalse(rcp.version_ok("1.0.9", ">=1.1, <2"))
        self.assertIsNone(rcp.version_ok("", ">=1"))

    def test_validation_messages(self):
        bad = base_recipe(id="Bad Id", mappings=[{"component": "main", "to": "{nope}/x"}])
        problems = rcp.validate(bad)
        self.assertTrue(any("slug" in p for p in problems))
        self.assertTrue(any("unknown placeholder" in p for p in problems))
        self.assertEqual(rcp.validate(base_recipe()), [])

    def test_example_recipe_valid(self):
        ex = Path(__file__).resolve().parents[1] / "examples/hue-potato/mashwright.json"
        self.assertEqual(rcp.validate(json.loads(ex.read_text())), [])


if __name__ == "__main__":
    unittest.main()
