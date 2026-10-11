"""A native GNOME window for Mashwright (GTK 4 + libadwaita + WebKitGTK 6).

The header bar is real libadwaita: a view switcher (Mashups / Games / Add / Log), a Rescan button
and the main menu with About. The page below is Mashwright's own UI, drawn in Adwaita's style and kept
in step with the desktop's light/dark setting and accent colour. Used automatically on Linux when the
bindings are installed (Fedora Workstation and most GNOME desktops ship them); otherwise Mashwright
opens in a browser window instead.
"""

import json
import logging
import threading

log = logging.getLogger(__name__)

APP_ID = "io.github.mashwright.Mashwright"
TABS = [("discover", "Discover"), ("mashups", "Library"), ("games", "Games"), ("add", "Add"), ("log", "Log")]


def available() -> bool:
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        gi.require_version("WebKit", "6.0")
        from gi.repository import Adw, Gtk, WebKit  # noqa: F401
        return Adw.get_minor_version() >= 4
    except (ImportError, ValueError, AttributeError):
        return False


def run(srv) -> int:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("WebKit", "6.0")
    from gi.repository import Adw, Gio, GLib, Gtk, WebKit

    from . import __version__

    threading.Thread(target=srv.serve_forever, daemon=True).start()
    app = Adw.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
    GLib.set_application_name("Mashwright")

    def accent_hex(sm) -> str:
        try:
            c = sm.get_accent_color_rgba()
            return "#%02x%02x%02x" % (int(c.red * 255), int(c.green * 255), int(c.blue * 255))
        except AttributeError:
            return "#3584e4"

    def on_activate(_app):
        win = Adw.ApplicationWindow(application=app, title="Mashwright", default_width=1040, default_height=720)
        win.set_size_request(360, 400)
        sm = Adw.StyleManager.get_default()

        ucm = WebKit.UserContentManager()
        view = WebKit.WebView(user_content_manager=ucm)
        view.set_vexpand(True)
        view.get_settings().set_enable_developer_extras(False)
        view.set_background_color(_rgba(Gtk, "rgba(0,0,0,0)"))

        def js(code: str):
            view.evaluate_javascript(code, -1, None, None, None, None, None)

        def push_theme(*_a):
            js("window.mashwrightTheme && window.mashwrightTheme(%s)" % json.dumps(
                {"dark": sm.get_dark(), "accent": accent_hex(sm)}))

        # Header bar: view switcher, rescan, main menu.
        toggles = Adw.ToggleGroup()
        for name, label in TABS:
            toggles.add(Adw.Toggle(name=name, label=label))
        toggles.set_active_name("discover")
        syncing = {"from_page": False}

        def on_toggle(group, _p):
            if not syncing["from_page"]:
                js("window.mashwrightSelectTab && window.mashwrightSelectTab(%s)" % json.dumps(group.get_active_name()))
        toggles.connect("notify::active-name", on_toggle)

        header = Adw.HeaderBar()
        header.set_title_widget(toggles)
        rescan = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Look for Games Again")
        rescan.connect("clicked", lambda *_: js("window.mashwrightRescan && window.mashwrightRescan()"))
        header.pack_start(rescan)

        menu = Gio.Menu()
        menu.append("_About Mashwright", "app.about")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Main Menu")
        menu_btn.set_primary(True)
        header.pack_end(menu_btn)

        about = Gio.SimpleAction.new("about", None)

        def show_about(*_a):
            dlg = Adw.AboutDialog(
                application_name="Mashwright", application_icon=APP_ID, version=__version__,
                developer_name="Mashwright contributors", license_type=Gtk.License.MIT_X11,
                comments="An open-source launcher for game mashups and mods.\n\n"
                         "Inspired by Melty (melty.gg). Not affiliated with Melty or Stella Montis Inc.")
            dlg.present(win)
        about.connect("activate", show_about)
        app.add_action(about)

        # The page tells us when it switches tabs itself (e.g. after an import).
        def on_message(_ucm, value):
            try:
                data = json.loads(value.to_json(0))
            except Exception:
                return
            if isinstance(data, dict) and data.get("tab"):
                syncing["from_page"] = True
                toggles.set_active_name(data["tab"])
                syncing["from_page"] = False
        try:
            ucm.register_script_message_handler("mashwright", None)
        except TypeError:
            ucm.register_script_message_handler("mashwright")
        ucm.connect("script-message-received::mashwright", on_message)

        # Stay on Mashwright's own page; anything else opens in the default browser.
        def on_policy(_view, decision, kind):
            if kind not in (WebKit.PolicyDecisionType.NAVIGATION_ACTION, WebKit.PolicyDecisionType.NEW_WINDOW_ACTION):
                return False
            uri = decision.get_navigation_action().get_request().get_uri() or ""
            if uri.startswith(srv.url):
                return False
            decision.ignore()
            Gtk.UriLauncher.new(uri).launch(win, None, None, None)
            return True
        view.connect("decide-policy", on_policy)
        view.connect("load-changed", lambda v, ev: push_theme() if ev == WebKit.LoadEvent.FINISHED else None)
        sm.connect("notify::dark", push_theme)
        sm.connect("notify::accent-color", push_theme)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(view)
        win.set_content(toolbar)
        win.connect("close-request", lambda *_: (srv.shutdown(), False)[1])
        view.load_uri(srv.url + "?shell=gnome")
        win.present()
        shot = srv.env.env("MASHWRIGHT_SNAPSHOT")
        if shot:
            # Developer aid: save what the window shows (tabs given as name:file,name:file).
            plan = [p.split(":", 1) for p in shot.split(",")]

            def take(i=0):
                if i >= len(plan):
                    return False
                tab, path = plan[i]
                toggles.set_active_name(tab)
                GLib.timeout_add(900, lambda: (_save(Gtk, win, path), take(i + 1))[1] or False)
                return False
            GLib.timeout_add(2500, take)

    app.connect("activate", on_activate)
    return app.run([])


def _rgba(Gtk, spec: str):
    from gi.repository import Gdk
    c = Gdk.RGBA()
    c.parse(spec)
    return c


def _save(Gtk, win, path: str) -> None:
    w, h = win.get_width(), win.get_height()
    snap = Gtk.Snapshot()
    Gtk.WidgetPaintable(widget=win).snapshot(snap, w, h)
    node = snap.to_node()
    if node is not None:
        win.get_renderer().render_texture(node, None).save_to_png(path)
