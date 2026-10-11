# Mashwright

*A wright is a maker: a playwright makes plays, a wheelwright makes wheels, and a mashwright makes and
plays mashups.*

**Mashwright is an open-source launcher for game mashups and mods.** It finds the games you own (on
any store, on Linux, Windows or macOS), puts a mashup's files exactly where each game loads them,
starts the game, and takes everything back out again, leaving your game exactly as it was.

> Inspired by Melty (melty.gg). Mashwright is an independent project, not affiliated with or
> endorsed by Melty or Stella Montis Inc., and contains none of its code.

## Features
- **Finds your games**: Steam (native, Flatpak, Snap; every library; Proton-aware), Heroic (Epic, GOG,
  Amazon), Lutris, Epic Games Launcher, GOG Galaxy, itch.io, plus any folder you add by hand.
- **Safe installs**: every file it writes is journalled; files it replaces are backed up and put back
  byte-for-byte on uninstall. Archives that try to escape their folder are refused. A failed install
  rolls itself back.
- **Proton-aware**: `{appdata}` points inside the game's Proton prefix when a Windows game runs
  through Proton, so Windows mods "just work" on Linux.
- **Beyond PC** (your own, already-working setup only):
  - **Nintendo Switch**: Ryujinx/Ryubing and yuzu-family emulator mod folders, or Atmosphère's
    LayeredFS folder on your SD card.
  - **Android**: pushes mod files over `adb` into folders a game reads.
  - **iOS**: copies into apps that share their Documents folder (libimobiledevice + ifuse).
  - **Emulated consoles**: GameCube/Wii (Dolphin), 3DS (Azahar, Lime3DS, Citra), Wii U (Cemu),
    PSP (PPSSPP), PS1 (DuckStation), PS2 (PCSX2), PS3 (RPCS3): texture packs, graphics packs,
    LayeredFS mods and patches go into each emulator's own mod folder (native or Flatpak).
  - Xbox and PlayStation consoles have no supported way to load mods, so they aren't targets.
  Mashwright never touches console keys, firmware, game dumps, app encryption, jailbreaks or root.
- **Opens Melty-format packages**: a folder or zip with Melty's `recipe.json` beside its component
  zips (for example the files a creator builds for their own mashup) is converted and installed.
  Mashwright doesn't scrape, download from or sign in to Melty: Melty's terms forbid scraping and
  have players install Melty mashups through the Melty app.
- **Fits any build of a game**: Mashwright looks inside every component and identifies each binary
  (Windows PE, Linux ELF, macOS Mach-O, even inside nested archives). Hybrid packages that carry
  several builds in per-OS folders install only the one your game needs; Windows-only parts on a
  native Linux game, or DLL loaders under Proton, come with clear advice (force Proton, or the
  `WINEDLLOVERRIDES` launch option). `mashwright inspect ID` shows the full report.
- **Native on GNOME**: a libadwaita window (header bar, view switcher, About) that follows your
  accent colour and dark style; elsewhere it opens in a browser window.
- **No dependencies**: just Python 3.9+. A clean local web UI (dark and light) opens in its own window.

| | Linux (Fedora etc.) | Windows | macOS |
|---|---|---|---|
| Steam | ✓ native, Flatpak, Snap, Proton | ✓ | ✓ |
| Heroic (Epic/GOG/Amazon) | ✓ native + Flatpak | ✓ | ✓ |
| Lutris | ✓ | – | – |
| Epic launcher / GOG Galaxy | via Heroic | ✓ | ✓ |
| itch.io | ✓ | ✓ | ✓ |
| Switch emulators / SD card | ✓ | ✓ | ✓ |
| Android (adb) | ✓ | ✓ | ✓ |
| iOS (file-sharing apps) | ✓ | – | ✓ |
| Emulators (Dolphin, Azahar, Cemu, PPSSPP, DuckStation, PCSX2, RPCS3) | ✓ native + Flatpak | ✓ | ✓ |

## Quick start

**Fedora Workstation / any Linux**

    ./packaging/install-linux.sh        # adds Mashwright to your app menu and a `mashwright` command
    mashwright                            # or open "Mashwright" from the app menu

Or run it in place without installing: `python3 mashwright.py`.

**Windows**: double-click `packaging/run-windows.bat` (needs Python 3.9+).
**macOS**: double-click `packaging/run-macos.command`.

Then drop a `.mashwright` file on the **Add** tab, press **Install**, and **Play**.

## Command line

    mashwright                     open the window
    mashwright list                games found + mashups in your library
    mashwright import FILE         add a .mashwright package (or a mashup folder)
    mashwright install ID [--game slug=KEY] [--backend ryujinx|yuzu|atmosphere]
    mashwright launch ID
    mashwright uninstall ID        put the game back exactly as it was
    mashwright inspect ID          which platforms its binaries are for, and how it fits your game
    mashwright status ID           installed? any files changed since?
    mashwright remove ID           delete from your library
    mashwright doctor              what Mashwright can see on this computer

## Online catalog
**Discover → From the catalog** lists mashups from `catalog/index.json` in this repository; packages
are downloaded from GitHub Releases and checked against their sha256 before installing
(`mashwright catalog`, `mashwright get ID`). Add your own catalogs in
`~/.config/mashwright/catalogs.json`. To list a mashup, see `catalog/README.md`.

Mashwright doesn't scrape or download from Melty; a catalog entry can link to a mashup's Melty page.

## In this repository
- `mashwright/`, `mashwright.py`: the app. `tests/`: its tests (CI runs them on Linux, Windows, macOS).
- `catalog/`: the online catalog. `tools/catalog_entry.py`: adds a package to it.
- `examples/hue-potato/`: Hue Potato as a Mashwright package (`make_package.py`).
- `mashups/hue-potato/`: Hue Potato's full source (Brotato × Hue): design sheets, Godot mod,
  build tools. It contains nothing from either game; it reads Hue from the player's copy.

## Making a mashup

A mashup is a folder (or a `.mashwright` zip of it) with `mashwright.json` and its component files:

```json
{
  "mashwright": 1, "id": "hue-potato", "title": "Hue Potato", "version": "0.1.0",
  "games": [{"slug": "brotato", "role": "primary", "version": ">=1.1.15"},
            {"slug": "hue", "role": "secondary"}],
  "components": [{"id": "main", "file": "HuePotato-Mod.zip", "extract": true, "sha256": "…"}],
  "mappings": [{"component": "main", "from": "", "to": "{game}/mods"}],
  "launch": {"game": "brotato"}
}
```

- `extract: true` unzips a component (`from` picks a sub-folder); `false` copies the file itself.
- Placeholders: `{game}`, `{game:<slug>}`, `{appdata}` (Proton-aware), `{home}`, `{data}`,
  `{proton_prefix}`, `{proton_appdata}`, `{switch_mod}`, `{android_data}`, `{android_media}`,
  `{sdcard}`, `{ios_documents}`, `{emu_mod}`, `{emu_root}`.
- `when: {"host": "linux", "platform": "windows", "runner": "proton"}` limits a mapping.
- `settings` writes INI values (journalled and restored), e.g. a path a mod needs.
- Device games: give a game `"switch_title": "0100…"`, `"android_package": "com.x.y"` or
  `"ios_bundle": "com.x.y"`; emulated games `"emulator": {"system": "gamecube", "id": "GALE01"}`
  (systems: gamecube, wii, 3ds, wiiu, psp, ps1, ps2, ps3).
- Games are matched by slug: known store ids (see `mashwright/stores/__init__.py`) and title slugs.

See `SPEC.md` for the full design and `examples/hue-potato` for a real mashup.

## Proton notes
Windows-only mods work inside Proton prefixes. Mods that inject DLLs (e.g. `winhttp.dll` loaders)
also need `WINEDLLOVERRIDES="winhttp=n,b" %command%` in the game's Steam launch options.

## Safety model
Mashwright never runs code from a mashup: packages are data. It only writes inside the chosen games'
folders, their app-data folders, emulator mod folders and its own data folder. The local web UI
listens on 127.0.0.1 only and every request needs a per-session token.

## Tests

    python3 -m unittest discover -s tests

## Licence
MIT. See LICENSE and NOTICE.md.
