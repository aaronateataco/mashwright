import json
import sqlite3
import unittest
from pathlib import Path

from helpers import fake_env, steam_manifest, write
from mashwright import stores, vdf
from mashwright.stores import custom, heroic, lutris, steam


class VdfTest(unittest.TestCase):
    def test_nested_and_comments(self):
        d = vdf.loads('// hi\n"a" { "b" "1" "c" { "d" "x\\"y" } "e" [$WIN32] "2" }')
        self.assertEqual(vdf.get_ci(d, "A", "c", "D"), 'x"y')
        self.assertEqual(vdf.get_ci(d, "a", "b"), "1")


class SteamTest(unittest.TestCase):
    def test_linux_flatpak_with_extra_library_and_proton(self):
        env = fake_env("linux")
        root = env.home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"
        lib2 = env.home / "games/SteamLibrary"
        write(root / "steamapps/libraryfolders.vdf",
              f'"libraryfolders"\n{{\n "0"\n {{\n "path" "{root}"\n }}\n "1"\n {{\n "path" "{lib2}"\n }}\n}}\n')
        steam_manifest(lib2, "1942280", "Brotato", "Brotato")
        write(lib2 / "steamapps/common/Brotato/Brotato.x86_64", data=b"\x7fELF" + b"\0" * 100)
        steam_manifest(lib2, "999", "WinGame", "WinGame")
        write(lib2 / "steamapps/common/WinGame/Game.exe", data=b"MZ")
        (lib2 / "steamapps/compatdata/999/pfx").mkdir(parents=True)
        steam_manifest(lib2, "1493710", "Proton Experimental", "Proton - Experimental")
        write(lib2 / "steamapps/common/Proton - Experimental/proton", "x")
        steam_manifest(lib2, "555", "Half Downloaded", "Half", flags=2)
        write(lib2 / "steamapps/common/Half/x.exe", data=b"MZ")
        games = {g.key: g for g in steam.detect(env)}
        self.assertEqual(set(games), {"steam:1942280", "steam:999"})
        self.assertEqual(games["steam:1942280"].runner, "native")
        self.assertEqual(games["steam:999"].runner, "proton")
        self.assertTrue(games["steam:999"].extra["prefix"].endswith("pfx"))
        self.assertEqual(games["steam:1942280"].launch["url"], "steam://rungameid/1942280")

    def test_library_found_after_mount_point_moved(self):
        vol = fake_env().home / "mnt-new"
        env = fake_env("linux", volumes=[vol])
        root = env.home / ".local/share/Steam"
        old = env.home / "run/media/me/Games/SteamLibrary"   # no longer exists
        write(root / "steamapps/libraryfolders.vdf",
              f'"libraryfolders"\n{{\n "1"\n {{\n "path" "{old}"\n "contentid" "42"\n }}\n}}\n')
        lib = vol / "SteamLibrary"
        write(lib / "libraryfolder.vdf", '"libraryfolder"\n{\n "contentid" "42"\n}\n')
        steam_manifest(lib, "383270", "Hue", "Hue")
        write(lib / "steamapps/common/Hue/Hue.x86_64", data=b"\x7fELF" + b"\0" * 100)
        self.assertEqual([g.key for g in steam.detect(env)], ["steam:383270"])

    def test_windows_registry_and_old_vdf(self):
        env = fake_env("windows")
        root = env.home / "Steam"
        lib = env.home / "D/Games"
        write(root / "steamapps/libraryfolders.vdf", f'"LibraryFolders"\n{{\n "TimeNextStatsReport" "1"\n "1" "{lib}"\n}}\n')
        steam_manifest(lib, "383270", "Hue", "Hue")
        write(lib / "steamapps/common/Hue/Hue.exe", data=b"MZ")
        env = fake_env("windows", home=env.home, reg=lambda h, k, v: str(root) if v == "SteamPath" else None)
        games = steam.detect(env)
        self.assertEqual([g.key for g in games], ["steam:383270"])
        self.assertEqual(games[0].platform, "windows")

    def test_detect_all_slugs(self):
        env = fake_env("linux")
        root = env.home / ".local/share/Steam"
        steam_manifest(root, "383270", "Hue", "Hue")
        write(root / "steamapps/common/Hue/Hue.x86_64", data=b"\x7fELF" + b"\0" * 100)
        games = stores.detect_all(env)
        self.assertIn("hue", games[0].slugs)
        self.assertEqual(stores.find_games(games, "hue")[0].key, "steam:383270")


class OtherStoresTest(unittest.TestCase):
    def test_heroic_legendary_and_gog(self):
        env = fake_env("linux")
        root = env.home / ".config/heroic"
        gdir = env.home / "Games/Heroic/Thing"
        gdir.mkdir(parents=True)
        write(root / "legendaryConfig/legendary/installed.json",
              json.dumps({"Fennec": {"title": "Thing", "install_path": str(gdir), "platform": "Windows"}}))
        write(root / "gog_store/installed.json", json.dumps({"installed": [{"appName": "123", "install_path": str(gdir), "platform": "linux"}]}))
        write(root / "gog_store/library.json", json.dumps({"games": [{"app_name": "123", "title": "Other"}]}))
        games = {g.key: g for g in heroic.detect(env)}
        self.assertEqual(games["heroic:legendary:Fennec"].runner, "wine")
        self.assertEqual(games["heroic:gog:123"].title, "Other")
        self.assertEqual(games["heroic:gog:123"].platform, "linux")

    def test_lutris(self):
        env = fake_env("linux")
        db = env.home / ".local/share/lutris/pga.db"
        db.parent.mkdir(parents=True)
        gdir = env.home / "Games/x"
        gdir.mkdir(parents=True)
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE games (id INTEGER, name TEXT, slug TEXT, runner TEXT, directory TEXT, installed INTEGER)")
        con.execute("INSERT INTO games VALUES (7, 'X', 'x', 'wine', ?, 1)", (str(gdir),))
        con.execute("INSERT INTO games VALUES (8, 'Y', 'y', 'linux', '/nope', 1)")
        con.commit()
        con.close()
        games = lutris.detect(env)
        self.assertEqual([(g.key, g.platform) for g in games], [("lutris:7", "windows")])

    def test_custom_round_trip(self):
        env = fake_env("linux")
        d = env.home / "MyGame"
        write(d / "run.sh", "#!/bin/sh")
        g = custom.add_custom_game(env, "My Game", str(d), "linux", "run.sh")
        self.assertEqual(g.key, "custom:my-game")
        self.assertEqual([x.key for x in custom.detect(env)], ["custom:my-game"])


if __name__ == "__main__":
    unittest.main()
