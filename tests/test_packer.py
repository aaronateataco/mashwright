import json
import unittest
import zipfile

from helpers import fake_env, write
from mashwright import packer


class PackerTest(unittest.TestCase):
    def test_pack_melty_format_build(self):
        env = fake_env()
        src = env.home / "My Mashup"
        write(src / "recipe.json", json.dumps({
            "schemaVersion": 1, "games": [{"slug": "brotato", "role": "primary"}],
            "components": [{"id": "main", "fileName": "Mod.zip", "required": True}],
            "mappings": [{"component": "main", "from": "", "to": "{game}/mods"}]}))
        with zipfile.ZipFile(src / "Mod.zip", "w") as z:
            z.writestr("a.txt", "a")
        cover = write(env.home / "shot.png", data=b"\x89PNG....")
        out = packer.pack(str(src), str(env.home / "out.mashwright"), version="2.1", authors=["me"], cover=str(cover))
        with zipfile.ZipFile(out) as z:
            r = json.loads(z.read("mashwright.json"))
            self.assertEqual(sorted(z.namelist()), ["Mod.zip", "cover.png", "mashwright.json"])
        self.assertEqual((r["id"], r["version"], r["authors"], r["cover"]), ("my-mashup", "2.1", ["me"], "cover.png"))
        self.assertEqual(len(r["components"][0]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
