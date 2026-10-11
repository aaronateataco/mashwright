import unittest
import zipfile

from helpers import fake_env, write
from mashwright import binaries, installer
from mashwright import recipe as rcp
from mashwright.model import Game

ELF = b"\x7fELF" + b"\0" * 60
PE = b"MZ" + b"\0" * 60
MACHO = b"\xcf\xfa\xed\xfe" + b"\0" * 60


def mk(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)


class BinariesTest(unittest.TestCase):
    def setUp(self):
        self.env = fake_env("linux")
        self.d = self.env.home / "m"
        self.d.mkdir()
        self.game_dir = self.env.home / "Game"
        write(self.game_dir / "Game.x86_64", data=ELF)

    def recipe(self, comps):
        return {"mashwright": 1, "id": "t", "title": "T", "version": "1",
                "games": [{"slug": "g", "role": "primary"}],
                "components": [{"id": c, "file": f"{c}.zip", "extract": True} for c in comps],
                "mappings": [{"component": c, "to": "{game}"} for c in comps]}

    def game(self, runner="native", platform="linux"):
        return Game(key="steam:1", store="steam", store_id="1", title="G", install_dir=self.game_dir,
                    platform=platform, runner=runner)

    def test_classify(self):
        self.assertEqual(binaries.classify(ELF), "linux")
        self.assertEqual(binaries.classify(PE), "windows")
        self.assertEqual(binaries.classify(MACHO), "macos")
        self.assertIsNone(binaries.classify(b"extends Node"))

    def test_hybrid_installs_only_matching_build(self):
        mk(self.d / "tools.zip", {"tool/win64/t.exe": PE, "tool/linux/t": ELF, "tool/macos/t": MACHO, "tool/README": "x"})
        mk(self.d / "mod.zip", {"inner.zip": b"", "mod/script.gd": "extends Node"})
        r = self.recipe(["tools", "mod"])
        fit = binaries.fit(r, binaries.analyze(r, self.d), self.game(), "linux")
        self.assertEqual(fit["status"], "adjusted")
        self.assertEqual(sorted(fit["skip"]), ["tools:tool/macos", "tools:tool/win64"])
        installer.install(r, self.d, {"g": self.game()}, self.env, skip=fit["skip"])
        self.assertTrue((self.game_dir / "tool/linux/t").exists())
        self.assertFalse((self.game_dir / "tool/macos").exists())
        self.assertFalse((self.game_dir / "tool/win64").exists())
        self.assertTrue((self.game_dir / "tool/README").exists())

    def test_windows_only_on_native_linux_warns(self):
        mk(self.d / "dll.zip", {"BepInEx/core/BepInEx.dll": PE, "winhttp.dll": PE})
        r = self.recipe(["dll"])
        fit = binaries.fit(r, binaries.analyze(r, self.d), self.game(), "linux")
        self.assertEqual(fit["status"], "warning")
        self.assertTrue(any("Proton" in a for a in fit["advice"]))
        fit = binaries.fit(r, binaries.analyze(r, self.d), self.game("proton", "windows"), "linux")
        self.assertEqual(fit["target"], "windows")
        self.assertTrue(any("WINEDLLOVERRIDES" in a for a in fit["advice"]))

    def test_nested_archive_scanned(self):
        inner = self.env.home / "inner.zip"
        mk(inner, {"lib/x.so": ELF})
        mk(self.d / "outer.zip", {"inner.zip": inner.read_bytes()})
        rep = binaries.analyze_component(self.d / "outer.zip", "outer")
        self.assertEqual(rep.platforms, {"linux"})
        self.assertEqual(rep.nested, ["inner.zip"])


if __name__ == "__main__":
    unittest.main()
