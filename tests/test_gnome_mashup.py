import json
import unittest
import zipfile

from helpers import fake_env, steam_manifest, write
from mashwright import library
from mashwright import recipe as rcp
from mashwright.app import App


class GnomeMashupTest(unittest.TestCase):
    def test_extension_installs_and_is_enabled(self):
        calls = []

        def run(cmd, timeout=0):
            calls.append(cmd)
            if cmd[:2] == ["gsettings", "get"]:
                return 0, "['other@ext']"
            return (1, "doesn't exist") if cmd[1:2] == ["enable"] else (0, "")
        env = fake_env("linux", run=run, which=lambda n: "/usr/bin/" + n if n == "gnome-extensions" else None)
        root = env.home / ".local/share/Steam"
        steam_manifest(root, "391540", "Undertale", "Undertale")
        write(root / "steamapps/common/Undertale/assets/game.unx", data=b"FORM")
        write(root / "steamapps/common/Undertale/run.sh", "#!/bin/sh")
        pkg = env.home / "pkg"
        with zipfile.ZipFile(write(pkg / "ext.zip", data=b"").parent / "ext.zip", "w") as z:
            z.writestr("metadata.json", "{}")
            z.writestr("extension.js", "export default class {}")
        write(pkg / "mashwright.json", json.dumps({
            "mashwright": 1, "id": "pet", "title": "Pet", "version": "1",
            "games": [{"slug": "undertale", "role": "primary"}],
            "components": [{"id": "ext", "file": "ext.zip", "extract": True}],
            "mappings": [{"component": "ext", "to": "{gnome_extensions}/pet@test", "when": {"host": "linux"}}],
            "gnome_extension": "pet@test", "launch": {"kind": "desktop", "message": "On your desktop"}}))
        self.assertEqual(rcp.validate(json.loads((pkg / "mashwright.json").read_text())), [])
        library.import_path(env, pkg)
        app = App(env)
        app.install("pet")
        self.assertTrue((env.home / ".local/share/gnome-shell/extensions/pet@test/extension.js").is_file())
        self.assertIn(["gsettings", "set", "org.gnome.shell", "enabled-extensions", "['other@ext', 'pet@test']"], calls)
        self.assertEqual(app.launch("pet"), "On your desktop")
        state = app.set_desktop("pet", False)
        self.assertIn(["/usr/bin/gnome-extensions", "disable", "pet@test"], calls)
        self.assertEqual(state["extension"], "pet@test")
        app.uninstall("pet")
        self.assertFalse((env.home / ".local/share/gnome-shell/extensions/pet@test").exists())


if __name__ == "__main__":
    unittest.main()
