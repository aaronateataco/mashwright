// Finds the player's own Undertale data file: an explicit path from the settings, then every Steam
// library (native, Flatpak and Snap Steam; Linux, Windows/Proton and macOS builds), then common
// GOG/Heroic folders.

import GLib from 'gi://GLib';
import Gio from 'gi://Gio';

const DATA_FILES = ['assets/game.unx', 'data.win', 'UNDERTALE.app/Contents/Resources/game.ios', 'game.ios'];

function readText(path) {
    try {
        const [ok, bytes] = GLib.file_get_contents(path);
        return ok ? new TextDecoder().decode(bytes) : '';
    } catch (e) {
        return '';
    }
}

function exists(path) {
    return GLib.file_test(path, GLib.FileTest.EXISTS);
}

function steamLibraries() {
    const home = GLib.get_home_dir();
    const roots = ['.steam/steam', '.steam/root', '.local/share/Steam',
        '.var/app/com.valvesoftware.Steam/.local/share/Steam', '.var/app/com.valvesoftware.Steam/data/Steam',
        'snap/steam/common/.local/share/Steam', 'Library/Application Support/Steam'].map(r => GLib.build_filenamev([home, r]));
    const libs = [];
    for (const root of roots) {
        if (!exists(root))
            continue;
        libs.push(root);
        const text = readText(GLib.build_filenamev([root, 'steamapps', 'libraryfolders.vdf']));
        for (const m of text.matchAll(/"path"\s+"([^"]+)"/g))
            libs.push(m[1].replace(/\\\\/g, '/'));
    }
    // A library listed at a mount point that has moved: look for a SteamLibrary on any mounted drive.
    for (const base of ['/mnt', '/media', `/run/media/${GLib.get_user_name()}`]) {
        try {
            const e = Gio.File.new_for_path(base).enumerate_children('standard::name', 0, null);
            let info;
            while ((info = e.next_file(null)))
                libs.push(GLib.build_filenamev([base, info.get_name(), 'SteamLibrary']));
        } catch (err) { /* no such folder */ }
    }
    return [...new Set(libs)];
}

export function findUndertale(override) {
    if (override && exists(override))
        return override;
    const tried = [];
    for (const lib of steamLibraries()) {
        const game = GLib.build_filenamev([lib, 'steamapps', 'common', 'Undertale']);
        for (const rel of DATA_FILES) {
            const p = GLib.build_filenamev([game, rel]);
            tried.push(p);
            if (exists(p))
                return p;
        }
    }
    const home = GLib.get_home_dir();
    for (const dir of ['Games/Heroic/Undertale', 'GOG Games/Undertale', 'Games/Undertale']) {
        for (const rel of DATA_FILES) {
            const p = GLib.build_filenamev([home, dir, rel]);
            if (exists(p))
                return p;
        }
    }
    return null;
}

export function findMusic(dataPath, name) {
    // Undertale keeps its music as .ogg files next to its data file (Linux/Windows builds).
    const p = GLib.build_filenamev([GLib.path_get_dirname(dataPath), `${name}.ogg`]);
    return exists(p) ? p : null;
}
