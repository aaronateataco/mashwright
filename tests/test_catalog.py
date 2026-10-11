import hashlib
import io
import json
import unittest
import zipfile
from unittest import mock

from helpers import fake_env, write
from mashwright import catalog, library
from mashwright.model import MashwrightError


def package_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mashwright.json", json.dumps({
            "mashwright": 1, "id": "demo", "title": "Demo", "version": "2.0",
            "games": [{"slug": "brotato", "role": "primary"}],
            "components": [{"id": "m", "file": "m.zip", "extract": True}],
            "mappings": [{"component": "m", "to": "{game}/mods"}]}))
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as iz:
            iz.writestr("a.txt", "a")
        z.writestr("m.zip", inner.getvalue())
    return buf.getvalue()


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.env = fake_env("linux")
        self.pkg = package_bytes()
        write(self.env.home / ".config/mashwright/catalogs.json", json.dumps(["https://example.test/index.json", "http://insecure/x.json"]))
        self.index = {"mashwright_catalog": 1, "name": "Test", "mashups": [
            {"id": "demo", "title": "Demo", "version": "2.0", "package_url": "https://example.test/demo.mashwright",
             "sha256": hashlib.sha256(self.pkg).hexdigest(), "size": len(self.pkg)},
            {"id": "bad", "title": "No checksum", "package_url": "https://example.test/x"}]}

    def fake_urlopen(self, req, timeout=0):
        url = req.full_url
        if url.endswith("index.json"):
            return FakeResp(json.dumps(self.index).encode())
        if url.endswith("demo.mashwright"):
            return FakeResp(self.pkg)
        raise OSError("404")

    def test_fetch_filters_and_download_verifies(self):
        self.assertEqual(catalog.catalog_urls(self.env), ["https://example.test/index.json"])
        with mock.patch("urllib.request.urlopen", self.fake_urlopen):
            items = catalog.fetch(self.env, force=True)
            self.assertEqual([e["id"] for e in items], ["demo"])
            r = catalog.download(self.env, "demo")
        self.assertEqual(r["id"], "demo")
        self.assertEqual(library.get(self.env, "demo")["version"], "2.0")

    def test_checksum_mismatch_refused(self):
        self.index["mashups"][0]["sha256"] = "0" * 64
        with mock.patch("urllib.request.urlopen", self.fake_urlopen):
            catalog.fetch(self.env, force=True)
            with self.assertRaises(MashwrightError):
                catalog.download(self.env, "demo")
        self.assertIsNone(library.get(self.env, "demo"))


if __name__ == "__main__":
    unittest.main()
