// DogDesk: the Annoying Dog from your own copy of Undertale, living on your GNOME desktop.
// It walks along your window tops, naps when you're away, notices notifications, sometimes "absorbs"
// a window you close, eats treats you give it, and keeps out of the way (never over fullscreen apps,
// still while you type, gone in the overview, out of the way of drags). It lives in Quick Settings.
// Its sprites, font and sounds are read from your Undertale install; nothing from the game ships here.

import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {QuickMenuToggle, SystemIndicator} from 'resource:///org/gnome/shell/ui/quickSettings.js';
import {Extension, gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

import {extractFont, extractSounds, extractSprites} from './gmdata.js';
import {findUndertale} from './locator.js';
import {Dog, SOUNDS, SPRITES} from './dog.js';

const CACHE_VERSION = 2;

const DogToggle = GObject.registerClass(
class DogToggle extends QuickMenuToggle {
    _init(ext) {
        super._init({title: _('Dog'), toggleMode: true});
        this._ext = ext;
        const s = ext._settings;
        this.subtitle = ext._dataPath ? null : _('Undertale not found');
        this.gicon = ext._iconFile ? Gio.FileIcon.new(Gio.File.new_for_path(ext._iconFile))
            : Gio.ThemedIcon.new('face-smile-symbolic');
        this.checked = !s.get_boolean('hidden');
        this.connect('notify::checked', () => s.set_boolean('hidden', !this.checked));
        s.connectObject('changed::hidden', () => {
            this.checked = !s.get_boolean('hidden');
        }, this);
        this.menu.setHeader(this.gicon, _('DogDesk'), _('A small white dog from Undertale'));
        const add = (label, fn) => {
            const item = new PopupMenu.PopupMenuItem(label);
            item.connect('activate', fn);
            this.menu.addMenuItem(item);
        };
        add(_('Give a treat'), () => ext._dog?.giveTreat());
        add(_('Call the dog over'), () => ext._callDog());
        add(_('Let it nap'), () => ext._dog?.sleep());
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        for (const [key, label] of [['chatty', _('Chatty')], ['sounds', _('Sounds')]]) {
            const sw = new PopupMenu.PopupSwitchMenuItem(label, s.get_boolean(key));
            sw.connect('toggled', (_i, on) => s.set_boolean(key, on));
            s.connectObject(`changed::${key}`, () => sw.setToggleState(s.get_boolean(key)), this);
            this.menu.addMenuItem(sw);
        }
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        add(_('Preferences'), () => ext.openPreferences());
    }

    destroy() {
        this._ext._settings.disconnectObject(this);
        super.destroy();
    }
});

export default class DogDeskExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._dataPath = findUndertale(this._settings.get_string('data-path'));
        if (this._dataPath) {
            try {
                this._loadCache();
            } catch (e) {
                logError(e, 'DogDesk: reading Undertale failed');
                this._dataPath = null;
            }
        }
        this._indicator = new SystemIndicator();
        this._toggle = new DogToggle(this);
        this._indicator.quickSettingsItems.push(this._toggle);
        Main.panel.statusArea.quickSettings.addExternalIndicator(this._indicator);
        if (!this._dataPath)
            return;

        this._settings.connectObject('changed::scale', () => this._restart(), this);
        this._settings.connectObject('changed::hidden', () => this._applyHidden(), this);
        this._applyHidden();

        // Notifications: the dog looks up and "reads" them (not in Do Not Disturb).
        Main.messageTray.connectObject('source-added', (_tray, source) => {
            source.connectObject('notification-added', () => {
                if (this._notificationsShown())
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
        this._saveDog();
        this._dog?.destroy();
        this._dog = null;
        Main.messageTray.disconnectObject(this);
        for (const source of Main.messageTray.getSources?.() ?? [])
            source.disconnectObject(this);
        global.display.disconnectObject(this);
        for (const a of global.get_window_actors())
            a.meta_window?.disconnectObject(this);
        this._settings?.disconnectObject(this);
        this._toggle?.destroy();
        this._indicator?.quickSettingsItems.forEach(i => i.destroy());
        this._indicator?.destroy();
        this._toggle = this._indicator = null;
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

    // Sprites, the dialogue font and the dog's sounds, read once from Undertale and cached.
    _loadCache() {
        const dir = this._cacheDir();
        const indexFile = GLib.build_filenamev([dir, 'index.json']);
        const info = Gio.File.new_for_path(this._dataPath).query_info('standard::size,time::modified', 0, null);
        const stamp = `${this._dataPath}|${info.get_size()}|${info.get_attribute_uint64('time::modified')}`;
        try {
            const [, bytes] = GLib.file_get_contents(indexFile);
            const saved = JSON.parse(new TextDecoder().decode(bytes));
            if (saved.stamp === stamp) {
                Object.assign(this, {_index: saved.index, _font: saved.font, _sounds: saved.sounds});
                this._iconFile = GLib.build_filenamev([dir, `${SPRITES.walkR}_0.png`]);
                return;
            }
        } catch (e) { /* no cache yet */ }
        const scale = this._settings.get_int('scale');
        this._index = extractSprites(this._dataPath, Object.values(SPRITES), dir, scale);
        this._font = extractFont(this._dataPath, 'fnt_maintext', dir, Math.max(1, scale - 1));
        this._sounds = extractSounds(this._dataPath, Object.values(SOUNDS), dir);
        GLib.file_set_contents(indexFile, JSON.stringify({stamp, index: this._index, font: this._font, sounds: this._sounds}));
        this._iconFile = GLib.build_filenamev([dir, `${SPRITES.walkR}_0.png`]);
    }

    _restart() {
        this._saveDog();
        this._dog?.destroy();
        this._dog = null;
        this._loadCache();
        this._applyHidden();
    }

    _saveDog() {
        if (this._dog && this._settings)
            this._settings.set_value('last-position', new GLib.Variant('(ii)', this._dog.position()));
    }

    _applyHidden() {
        const hidden = this._settings.get_boolean('hidden');
        if (hidden && this._dog) {
            this._saveDog();
            this._dog.destroy();
            this._dog = null;
        } else if (!hidden && !this._dog) {
            const [x, y] = this._settings.get_value('last-position').deepUnpack();
            this._dog = new Dog({index: this._index, dir: this._cacheDir(), settings: this._settings,
                font: this._font, startAt: x >= 0 ? [x, y] : null, playSound: name => this._play(name)});
        }
    }

    _play(name) {
        if (!this._settings?.get_boolean('sounds') || !this._sounds?.includes(name))
            return;
        const file = Gio.File.new_for_path(GLib.build_filenamev([this._cacheDir(), `${name}.wav`]));
        global.display.get_sound_player().play_from_file(file, 'DogDesk', null);
    }

    _callDog() {
        if (!this._dog)
            return;
        const [px] = global.get_pointer();
        const wa = Main.layoutManager.getWorkAreaForMonitor(global.display.get_current_monitor());
        this._dog.digTo({x: Math.max(wa.x + 40, Math.min(wa.x + wa.width - 40, px)), y: wa.y + wa.height});
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
            if (n === 2 && this._dog) {
                const tops = this._dog._surfaces().filter(s => s.win);
                if (tops.length)
                    this._dog.digTo({x: (tops[0].x1 + tops[0].x2) / 2, y: tops[0].y});
            }
            if (n === 4)
                this._dog?.say('* (The dog is posing for a photo.)');
            if (n === 5)
                this._dog?.giveTreat();
            if (n === 7) {
                Main.panel.statusArea.quickSettings.menu.open();
            }
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
            return n < 8 ? GLib.SOURCE_CONTINUE : GLib.SOURCE_REMOVE;
        });
    }
}
