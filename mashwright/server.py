"""Mashwright's local web UI: a small JSON API plus static files, on 127.0.0.1 only.

Every /api/ request needs the per-session token (X-Mashwright-Token); the Host header must be this
server (DNS-rebinding defence) and a cross-site Origin is refused. Long jobs run in threads.
"""

import collections
import inspect
import json
import logging
import mimetypes
import secrets
import shutil
import tempfile
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from . import __version__
from .model import MashwrightError
from .platforms import HostEnv

log = logging.getLogger(__name__)
UI_DIR = Path(__file__).parent / "ui"
MAX_UPLOAD = 2 << 30
MAX_JSON = 1 << 20


class LogBuffer(logging.Handler):
    def __init__(self, size: int = 300):
        super().__init__()
        self.lines = collections.deque(maxlen=size)

    def emit(self, record):
        self.lines.append(self.format(record))


class Server:
    def __init__(self, app, env: HostEnv, port: int = 0):
        self.app = app
        self.env = env
        self.token = secrets.token_urlsafe(24)
        self.jobs = {}
        self.lock = threading.Lock()
        self.logbuf = LogBuffer()
        self.logbuf.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
        logging.getLogger("mashwright").addHandler(self.logbuf)
        handler = _make_handler(self)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/"

    def serve_forever(self):
        self.httpd.serve_forever()

    def shutdown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    # ---- jobs ----
    def start_job(self, label: str, fn, *args) -> str:
        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "label": label, "state": "running", "progress": 0.0, "message": "", "result": None}
        with self.lock:
            self.jobs[jid] = job

        def progress(msg, frac):
            job["message"], job["progress"] = msg, frac

        def run():
            try:
                takes_progress = "progress" in inspect.signature(fn).parameters
                job["result"] = fn(*args, progress=progress) if takes_progress else fn(*args)
                job["state"] = "done"
                job["progress"] = 1.0
                log.info("%s: done", label)
            except MashwrightError as e:
                job["state"], job["message"] = "failed", str(e)
                log.warning("%s failed: %s", label, e)
            except Exception as e:
                job["state"], job["message"] = "failed", f"Unexpected error: {e}"
                log.exception("%s crashed", label)
        threading.Thread(target=run, daemon=True).start()
        return jid

    def state(self) -> dict:
        return {"version": __version__, "host": self.env.os,
                "games": [g.to_json() for g in self.app.games],
                "mashups": self.app.mashups()}


def _make_handler(srv: Server):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Mashwright"

        def log_message(self, fmt, *args):
            log.debug("http " + fmt, *args)

        # ---- helpers ----
        def _send(self, code: int, body: bytes, ctype: str = "application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                             "connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj).encode("utf-8"))

        def _host_ok(self) -> bool:
            host = self.headers.get("Host", "")
            return host in (f"127.0.0.1:{srv.port}", f"localhost:{srv.port}")

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            return origin is None or origin in (f"http://127.0.0.1:{srv.port}", f"http://localhost:{srv.port}")

        def _authed(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-Mashwright-Token", ""), srv.token)

        def _guard(self, api: bool) -> bool:
            if not self._host_ok():
                self._json(421, {"error": "wrong host"})
                return False
            if api and (not self._origin_ok() or not self._authed()):
                self._json(403, {"error": "forbidden"})
                return False
            return True

        def _body_json(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_JSON:
                raise MashwrightError("Request too large")
            raw = self.rfile.read(n) if n else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                raise MashwrightError("Bad JSON")
            if not isinstance(data, dict):
                raise MashwrightError("Bad JSON")
            return data

        # ---- GET ----
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path.startswith("/api/"):
                if not self._guard(True):
                    return
                if path == "/api/state":
                    return self._json(200, srv.state())
                if path == "/api/catalog":
                    force = "refresh=1" in self.path
                    return self._json(200, {"mashups": srv.app.catalog(force)})
                if path == "/api/melty":
                    from . import melty_wine
                    return self._json(200, melty_wine.status(srv.env))
                if path == "/api/log":
                    return self._json(200, {"lines": list(srv.logbuf.lines)})
                if path.startswith("/api/jobs/"):
                    job = srv.jobs.get(path.rsplit("/", 1)[-1])
                    return self._json(200, job) if job else self._json(404, {"error": "no such job"})
                return self._json(404, {"error": "not found"})
            if not self._guard(False):
                return
            if path.startswith("/art/"):
                return self._art(path)
            self._static(path)

        # Images: a game's local store artwork or a mashup's cover. <img> can't send headers, so the
        # token comes as ?t=; only files the app already knows about are served.
        def _art(self, path: str):
            from urllib.parse import parse_qs, unquote, urlparse
            q = parse_qs(urlparse(self.path).query)
            if not secrets.compare_digest((q.get("t") or [""])[0], srv.token):
                return self._send(403, b"forbidden", "text/plain")
            parts = [unquote(p) for p in path.split("/")[2:]]
            f = None
            if len(parts) == 3 and parts[0] == "game":
                g = srv.app.game(parts[1])
                f = (g.extra.get("art") or {}).get(parts[2]) if g else None
            elif len(parts) == 2 and parts[0] == "mashup":
                f = srv.app.cover_path(parts[1])
            elif len(parts) == 2 and parts[0] == "catalog":
                from . import catalog
                f = catalog.cover_file(srv.env, parts[1])
            if not f or not Path(f).is_file():
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            if not ctype.startswith("image/"):
                return self._send(404, b"not found", "text/plain")
            self._send(200, Path(f).read_bytes(), ctype)

        def _static(self, path: str):
            name = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (UI_DIR / name).resolve()
            if UI_DIR.resolve() not in target.parents or not target.is_file():
                return self._send(404, b"not found", "text/plain")
            body = target.read_bytes()
            if name == "index.html":
                body = body.replace(b"__MASHWRIGHT_TOKEN__", srv.token.encode())
                # Linux gets GNOME's Adwaita look; elsewhere Mashwright's own.
                body = body.replace(b"__MASHWRIGHT_THEME__", b"gnome" if srv.env.os == "linux" else b"mashwright")
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, body, ctype)

        # ---- POST ----
        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if not self._guard(True):
                return
            try:
                if path == "/api/import-upload":
                    return self._upload()
                data = self._body_json()
                app = srv.app
                if path == "/api/rescan":
                    app.rescan()
                    return self._json(200, srv.state())
                if path == "/api/import":
                    return self._json(200, {"recipe": app.import_path(str(data.get("path", "")))})
                if path == "/api/install":
                    jid = srv.start_job(f"Install {data.get('id')}", app.install, str(data.get("id", "")),
                                        data.get("choices") or {}, str(data.get("backend", "")))
                    return self._json(202, {"job": jid})
                if path == "/api/catalog/get":
                    jid = srv.start_job(f"Get {data.get('id')}", app.get_from_catalog, str(data.get("id", "")))
                    return self._json(202, {"job": jid})
                if path == "/api/melty/setup":
                    from . import melty_wine
                    jid = srv.start_job("Set up Melty", lambda progress=None: melty_wine.setup(srv.env, progress))
                    return self._json(202, {"job": jid})
                if path == "/api/melty/open":
                    from . import melty_wine
                    return self._json(200, {"message": melty_wine.open_melty(srv.env)})
                if path == "/api/desktop":
                    return self._json(200, app.set_desktop(str(data.get("id", "")), bool(data.get("on"))))
                if path == "/api/desktop/prefs":
                    return self._json(200, {"message": app.desktop_prefs(str(data.get("id", "")))})
                if path == "/api/uninstall":
                    jid = srv.start_job(f"Uninstall {data.get('id')}", app.uninstall, str(data.get("id", "")))
                    return self._json(202, {"job": jid})
                if path == "/api/launch":
                    return self._json(200, {"message": app.launch(str(data.get("id", "")))})
                if path == "/api/remove":
                    app.remove(str(data.get("id", "")))
                    return self._json(200, {"ok": True})
                if path == "/api/custom-game":
                    from .stores import custom
                    g = custom.add_custom_game(srv.env, str(data.get("title", "")), str(data.get("install_dir", "")),
                                               str(data.get("platform", "")), str(data.get("exe", "")))
                    app.rescan()
                    return self._json(200, {"game": g.to_json()})
                return self._json(404, {"error": "not found"})
            except MashwrightError as e:
                log.warning("%s", e)
                return self._json(400, {"error": str(e)})
            except Exception as e:
                log.exception("request failed")
                return self._json(500, {"error": f"Unexpected error: {e}"})

        def _upload(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_UPLOAD:
                return self._json(413, {"error": "Package too large or empty"})
            with tempfile.TemporaryDirectory(prefix="mashwright-up-") as td:
                f = Path(td) / "upload.mashwright"
                left = n
                with open(f, "wb") as out:
                    while left > 0:
                        chunk = self.rfile.read(min(left, 1 << 20))
                        if not chunk:
                            break
                        out.write(chunk)
                        left -= len(chunk)
                return self._json(200, {"recipe": srv.app.import_path(str(f))})

    return Handler


def _app_window_cmd(env: HostEnv, url: str) -> Optional[list]:
    """A Chromium-family browser in --app mode, if one is installed."""
    names = ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "brave-browser",
             "microsoft-edge", "msedge", "chrome"]
    for n in names:
        p = env.which(n)
        if p:
            return [p, f"--app={url}", "--new-window"]
    if env.os == "windows":
        for base in (env.env("ProgramFiles(x86)", "C:\\Program Files (x86)"), env.env("ProgramFiles", "C:\\Program Files")):
            for rel in ("Microsoft\\Edge\\Application\\msedge.exe", "Google\\Chrome\\Application\\chrome.exe"):
                p = Path(base) / rel
                if p.is_file():
                    return [str(p), f"--app={url}"]
    if env.os == "macos":
        for app in ("Google Chrome", "Microsoft Edge", "Chromium", "Brave Browser"):
            if Path(f"/Applications/{app}.app").is_dir():
                return ["open", "-na", app, "--args", f"--app={url}"]
    if env.os == "linux" and env.which("flatpak"):
        for fid in ("org.chromium.Chromium", "com.google.Chrome", "com.brave.Browser", "com.microsoft.Edge"):
            if Path(f"/var/lib/flatpak/app/{fid}").is_dir() or (env.home / ".local/share/flatpak/app" / fid).is_dir():
                return ["flatpak", "run", fid, f"--app={url}"]
    return None


def serve(env: HostEnv, open_browser: bool = True, port: int = 0) -> None:
    from .app import App
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    srv = Server(App(env), env, port)
    print(f"Mashwright is running at {srv.url}  (Ctrl+C to quit)")
    if open_browser and env.os == "linux" and not env.env("MASHWRIGHT_BROWSER"):
        from . import gnome_window
        if gnome_window.available():
            gnome_window.run(srv)
            return
    if open_browser:
        cmd = _app_window_cmd(env, srv.url)
        try:
            if cmd:
                import subprocess
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                webbrowser.open(srv.url)
        except OSError:
            webbrowser.open(srv.url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
