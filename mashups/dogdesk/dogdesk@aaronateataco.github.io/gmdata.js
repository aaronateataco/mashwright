// Reads sprites out of a GameMaker Studio 1.4 data file (Undertale's game.unx / data.win / game.ios)
// on the player's own computer, and caches the frames DogDesk needs as PNGs. Only the chunks it needs
// are read (the file is ~140 MB); nothing is copied anywhere else.

import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import GdkPixbuf from 'gi://GdkPixbuf';

function readAt(stream, offset, length) {
    stream.seek(offset, GLib.SeekType.SET, null);
    const bytes = stream.read_bytes(length, null);
    return bytes.toArray();
}

function u32(view, o) { return view.getUint32(o, true); }

function le32(a) { return new DataView(a.buffer, a.byteOffset, a.byteLength).getUint32(0, true); }

export class GMData {
    constructor(path) {
        this.file = Gio.File.new_for_path(path);
        this.stream = this.file.read(null);
        const h0 = readAt(this.stream, 0, 8);
        const head = new DataView(h0.buffer, h0.byteOffset, h0.byteLength);
        if (String.fromCharCode(...readAt(this.stream, 0, 4)) !== 'FORM')
            throw new Error('not a GameMaker data file');
        const end = 8 + u32(head, 4);
        this.chunks = {};
        let pos = 8;
        while (pos < end) {
            const h = readAt(this.stream, pos, 8);
            const name = String.fromCharCode(...h.slice(0, 4));
            const size = new DataView(h.buffer, h.byteOffset, h.byteLength).getUint32(4, true);
            this.chunks[name] = {start: pos + 8, size};
            pos += 8 + size;
        }
        // The small chunks are read whole; offsets inside the file are absolute.
        this._buf = {};
        for (const name of ['SPRT', 'TPAG', 'STRG', 'TXTR', 'FONT', 'SOND', 'AUDO'].filter(n => n !== 'AUDO'))
            this._buf[name] = readAt(this.stream, this.chunks[name].start, this.chunks[name].size);
    }

    _view(name) {
        const b = this._buf[name];
        return new DataView(b.buffer, b.byteOffset, b.byteLength);
    }

    _at(name, absolute) { return absolute - this.chunks[name].start; }

    _string(ptr) {
        const v = this._view('STRG');
        const o = this._at('STRG', ptr);
        const n = u32(v, o - 4);
        return new TextDecoder().decode(this._buf.STRG.slice(o, o + n));
    }

    _list(name) {
        const v = this._view(name);
        const n = u32(v, 0);
        const out = [];
        for (let i = 0; i < n; i++)
            out.push(u32(v, 4 + 4 * i));
        return out;
    }

    sprites(wanted) {
        const v = this._view('SPRT');
        const tp = this._view('TPAG');
        const out = {};
        for (const p of this._list('SPRT')) {
            const o = this._at('SPRT', p);
            const name = this._string(u32(v, o));
            if (!wanted.includes(name))
                continue;
            const n = u32(v, o + 56);
            const frames = [];
            for (let i = 0; i < n; i++) {
                const t = this._at('TPAG', u32(v, o + 60 + 4 * i));
                const s = k => tp.getInt16(t + 2 * k, true);
                frames.push({sx: s(0), sy: s(1), sw: s(2), sh: s(3), tx: s(4), ty: s(5), page: tp.getUint16(t + 20, true)});
            }
            out[name] = {w: u32(v, o + 4), h: u32(v, o + 8), frames};
        }
        return out;
    }

    _tpag(absolute) {
        const tp = this._view('TPAG');
        const t = this._at('TPAG', absolute);
        const s = k => tp.getInt16(t + 2 * k, true);
        return {sx: s(0), sy: s(1), sw: s(2), sh: s(3), tx: s(4), ty: s(5), page: tp.getUint16(t + 20, true)};
    }

    // A bitmap font: {tpag, glyphs: {charCode: {x, y, w, h, shift, offset}}}
    font(name) {
        const v = this._view('FONT');
        for (const p of this._list('FONT')) {
            const o = this._at('FONT', p);
            if (this._string(u32(v, o)) !== name)
                continue;
            const glyphs = {};
            const n = u32(v, o + 40);
            for (let i = 0; i < n; i++) {
                const g = this._at('FONT', u32(v, o + 44 + 4 * i));
                const r = k => v.getUint16(g + 2 * k, true);
                glyphs[r(0)] = {x: r(1), y: r(2), w: r(3), h: r(4), shift: v.getInt16(g + 10, true), offset: v.getInt16(g + 12, true)};
            }
            return {tpag: this._tpag(u32(v, o + 28)), glyphs};
        }
        return null;
    }

    // An embedded sound's WAV bytes, by name (null if it isn't embedded).
    sound(name) {
        const v = this._view('SOND');
        for (const p of this._list('SOND')) {
            const o = this._at('SOND', p);
            if (this._string(u32(v, o)) !== name)
                continue;
            const id = v.getInt32(o + 32, true);
            if (id < 0)
                return null;
            const audo = this.chunks.AUDO.start;
            const ptr = le32(readAt(this.stream, audo + 4 + 4 * id, 4));
            const len = le32(readAt(this.stream, ptr, 4));
            return readAt(this.stream, ptr + 4, len);
        }
        return null;
    }

    page(index) {
        if (!this._pages)
            this._pages = {};
        if (this._pages[index])
            return this._pages[index];
        const v = this._view('TXTR');
        const ptrs = this._list('TXTR');
        const offs = ptrs.map(p => u32(v, this._at('TXTR', p) + 4));
        const start = offs[index];
        const later = offs.filter(x => x > start);
        const end = later.length ? Math.min(...later) : this.chunks.TXTR.start + this.chunks.TXTR.size;
        const png = readAt(this.stream, start, end - start);
        const loader = new GdkPixbuf.PixbufLoader();
        loader.write(png);
        loader.close();
        this._pages[index] = loader.get_pixbuf();
        return this._pages[index];
    }

    close() {
        this.stream.close(null);
    }
}

// Writes <dir>/font_<code>.png for printable ASCII glyphs of a font, scaled; returns the metrics.
export function extractFont(dataPath, name, dir, scale) {
    const gm = new GMData(dataPath);
    try {
        const f = gm.font(name);
        if (!f)
            return null;
        const page = gm.page(f.tpag.page);
        const out = {height: 0, glyphs: {}};
        GLib.mkdir_with_parents(dir, 0o755);
        for (let code = 32; code < 127; code++) {
            const g = f.glyphs[code];
            if (!g)
                continue;
            out.height = Math.max(out.height, g.h * scale);
            out.glyphs[code] = {w: g.w * scale, h: g.h * scale, shift: g.shift * scale, offset: g.offset * scale};
            if (g.w <= 0 || g.h <= 0)
                continue;
            const px = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, true, 8, g.w, g.h);
            page.copy_area(f.tpag.sx + g.x, f.tpag.sy + g.y, g.w, g.h, px, 0, 0);
            px.scale_simple(g.w * scale, g.h * scale, GdkPixbuf.InterpType.NEAREST)
                .savev(GLib.build_filenamev([dir, `font_${code}.png`]), 'png', [], []);
        }
        return out;
    } finally {
        gm.close();
    }
}

// Writes <dir>/<sound>.wav for each embedded sound found; returns the names written.
export function extractSounds(dataPath, names, dir) {
    const gm = new GMData(dataPath);
    try {
        const done = [];
        GLib.mkdir_with_parents(dir, 0o755);
        for (const n of names) {
            const wav = gm.sound(n);
            if (wav) {
                GLib.file_set_contents(GLib.build_filenamev([dir, `${n}.wav`]), wav);
                done.push(n);
            }
        }
        return done;
    } finally {
        gm.close();
    }
}

// Writes <dir>/<sprite>_<frame>.png for each sprite, scaled up with crisp pixels. Returns
// {sprite: {w, h, count}} with the scaled sizes.
export function extractSprites(dataPath, names, dir, scale) {
    const gm = new GMData(dataPath);
    try {
        const sprites = gm.sprites(names);
        const index = {};
        GLib.mkdir_with_parents(dir, 0o755);
        for (const [name, s] of Object.entries(sprites)) {
            s.frames.forEach((f, i) => {
                const frame = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, true, 8, s.w, s.h);
                frame.fill(0x00000000);
                gm.page(f.page).copy_area(f.sx, f.sy, f.sw, f.sh, frame, f.tx, f.ty);
                const big = frame.scale_simple(s.w * scale, s.h * scale, GdkPixbuf.InterpType.NEAREST);
                big.savev(GLib.build_filenamev([dir, `${name}_${i}.png`]), 'png', [], []);
            });
            index[name] = {w: s.w * scale, h: s.h * scale, count: s.frames.length};
        }
        return index;
    } finally {
        gm.close();
    }
}
