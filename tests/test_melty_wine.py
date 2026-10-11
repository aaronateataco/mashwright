import os
import unittest

from helpers import fake_env, write
from mashwright import melty_wine as mw
from mashwright.model import MashwrightError


class MeltyWineTest(unittest.TestCase):
    def test_library_drive_letters_and_vdf(self):
        env = fake_env("linux")
        inside = env.home / ".steam/steam"
        outside = fake_env().home / "disk-0:0-part1"   # outside home, with a ':' Windows can't use
        inside.mkdir(parents=True)
        outside.mkdir(parents=True)
        pairs = mw.map_libraries(env, [inside, outside])
        self.assertTrue(pairs[0][1].startswith("Z:"))
        self.assertTrue(pairs[1][1].startswith("G:\\"))
        link = mw.prefix(env) / "dosdevices" / "g:"
        self.assertTrue(link.is_symlink())
        again = mw.map_libraries(env, [inside, outside])   # stable: same letter reused
        self.assertEqual(again[1][1], pairs[1][1])

    def test_status_and_guards(self):
        env = fake_env("linux", which=lambda n: None)
        st = mw.status(env)
        self.assertFalse(st["installed"])
        with self.assertRaises(MashwrightError):
            mw.open_melty(env)
        with self.assertRaises(MashwrightError):
            mw.setup(fake_env("windows"))


if __name__ == "__main__":
    unittest.main()
