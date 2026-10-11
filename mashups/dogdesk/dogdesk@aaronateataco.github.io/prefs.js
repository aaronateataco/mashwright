import Adw from 'gi://Adw';
import Gtk from 'gi://Gtk';
import Gio from 'gi://Gio';
import {ExtensionPreferences, gettext as _} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class DogDeskPrefs extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const s = this.getSettings();
        const page = new Adw.PreferencesPage({title: _('DogDesk'), icon_name: 'face-smile-symbolic'});
        const dog = new Adw.PreferencesGroup({title: _('The dog'),
            description: _('A small white dog from your own copy of Undertale.')});
        const scale = new Adw.SpinRow({title: _('Size'), subtitle: _('Pixel scale of the sprites'),
            adjustment: new Gtk.Adjustment({lower: 1, upper: 4, step_increment: 1})});
        s.bind('scale', scale, 'value', Gio.SettingsBindFlags.DEFAULT);
        dog.add(scale);
        const nap = new Adw.SpinRow({title: _('Nap after'), subtitle: _('Minutes without input before it naps'),
            adjustment: new Gtk.Adjustment({lower: 1, upper: 60, step_increment: 1})});
        s.bind('idle-sleep-minutes', nap, 'value', Gio.SettingsBindFlags.DEFAULT);
        dog.add(nap);
        for (const [key, title, sub] of [
            ['chatty', _('Chatty'), _('Little text boxes now and then')],
            ['sounds', _('Sounds'), _("Undertale's dog jingle when you pet it")],
            ['hidden', _('Hide the dog'), _('Keep it off the desktop for now')]]) {
            const row = new Adw.SwitchRow({title, subtitle: sub});
            s.bind(key, row, 'active', Gio.SettingsBindFlags.DEFAULT);
            dog.add(row);
        }
        page.add(dog);
        const game = new Adw.PreferencesGroup({title: _('Undertale'),
            description: _('Found automatically in your Steam libraries. Set the data file (game.unx, data.win or game.ios) only if it isn\'t.')});
        const path = new Adw.EntryRow({title: _('Data file')});
        s.bind('data-path', path, 'text', Gio.SettingsBindFlags.DEFAULT);
        game.add(path);
        page.add(game);
        window.add(page);
    }
}
