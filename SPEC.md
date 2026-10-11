# Mashwright — architecture spec (source of truth for every module)

Mashwright is an original, open-source launcher for game **mashups and mods**: it finds the games a
player owns (any store, any OS), puts a mashup's files where the game loads them, starts the game,
and takes everything back out cleanly. It is inspired by Melty (melty.gg) but contains **no Melty code,
assets, branding or service calls**; it is not affiliated with Melty / Stella Montis Inc.

Licence: MIT. Language: **Python 3.9+ standard library only** (no pip installs) so it runs on a
stock Fedora Workstation, Windows 10/11 and macOS. UI: a local web app served by Python's
`http.server` on 127.0.0.1 and opened in the user's browser (Chromium/Chrome/Edge `--app` window if
found, else the default browser).

Hard rules (all modules):
- Never circumvent DRM or platform security. No console keys, firmware, ROM/ISO handling, no IPA
  decryption, no jailbreak/root tooling. Non-PC targets only place mod files where the user's own,
  already-working setup loads them (emulator mod folders, an Atmosphère SD card, adb-reachable
  Android folders, iOS apps that share their Documents folder).
- Never run code from a mashup package. Packages are data: files to place + metadata.
- Every file Mashwright writes into a game is journalled; uninstall restores the game exactly
  (originals it overwrote are backed up and put back).
- Zip extraction is safe: reject absolute paths, `..`, drive letters, symlinks; cap total size.
- The web server binds 127.0.0.1 only, checks the Host header (127.0.0.1/localhost with our port),
  and requires the per-session token (header `X-Mashwright-Token`) on every `/api/` call.
- Pure functions take explicit paths/env so tests can point them at fake directory trees: every
  detector accepts `env: HostEnv` (see `platforms.py`) instead of reading `os.environ`/`sys.platform`
  directly.

## Layout

```
Mashwright/
  mashwright.py                 # entry point: `python3 mashwright.py [ui|list|install|uninstall|launch|doctor]`
  mashwright/
    __init__.py                # __version__ = "0.1.0", APP_NAME = "Mashwright"
    platforms.py               # HostEnv, host detection, standard dirs
    vdf.py                     # Valve KeyValues (text) parser
    model.py                   # dataclasses shared by everyone (below)
    stores/
      __init__.py              # detect_all(env) -> list[Game]; DETECTORS list
      steam.py  epic.py  gog.py  heroic.py  lutris.py  itch.py  custom.py
    targets/
      __init__.py              # detect_all_targets(env) -> list[Game] for non-PC platforms
      switch.py  android.py  ios.py
    recipe.py                  # load/validate recipes, resolve placeholders
    installer.py               # install/uninstall with journal + backups
    launcher.py                # start a game (per store / OS / target)
    library.py                 # local mashup library (import .mashwright / folder, list, remove)
    server.py                  # http UI + JSON API
    ui/index.html ui/app.js ui/style.css
  tests/test_*.py              # unittest; fake trees under tempfile; no network, no real devices
  packaging/
    install-linux.sh           # copies to ~/.local/share/mashwright, writes ~/.local/bin/mashwright + .desktop
    mashwright.desktop
    mashwright.svg              # original icon
    run-windows.bat  run-macos.command
  examples/hue-potato/         # Hue Potato (Brotato x Hue) as a Mashwright mashup
  README.md  LICENSE  NOTICE.md (credits: inspired by Melty; vgmstream etc. where bundled)
```

## platforms.py

```python
@dataclass(frozen=True)
class HostEnv:
    os: str            # "windows" | "linux" | "macos"
    home: Path
    environ: Mapping[str, str]
    # Windows registry reader: (hive, key, value) -> str|None ; None on other OSes / in tests
    reg: Optional[Callable[[str, str, str], Optional[str]]] = None
    # Runs a command, returns (code, stdout). Injected so tests can fake adb/ideviceinstaller.
    run: Callable[[list[str], float], tuple[int, str]] = default_run
    which: Callable[[str], Optional[str]] = shutil.which

def current() -> HostEnv
def data_dir(env) -> Path      # windows %APPDATA%\Mashwright ; linux $XDG_DATA_HOME/mashwright (~/.local/share) ; macos ~/Library/Application Support/Mashwright
def config_dir(env) -> Path    # windows %APPDATA%\Mashwright ; linux $XDG_CONFIG_HOME/mashwright ; macos same as data_dir
def appdata_dir(env) -> Path   # the "per-user app data" a game would use: windows %APPDATA% ; linux $XDG_DATA_HOME ; macos ~/Library/Application Support
```

## model.py

```python
@dataclass
class Game:
    key: str              # globally unique: f"{store}:{store_id}" e.g. "steam:1942280", "switch:0100ABCD...", "android:com.foo.bar"
    store: str            # "steam"|"epic"|"gog"|"heroic"|"lutris"|"itch"|"custom"|"switch"|"android"|"ios"
    store_id: str
    title: str
    install_dir: Optional[Path]      # PC games: folder with the game; None for device targets
    platform: str                    # what the game binary is: "windows"|"linux"|"macos"|"switch"|"android"|"ios"
    runner: str = "native"           # "native"|"proton"|"wine"|"emulator:<name>"|"device"
    launch: dict = field(default_factory=dict)   # data launcher.py needs (url, exe, args, appid...)
    extra: dict = field(default_factory=dict)    # store-specific (proton prefix, emulator mod root, device serial...)
    slugs: list[str] = field(default_factory=list)  # recipe slugs this game satisfies (from KNOWN_GAMES + title slug)

@dataclass
class Placement:          # one resolved mapping
    component: str
    source: str            # path inside the component archive ("" = whole archive)
    dest: str              # resolved destination: absolute path (PC) or "device:<serial>:<path>" / "afc:<bundle>:<path>"

class MashwrightError(Exception): ...
```

`stores/__init__.py` also holds `KNOWN_GAMES`: a dict slug -> list of store keys,
e.g. `"brotato": ["steam:1942280"]`, `"hue": ["steam:383270", "gog:1207664943", "epic:..."]`
(fill only ids you are sure about; title-slug matching is the fallback: slug = lowercase title with
non-alphanumerics -> "-").

## Store detectors (stores/*.py) — each exposes `detect(env: HostEnv) -> list[Game]`, never raises
(log and return [] on any error).
- **steam**: library roots — windows: registry `HKCU\Software\Valve\Steam\SteamPath`, default
  `C:\Program Files (x86)\Steam`; linux: `~/.steam/steam`, `~/.local/share/Steam`,
  Flatpak `~/.var/app/com.valvesoftware.Steam/.local/share/Steam`, Snap `~/snap/steam/common/.local/share/Steam`;
  macos `~/Library/Application Support/Steam`. Parse `steamapps/libraryfolders.vdf` (both old and new
  formats) + every `steamapps/appmanifest_*.acf`. install_dir = `<lib>/steamapps/common/<installdir>`
  if it exists. Linux: if `<lib>/steamapps/compatdata/<appid>/pfx` exists or the install contains
  only Windows binaries (`*.exe`, no ELF/`.x86_64`/`.sh`), runner="proton", platform="windows",
  extra["prefix"]=that pfx path. launch={"url": "steam://rungameid/<appid>"}. Skip tools/runtimes
  (appids 228980, 1070560, 1391110, 1628350, 1493710, 1826330, 2180100, 2348590 and names starting
  "Proton"/"Steam Linux Runtime"/"Steamworks").
- **epic**: windows/macos launcher manifests (`%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests\*.item`,
  `~/Library/Application Support/Epic/EpicGamesLauncher/Data/Manifests/*.item`; JSON keys
  `InstallLocation`, `DisplayName`, `AppName`, `CatalogNamespace`, `CatalogItemId`).
  launch url `com.epicgames.launcher://apps/<ns>%3A<item>%3A<AppName>?action=launch&silent=true`.
- **gog**: windows registry `HKLM\SOFTWARE\WOW6432Node\GOG.com\Games\<id>` (`path`, `gameName`,
  `exe`) — implement with env.reg enumerating via a helper `env.reg_subkeys` if available, else
  scan `C:\GOG Games\*\goggame-*.info` JSON files; macos `/Applications/*.app/Contents/Resources/goggame-*.info`.
- **heroic** (linux/macos; also Flatpak `~/.var/app/com.heroicgameslauncher.hgl/config/heroic`):
  Epic via `legendaryConfig/legendary/installed.json`, GOG via `gog_store/installed.json` +
  `gog_store/library.json` for titles, Amazon via `nile_config/nile/installed.json`; launch via
  `heroic://launch/<runner>/<appName>` url. platform/runner from the entry (`platform`, `is_installed`;
  windows games on linux run via wine/proton -> runner "wine").
- **lutris** (linux): sqlite `~/.local/share/lutris/pga.db` table `games` (slug, name, directory,
  runner, installed). launch `lutris:rungameid/<id>`.
- **itch** (all): butler db `<itch config>/db/butler.db` (`caves` table: game_id, install_folder_name,
  install location in `install_locations`) — best effort; tolerate schema differences.
- **custom**: user-added folders stored in `config_dir/custom_games.json`
  `[{"title","slug","install_dir","platform","exe"}]`; launch = run exe (or proton/wine note).

## Non-PC targets (targets/*.py) — `detect(env) -> list[Game]`, `place(game, rel_dest, src_file, env)`,
`remove(game, rel_dest, env)`, `exists(game, rel_dest, env) -> bool`; for local-folder targets placing is
plain file IO and the installer handles it; device targets (android/ios) implement place/remove.
- **switch**: emulators, all OSes — Ryujinx & Ryubing (data dir `%APPDATA%/Ryujinx`,
  `~/.config/Ryujinx`, `~/Library/Application Support/Ryujinx`, Flatpak `org.ryujinx.Ryujinx`):
  mod root `<data>/mods/contents/<titleid>/<modname>/` (romfs/, exefs/); titles from
  `<data>/games/<titleid>` folders. yuzu-family (yuzu, suyu, sudachi, citron, eden; data dirs
  `%APPDATA%/<name>`, `~/.local/share/<name>`, Flatpak, mac Application Support): mod root
  `<data>/load/<titleid>/<modname>/`; titles from `<data>/load/*` and `<data>/cache/game_list/*`.
  Atmosphère SD card: any mounted volume with `/atmosphere/` (Windows drive letters; linux
  `/run/media/$USER/*`, `/media/$USER/*`; macos `/Volumes/*`): mod root `atmosphere/contents/<titleid>/`.
  Game: store "switch", store_id = 16-hex title id (upper), install_dir = None,
  extra = {"mod_roots": [{"kind": "ryujinx"|"yuzu-family:<name>"|"atmosphere", "path": str}]}.
  Recipe placeholder `{switch_mod}` -> `<mod root for chosen backend>` (for emulators includes
  `<modname>/` = the mashup slug; for Atmosphère the contents/<titleid> dir).
  Titles are 16 hex chars; recipes declare them; no title keys or dumps are ever touched.
- **android**: needs `adb` on PATH (env.which). `adb devices` -> serials; `adb -s S shell pm list packages`
  -> packages; Game per (serial, package) only for packages a recipe asks for (detect returns the
  device list in extra; `find(env, package)` returns Games). Placeholder `{android_data}` ->
  `/sdcard/Android/data/<package>/files`, `{android_media}` -> `/sdcard/Android/media/<package>`,
  `{sdcard}` -> `/sdcard`. place = `adb -s S push`, remove = `adb -s S shell rm -f`. Report clearly when
  Android 11+ blocks Android/data (push fails) — suggest the game's documented mod folder instead.
- **ios**: needs libimobiledevice: `idevice_id -l`, `ideviceinstaller -l -o list_user` (or `ideviceinstaller list --user`)
  -> bundle ids; only apps with file sharing (Documents) are usable: placing uses `ifuse --documents <bundle> <mountpoint>`
  (linux/macos) then plain copy, then `fusermount -u`/`umount`. Placeholder `{ios_documents}`.
  On Windows report "iOS needs Linux or macOS with libimobiledevice + ifuse".

## recipe.py — Mashwright recipe (`mashwright.json` at the root of a mashup folder or .mashwright zip)

```json
{
  "mashwright": 1,
  "id": "hue-potato",                 // slug, [a-z0-9-]
  "title": "Hue Potato",
  "version": "0.1.0",
  "authors": ["..."], "license": "MIT", "description": "markdown", "homepage": "",
  "games": [ {"slug": "brotato", "role": "primary", "version": ">=1.1.15",
              "platforms": ["windows", "linux", "macos"] },
             {"slug": "hue", "role": "secondary", "optional": false } ],
  "components": [ {"id": "main", "file": "HuePotato-Mod.zip", "sha256": "...", "extract": false,
                   "label": "..."} ],
  "mappings": [ {"component": "main", "from": "", "to": "{game}/mods", "when": {"platform": "windows"}} ],
  "launch": {"game": "brotato", "args": []},
  "notes": {"firstLaunch": "...", "linux": "..."},
  "settings": [ {"file": "{appdata}/Brotato/huepotato.cfg", "section": "hue", "key": "data_dir",
                 "value": "{game:hue}/Hue_Data", "when": {"host": "linux"}} ]   // optional INI-style values Mashwright writes (journalled)
}
```
- `extract`: true = unzip the component into `to`; false = copy the file itself into `to` (keeps
  e.g. a Godot mod zip as a zip). `from` = sub-path inside the archive (extract=true) to take.
- Placeholders: `{game}` (primary install_dir), `{game:<slug>}`, `{appdata}`, `{home}`, `{data}` (Mashwright
  data dir for this mashup), `{switch_mod}`, `{android_data}`, `{android_media}`, `{sdcard}`,
  `{ios_documents}`, `{proton_prefix}` (game's prefix `pfx/drive_c` on linux+proton),
  `{proton_appdata}` (`<pfx>/drive_c/users/steamuser/AppData/Roaming`). A mapping whose placeholder can't
  be resolved for the chosen game is an error unless `"optional": true`.
- `when`: {"platform": game platform, "host": host os, "runner": ...}; all listed keys must match.
- Validation returns a list of human-readable problems (empty = valid). `version` checks use simple
  semver comparisons; when a store gives no version, the check is skipped with a warning.

## installer.py

```python
def plan(recipe, mashup_dir, games: dict[slug, Game], env) -> list[Placement]
def install(recipe, mashup_dir, games, env, on_progress=None) -> Journal   # atomic-ish: on failure rolls back
def uninstall(journal_path or mashup id, env) -> None                      # restores backups, removes created files/dirs (only empty dirs it created)
def status(mashup_id, env) -> dict                                        # installed? files ok? (sha256 check)
```
Journal JSON at `data_dir/installed/<mashup-id>.json`: entries `{"op":"create"|"overwrite"|"mkdir"|"setting",
"path", "sha256", "backup"}`; backups under `data_dir/backups/<mashup-id>/`. Device targets journal
`device:` / `afc:` paths and remove them on uninstall. Re-install = uninstall then install.

## launcher.py
`launch(game, env, args=[]) -> None`: steam/epic/heroic/lutris/gog URLs via `os.startfile` (windows),
`xdg-open` (linux), `open` (macos); custom/native exe via subprocess (cwd=install dir); switch: start the
emulator if found (`ryujinx`/`Ryujinx.exe` etc.) — never pass keys; android: `adb shell monkey -p <pkg> -c
android.intent.category.LAUNCHER 1`; ios: tell the user to open the app on the device.

## library.py
Mashups live in `data_dir/mashups/<id>/` (mashwright.json + component files). `import_path(path)`: a
`.mashwright`/`.zip` (safe-extract) or a folder (copy); validates the recipe and component sha256.
`list()`, `get(id)`, `remove(id)` (refuses while installed).

## server.py + ui/
`serve(env, open_browser=True, port=0)`. API (JSON, token header required):
`GET /api/state` -> {version, host, games:[...], mashups:[{recipe, installed, ready, missing_games, problems}]},
`POST /api/rescan`, `POST /api/import {path}`, `POST /api/install {id, choices:{slug: game_key}}`,
`POST /api/uninstall {id}`, `POST /api/launch {id}`, `POST /api/custom-game {...}`, `GET /api/log`.
Long actions run in a worker thread; `GET /api/jobs/<id>` for progress. Static files from `ui/`.
The token is injected into index.html at serve time (`window.MASHWRIGHT_TOKEN`).
UI: library grid of mashups (title, games needed with ✓/✗ per detected game, Install / Play / Remove),
a Games tab (everything detected, grouped by store/platform, with runner badges like "Proton"),
an "Add game folder" form, an Import button (path text field + drag-drop of a .mashwright file which
is uploaded to `/api/import-upload`), a log panel. Clean, modern, dark+light theme, no external CDNs
(fully offline). Accessible (labels, keyboard).

## CLI (mashwright.py)
`ui` (default), `list` (games + mashups), `import <path>`, `install <id> [--game slug=key]`,
`uninstall <id>`, `launch <id>`, `doctor` (prints host, store roots found, tools found: adb,
ideviceinstaller, ifuse, emulators). Exit code non-zero on errors with a clear message.

## Tests
`python -m unittest discover -s tests` must pass on Windows and Linux without network/devices. Use
temp dirs to fake: Steam libraries (incl. Flatpak path, compatdata/pfx, both vdf formats), Heroic
installed.json files, Lutris pga.db (create with sqlite3), Epic .item manifests, Ryujinx/yuzu dirs, an
Atmosphère card, fake `run` for adb/ideviceinstaller output; installer round trips (install ->
files present -> uninstall -> tree byte-identical to before, overwrites restored), zip-slip rejection,
recipe validation errors, server token/Host checks.
