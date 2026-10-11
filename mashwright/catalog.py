"""Online mashup catalogs: JSON indexes (normally kept in a GitHub repo) listing mashups and where to
download their .mashwright packages (normally GitHub Releases).

catalog/index.json:
{
  "mashwright_catalog": 1,
  "name": "Mashwright community catalog",
  "mashups": [{
    "id": "hue-potato", "title": "Hue Potato", "version": "0.1.0", "authors": ["..."],
    "description": "...", "games": [{"slug": "brotato", "title": "Brotato"}, ...],
    "package_url": "https://github.com/<owner>/<repo>/releases/download/<tag>/hue-potato.mashwright",
    "sha256": "...", "size": 123, "cover_url": "https://raw.githubusercontent.com/.../cover.jpg",
    "homepage": "https://...", "links": {"melty": "https://melty.gg/m/<slug>"}
  }]
}

Catalog URLs come from <config>/catalogs.json (a list of URLs), defaulting to DEFAULT_CATALOGS.
Only https is fetched; packages are checked against their sha256 before import.
"""

import hashlib
import json
import logging
import re
import shutil
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from . import __version__
from .model import MashwrightError, is_slug
from .platforms import HostEnv, config_dir, data_dir

log = logging.getLogger(__name__)

DEFAULT_CATALOGS = ["https://raw.githubusercontent.com/aaronateataco/mashwright/main/catalog/index.json"]
MAX_INDEX = 4 << 20
MAX_PACKAGE = 2 << 30
MAX_IMAGE = 8 << 20
CACHE_SECONDS = 15 * 60
UA = f"Mashwright/{__version__} (+https://github.com)"


def catalog_urls(env: HostEnv) -> List[str]:
    f = config_dir(env) / "catalogs.json"
    try:
        urls = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(urls, list) and all(isinstance(u, str) for u in urls):
            return [u for u in urls if u.startswith("https://")]
    except (OSError, ValueError):
        pass
    return list(DEFAULT_CATALOGS)


def _get(url: str, limit: int, timeout: float = 20.0) -> bytes:
    if urlparse(url).scheme != "https":
        raise MashwrightError(f"Only https downloads are allowed: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(limit + 1)
    except OSError as e:
        raise MashwrightError(f"Couldn't download {url}: {e}")
    if len(data) > limit:
        raise MashwrightError(f"{url} is too large")
    return data


def _valid_entry(e) -> bool:
    return (isinstance(e, dict) and is_slug(str(e.get("id", ""))) and isinstance(e.get("title"), str)
            and str(e.get("package_url", "")).startswith("https://")
            and re.fullmatch(r"[0-9a-f]{64}", str(e.get("sha256", "")).lower() or "") is not None)


def fetch(env: HostEnv, force: bool = False) -> List[dict]:
    """Every mashup in every configured catalog (cached for a few minutes)."""
    cache = data_dir(env) / "catalog_cache.json"
    if not force:
        try:
            c = json.loads(cache.read_text(encoding="utf-8"))
            if time.time() - c.get("at", 0) < CACHE_SECONDS and c.get("urls") == catalog_urls(env):
                return c["mashups"]
        except (OSError, ValueError, KeyError):
            pass
    out: Dict[str, dict] = {}
    for url in catalog_urls(env):
        try:
            idx = json.loads(_get(url, MAX_INDEX).decode("utf-8"))
        except (MashwrightError, ValueError) as e:
            log.warning("catalog %s unavailable: %s", url, e)
            continue
        if not isinstance(idx, dict) or idx.get("mashwright_catalog") != 1:
            log.warning("catalog %s has an unknown format", url)
            continue
        for e in idx.get("mashups", []):
            if _valid_entry(e) and e["id"] not in out:
                e = dict(e)
                e["catalog"] = idx.get("name") or url
                out[e["id"]] = e
    mashups = sorted(out.values(), key=lambda e: e["title"].lower())
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"at": time.time(), "urls": catalog_urls(env), "mashups": mashups}), encoding="utf-8")
    except OSError:
        pass
    return mashups


def entry(env: HostEnv, mashup_id: str) -> dict:
    for e in fetch(env):
        if e["id"] == mashup_id:
            return e
    raise MashwrightError(f"{mashup_id} isn't in your catalogs")


def download(env: HostEnv, mashup_id: str, progress=None) -> dict:
    """Download a catalog mashup, check its checksum, and add it to the library."""
    from . import library
    e = entry(env, mashup_id)
    progress = progress or (lambda m, f: None)
    progress(f"Downloading {e['title']}", 0.05)
    with tempfile.TemporaryDirectory(prefix="mashwright-dl-") as td:
        f = Path(td) / f"{e['id']}.mashwright"
        req = urllib.request.Request(e["package_url"], headers={"User-Agent": UA})
        h = hashlib.sha256()
        total = int(e.get("size") or 0)
        done = 0
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(f, "wb") as out:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > MAX_PACKAGE:
                        raise MashwrightError("Package is too large")
                    h.update(chunk)
                    out.write(chunk)
                    if total:
                        progress(f"Downloading {e['title']}", 0.05 + 0.8 * min(1.0, done / total))
        except OSError as ex:
            raise MashwrightError(f"Download failed: {ex}")
        if h.hexdigest() != e["sha256"].lower():
            raise MashwrightError(f"{e['title']} failed its checksum; not installing it")
        progress("Adding to your library", 0.9)
        return library.import_path(env, f)


def cover_file(env: HostEnv, mashup_id: str) -> Optional[Path]:
    """A local copy of a catalog mashup's cover image (downloaded once)."""
    try:
        e = entry(env, mashup_id)
    except MashwrightError:
        return None
    url = e.get("cover_url")
    if not url or not url.startswith("https://"):
        return None
    ext = Path(urlparse(url).path).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        return None
    d = data_dir(env) / "catalog_art"
    f = d / (hashlib.sha256(url.encode()).hexdigest()[:24] + ext)
    if not f.is_file():
        try:
            data = _get(url, MAX_IMAGE)
        except MashwrightError as ex:
            log.warning("%s", ex)
            return None
        d.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    return f
