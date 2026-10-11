// DogDesk: the Annoying Dog from your own copy of Undertale, living on your GNOME desktop.
// It walks along your window tops, naps when you're away, notices notifications, sometimes "absorbs"
// a window you close, and keeps out of the way (it never covers fullscreen apps and dodges drags).
// Its sprites and music are read from your Undertale install; nothing from the game ships with this.

import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import St from 'gi://St';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension, gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

import {extractSprites} from './gmdata.js';
import {findUndertale, findMusic} from './locator.js';
import {Dog, SPRITES} from './dog.js';

const CACHE_VERSION = 1;

export default class DogDeskExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._signals = [];
        this._dataPath = findUndertale(this._settings.get_string('data-path'));
        this._indicator = new PanelMenu.Button(0.5, 'DogDesk', false);
        this._icon = new St.Icon({icon_name: 'face-smile-symbolic', style_class: 'system-status-icon'});
        this._indicator.add_child(this._icon);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
        if (!this._dataPath) {
            this._indicator.menu.addMenuItem(new PopupMenu.PopupMenuItem(
                _('Undertale not found: install it, or set its data file in the preferences'), {reactive: false}));
            this._addPrefsItem();
            return;
        }
        this._loadSprites();
        this._buildMenu();
        this._settings.connectObject('changed::scale', () => this._restart(), this);
        this._settings.connectObject('changed::hidden', () => this._applyHidden(), this);
        this._applyHidden();

        // Notifications: the dog looks up and "reads" them (not when Do Not Disturb is on).
        Main.messageTray.connectObject('source-added', (_tray, source) => {
            source.connectObject('notification-added', () => {
                if (Main.messageTray._bannerBlocked || !this._notificationsShown())
                    return;
                this._dog?.notified();
            }, this);
        }, this);
        // Closed windows: now and then the dog digs over and chews on what's left.
        global.display.connectObject('window-created', (_d, win) => {
            win.connectObject('unmanaging', w => {
                const r = w.get_frame_rect();
                if (w.get_window_type() === 0 && r.width > 200)
                    this._dog?.windowClosed(r);
            }, this);
        }, this);
        this._maybeSnapshot();
    }

    disable() {
        this._dog?.destroy();
        this._dog = null;
        Main.messageTray.disconnectObject(this);
        for (const source of Main.messageTray.getSources?.() ?? [])
            source.disconnectObject(this);
        global.display.disconnectObject(this);
        for (const a of global.get_window_actors())
            a.meta_window?.disconnectObject(this);
        this._settings?.disconnectObject(this);
        this._indicator?.destroy();
        this._indicator = null;
        if (this._snapTimer)
            GLib.source_remove(this._snapTimer);
        this._snapTimer = 0;
        this._settings = null;
    }

    _notificationsShown() {
        try {
            return new Gio.Settings({schema_id: 'org.gnome.desktop.notifications'}).get_boolean('show-banners');
        } catch (e) {
            return true;
        }
    }

    _cacheDir() {
        return GLib.build_filenamev([GLib.get_user_cache_dir(), 'dogdesk', `v${CACHE_VERSION}-x${this._settings.get_int('scale')}`]);
    }

    _loadSprites() {
        const dir = this._cacheDir();
        const indexFile = GLib.build_filenamev([dir, 'index.json']);
        const stamp = (() => {
            const info = Gio.File.new_for_path(this._dataPath).query_info('standard::size,time::modified', 0, null);
            return `${this._dataPath}|${info.get_size()}|${info.get_attribute_uint64('time::modified')}`;
        })();
        try {
            const [, bytes] = GLib.file_get_contents(indexFile);
            const saved = JSON.parse(new TextDecoder().decode(bytes));
            if (saved.stamp === stamp) {
                this._index = saved.index;
                return;
            }
        } catch (e) { /* no cache yet */ }
        this._index = extractSprites(this._dataPath, Object.values(SPRITES), dir, this._settings.get_int('scale'));
        GLib.file_set_contents(indexFile, JSON.stringify({stamp, index: this._index}));
    }

    _restart() {
        this._dog?.destroy();
        this._dog = null;
        this._loadSprites();
        this._applyHidden();
    }

    _applyHidden() {
        const hidden = this._settings.get_boolean('hidden');
        if (hidden && this._dog) {
            this._dog.destroy();
            this._dog = null;
        } else if (!hidden && !this._dog) {
            this._dog = new Dog({index: this._index, dir: this._cacheDir(), settings: this._settings,
                playSound: name => this._play(name)});
        }
        if (this._showItem)
            this._showItem.setToggleState(!hidden);
        const icon = GLib.build_filenamev([this._cacheDir(), `${SPRITES.walkR}_0.png`]);
        this._icon.gicon = Gio.FileIcon.new(Gio.File.new_for_path(icon));
    }

    _play(name) {
        if (!this._settings.get_boolean('sounds'))
            return;
        const file = findMusic(this._dataPath, name);
        if (file)
            global.display.get_sound_player().play_from_file(Gio.File.new_for_path(file), 'DogDesk', null);
    }

    _buildMenu() {
        const menu = this._indicator.menu;
        this._showItem = new PopupMenu.PopupSwitchMenuItem(_('Show the dog'), !this._settings.get_boolean('hidden'));
        this._showItem.connect('toggled', (_i, on) => this._settings.set_boolean('hidden', !on));
        menu.addMenuItem(this._showItem);
        const call = new PopupMenu.PopupMenuItem(_('Call the dog over'));
        call.connect('activate', () => {
            if (!this._dog)
                return;
            const [px] = global.get_pointer();
            const wa = Main.layoutManager.getWorkAreaForMonitor(Main.layoutManager.primaryIndex);
            this._dog.digTo({x: Math.max(wa.x + 40, Math.min(wa.x + wa.width - 40, px)), y: wa.y + wa.height});
        });
        menu.addMenuItem(call);
        const nap = new PopupMenu.PopupMenuItem(_('Let it nap'));
        nap.connect('activate', () => this._dog?.sleep());
        menu.addMenuItem(nap);
        const chatty = new PopupMenu.PopupSwitchMenuItem(_('Chatty'), this._settings.get_boolean('chatty'));
        chatty.connect('toggled', (_i, on) => this._settings.set_boolean('chatty', on));
        menu.addMenuItem(chatty);
        const sounds = new PopupMenu.PopupSwitchMenuItem(_("Sounds (from Undertale)"), this._settings.get_boolean('sounds'));
        sounds.connect('toggled', (_i, on) => this._settings.set_boolean('sounds', on));
        menu.addMenuItem(sounds);
        menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._addPrefsItem();
    }

    _addPrefsItem() {
        const prefs = new PopupMenu.PopupMenuItem(_('Preferences'));
        prefs.connect('activate', () => this.openPreferences());
        this._indicator.menu.addMenuItem(prefs);
    }

    // Development aid: DOGDESK_SNAPSHOT=/path/prefix saves a few screenshots of the desktop.
    _maybeSnapshot() {
        const prefix = GLib.getenv('DOGDESK_SNAPSHOT');
        if (!prefix)
            return;
        Main.overview.hide();
        let n = 0;
        this._snapTimer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 4, () => {
            n++;
            const file = Gio.File.new_for_path(`${prefix}${n}.png`);
            const stream = file.replace(null, false, Gio.FileCreateFlags.NONE, null);
            const shooter = new Shell.Screenshot();
            shooter.screenshot(false, stream, (_s, res) => {
                try {
                    shooter.screenshot_finish(res);
                } catch (e) {
                    logError(e, 'DogDesk snapshot');
                }
                stream.close(null);
            });
            if (n === 2 && this._dog) {
                const tops = this._dog._surfaces().filter(s => s.win);
                if (tops.length)
                    this._dog.digTo({x: (tops[0].x1 + tops[0].x2) / 2, y: tops[0].y});
            }
            if (n === 4)
                this._dog?.say('* (The dog is posing for a photo.)');
            if (n === 6)
                this._dog?.sleep();
            return n < 8 ? GLib.SOURCE_CONTINUE : GLib.SOURCE_REMOVE;
        });
    }
}
