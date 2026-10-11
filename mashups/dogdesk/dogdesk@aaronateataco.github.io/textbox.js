// The dog's text box: Undertale's own dialogue font (read from the player's copy and cached as
// glyph images), white on a black box with a white border. Text is word-wrapped and typed out a
// letter at a time. Without the font it falls back to a plain monospace label.

import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';

const MAX_WIDTH = 380;

export class TextBox {
    constructor(font, dir) {
        this._font = font;
        this._dir = dir;
        this.actor = new St.BoxLayout({style_class: 'dogdesk-bubble', orientation: Clutter.Orientation.VERTICAL, opacity: 0, reactive: false});
        if (!font) {
            this._label = new St.Label({style_class: 'dogdesk-bubble-text'});
            this.actor.add_child(this._label);
        }
        this._glyphs = [];
        this._text = '';
    }

    _width(word) {
        let w = 0;
        for (const c of word)
            w += (this._font.glyphs[c.charCodeAt(0)] || this._font.glyphs[63] || {shift: 8}).shift;
        return w;
    }

    // Lay the whole text out (hidden), so revealing letters never re-wraps a line.
    setText(text) {
        this._text = text;
        if (this._label) {
            this._label.text = '';
            return;
        }
        this.actor.destroy_all_children();
        this._glyphs = [];
        const space = this._width(' ');
        const lines = [[]];
        let lineW = 0;
        for (const word of text.split(' ')) {
            const w = this._width(word);
            if (lineW > 0 && lineW + space + w > MAX_WIDTH) {
                lines.push([]);
                lineW = 0;
            }
            lines[lines.length - 1].push(word);
            lineW += (lineW ? space : 0) + w;
        }
        lines.forEach((words, li) => {
            const row = new St.Widget({layout_manager: new Clutter.FixedLayout(), height: this._font.height});
            let x = 0;
            const lineText = words.join(' ') + (li < lines.length - 1 ? ' ' : '');
            for (const c of lineText) {
                const g = this._font.glyphs[c.charCodeAt(0)] || this._font.glyphs[63];
                if (!g)
                    continue;
                const cell = new St.Widget({opacity: 0, width: Math.max(1, g.w), height: Math.max(1, g.h)});
                if (g.w > 0 && c !== ' ') {
                    const file = GLib.build_filenamev([this._dir, `font_${c.charCodeAt(0)}.png`]);
                    cell.set_style(`background-image: url("file://${file}"); background-size: ${g.w}px ${g.h}px;`);
                }
                cell.set_position(x + g.offset, 0);
                row.add_child(cell);
                this._glyphs.push(cell);
                x += g.shift;
            }
            row.width = x;
            this.actor.add_child(row);
        });
    }

    // Show the first n characters.
    reveal(n) {
        if (this._label) {
            this._label.text = this._text.slice(0, n);
            return;
        }
        this._glyphs.forEach((g, i) => {
            g.opacity = i < n ? 255 : 0;
        });
    }

    get length() {
        return this._label ? this._text.length : this._glyphs.length;
    }

    destroy() {
        this.actor.destroy();
    }
}
