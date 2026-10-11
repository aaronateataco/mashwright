import json
import threading
import unittest
import urllib.error
import urllib.request

from helpers import fake_env, write
from mashwright.model import MashwrightError
from mashwright.targets import android, switch


class SwitchTest(unittest.TestCase):
    def test_ryujinx_yuzu_and_atmosphere(self):
        sd = fake_env().home / "sd"
        (sd / "atmosphere/contents/0100000000010000").mkdir(parents=True)
        env = fake_env("linux", volumes=[sd])
        (env.home / ".config/Ryujinx/games/01006F8002326000").mkdir(parents=True)
        (env.home / ".local/share/sudachi/load/0100000000010000").mkdir(parents=True)
        games = {g.store_id: g for g in switch.detect(env)}
        self.assertEqual(set(games), {"01006F8002326000", "0100000000010000"})
        g = games["0100000000010000"]
        kinds = sorted(b["kind"] for b in g.extra["mod_roots"])
        self.assertEqual(kinds, ["atmosphere", "yuzu"])
        self.assertTrue(switch.mod_root(g, "yuzu", "my-mod").as_posix().endswith("sudachi/load/0100000000010000/my-mod"))
        self.assertTrue(switch.mod_root(g, "atmosphere", "my-mod").as_posix().endswith("atmosphere/contents/0100000000010000"))


class AndroidTest(unittest.TestCase):
    def test_find_and_push(self):
        calls = []

        def run(cmd, timeout=0):
            calls.append(cmd)
            if cmd[1:] == ["devices"]:
                return 0, "List of devices attached\nABC\tdevice\nDEF\tunauthorized\n"
            if "pm" in cmd:
                return 0, "package:com.example.game\npackage:com.other\n"
            return 0, ""
        env = fake_env("linux", run=run, which=lambda n: "/usr/bin/adb" if n == "adb" else None)
        games = android.find(env, "com.example.game")
        self.assertEqual([g.extra["serial"] for g in games], ["ABC"])
        android.place(games[0], "/sdcard/Android/media/com.example.game/mods/a.pak", "/tmp/a.pak", env)
        self.assertIn("push", calls[-1])
        with self.assertRaises(MashwrightError):
            android.place(games[0], "/data/data/com.example.game/x", "/tmp/a", env)


class FakeApp:
    games = []

    def mashups(self):
        return []


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mashwright.server import Server
        cls.srv = Server(FakeApp(), fake_env("linux"))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def get(self, path, headers=None):
        req = urllib.request.Request(self.srv.url.rstrip("/") + path, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_token_required(self):
        self.assertEqual(self.get("/api/state")[0], 403)
        code, body = self.get("/api/state", {"X-Mashwright-Token": self.srv.token})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["games"], [])

    def test_wrong_host_and_origin(self):
        self.assertEqual(self.get("/api/state", {"X-Mashwright-Token": self.srv.token, "Host": "evil.example:80"})[0], 421)
        self.assertEqual(self.get("/api/state", {"X-Mashwright-Token": self.srv.token, "Origin": "http://evil.example"})[0], 403)

    def test_index_has_token_and_traversal_blocked(self):
        code, body = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn(self.srv.token.encode(), body)
        self.assertEqual(self.get("/../../mashwright/server.py")[0], 404)
        self.assertEqual(self.get("/%2e%2e/server.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
