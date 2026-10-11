// The dog: a small actor in the Shell's chrome layer that walks along the tops of your windows and
// the bottom of the screen, naps when you're away, and keeps out of your way.

import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Meta from 'gi://Meta';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const TICK_MS = 50;
const FRAME_MS = 260;
const GRAVITY = 1800;      // px/s²
const WALK_SPEED = 46;     // px/s at scale 2
const NEAR_PX = 90;

export const SPRITES = {
    walkL: 'spr_tobdogl', walkR: 'spr_tobdogr', sleep: 'spr_sleepdog', wake: 'spr_wakedog',
    talk: 'spr_tobdogl_talk', emerge: 'spr_emergentdog', scoot: 'spr_tobydogscoot_small',
    eat: 'spr_tobydogeat_small', pile: 'spr_tobdog_pile',
};

export const LINES = {
    pet: ['* (You pet the dog.)', '* (The dog wags its tail.)', '* (Bark!)', '* (The dog seems very pleased.)'],
    chatter: ['* (The dog is guarding your windows.)', '* (The dog found a comfy title bar.)',
        "* (It's a small, white dog.)", '* (The dog sniffs your desktop.)', '* (The dog is doing its best.)'],
    notify: ['* (A message! The dog pretends to read it.)', '* (The dog barks at the notification.)'],
    absorb: ['* (The dog absorbed the window.)', '* (The dog chews on what is left of the window.)'],
    sleep: ['* (The dog fell asleep.)'],
    wake: ['* (The dog wakes up.)'],
};

function pick(list) {
    return list[Math.floor(Math.random() * list.length)];
}

export class Dog {
    constructor({index, dir, settings, playSound}) {
        this._index = index;
        this._dir = dir;
        this._settings = settings;
        this._playSound = playSound;
        this.actor = new St.Widget({reactive: true, track_hover: true, name: 'dogdesk-dog'});
        Main.layoutManager.addChrome(this.actor, {trackFullscreen: true});
        this.actor.connect('button-press-event', () => {
            this.pet();
            return Clutter.EVENT_STOP;
        });
        this._bubble = new St.Label({style_class: 'dogdesk-bubble', opacity: 0, reactive: false});
        this._bubbleShown = false;
        Main.layoutManager.addChrome(this._bubble, {trackFullscreen: true});

        const wa = this._workArea();
        this.x = wa.x + wa.width * (0.2 + Math.random() * 0.6);
        this.y = wa.y + wa.height;
        this.vy = 0;
        this.facing = 1;
        this.state = 'emerge';
        this.stateTime = 0;
        this.nextDecision = 3;
        this.frame = 0;
        this._frameTime = 0;
        this._sprite = null;
        this._lastPointer = global.get_pointer();
        this._pointerStill = 0;
        this._lastActive = GLib.get_monotonic_time();
        this._talkUntil = 0;
        this._chatterAt = this._now() + 60 + Math.random() * 120;
        this._absorbReadyAt = 0;
        this._setSprite('emerge', 0);
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, TICK_MS, () => {
            try {
                this._tick(TICK_MS / 1000);
            } catch (e) {
                logError(e, 'DogDesk tick');
            }
            return GLib.SOURCE_CONTINUE;
        });
    }

    destroy() {
        if (this._timer)
            GLib.source_remove(this._timer);
        if (this._typeTimer)
            GLib.source_remove(this._typeTimer);
        this._timer = this._typeTimer = 0;
        this.actor.destroy();
        this._bubble.destroy();
    }

    _now() {
        return GLib.get_monotonic_time() / 1e6;
    }

    _scale() {
        return this._settings.get_int('scale');
    }

    _workArea() {
        const mon = this._monitorIndex ?? Main.layoutManager.primaryIndex;
        return Main.layoutManager.getWorkAreaForMonitor(mon);
    }

    // ---- sprites ----------------------------------------------------------------------------

    _setSprite(key, frame) {
        const name = SPRITES[key];
        const info = this._index[name];
        if (!info)
            return;
        frame %= info.count;
        const id = `${name}_${frame}`;
        if (this._sprite === id)
            return;
        this._sprite = id;
        this._spriteInfo = info;
        const file = GLib.build_filenamev([this._dir, `${id}.png`]);
        this.actor.set_size(info.w, info.h);
        this.actor.set_style(`background-image: url("file://${file}"); background-size: ${info.w}px ${info.h}px;`);
        this._place();
    }

    _place() {
        const info = this._spriteInfo;
        if (!info)
            return;
        this.actor.set_position(Math.round(this.x - info.w / 2), Math.round(this.y - info.h));
        if (this._bubbleShown)
            this._placeBubble();
    }

    // ---- the world: surfaces the dog can stand on --------------------------------------------

    _surfaces() {
        const wa = this._workArea();
        const out = [{x1: wa.x, x2: wa.x + wa.width, y: wa.y + wa.height, win: null}];
        const ws = global.workspace_manager.get_active_workspace();
        const wins = global.display.sort_windows_by_stacking(
            global.get_window_actors().map(a => a.meta_window).filter(w =>
                w && !w.minimized && w.get_window_type() === Meta.WindowType.NORMAL &&
                w.located_on_workspace(ws) && !w.is_fullscreen() && w.showing_on_its_workspace()));
        const rects = wins.map(w => w.get_frame_rect());
        wins.forEach((w, i) => {
            const r = rects[i];
            if (r.y <= wa.y + 4 || r.y > wa.y + wa.height - 40 || r.width < 120)
                return;   // maximised or off-screen tops aren't somewhere to stand
            // The visible stretches of this window's top edge (windows above it cut pieces out).
            let parts = [[Math.max(r.x, wa.x), Math.min(r.x + r.width, wa.x + wa.width)]];
            for (let j = i + 1; j < rects.length; j++) {
                const o = rects[j];
                if (o.y <= r.y - 2 && o.y + o.height > r.y - 2) {
                    parts = parts.flatMap(([a, b]) => {
                        const res = [];
                        if (o.x > a)
                            res.push([a, Math.min(b, o.x)]);
                        if (o.x + o.width < b)
                            res.push([Math.max(a, o.x + o.width), b]);
                        return res;
                    });
                }
            }
            for (const [a, b] of parts) {
                if (b - a > 60)
                    out.push({x1: a, x2: b, y: r.y, win: w});
            }
        });
        return out;
    }

    _surfaceUnder(surfaces) {
        const w = this._spriteInfo ? this._spriteInfo.w / 2 : 20;
        return surfaces.find(s => Math.abs(s.y - this.y) < 3 && this.x >= s.x1 - w * 0.3 && this.x <= s.x2 + w * 0.3);
    }

    // ---- behaviour ---------------------------------------------------------------------------

    _tick(dt) {
        const now = this._now();
        this.stateTime += dt;
        this._frameTime += dt * 1000;
        const surfaces = this._surfaces();
        this._trackPointer(dt);
        this._trackIdle();

        let ground = this._surfaceUnder(surfaces);
        if (this.state !== 'emerge' && this.state !== 'dig') {
            if (!ground && this.state !== 'fall') {
                this.state = 'fall';
                this.vy = 0;
            }
            // Ride along with the window it is standing on.
            if (ground && ground.win && this._groundWin === ground.win && this._groundRect) {
                const r = ground.win.get_frame_rect();
                this.x += r.x - this._groundRect.x;
                this._groundRect = {x: r.x};
            }
            if (ground) {
                this._groundWin = ground.win;
                this._groundRect = ground.win ? {x: ground.win.get_frame_rect().x} : null;
            }
        }

        switch (this.state) {
        case 'fall': {
            this.vy += GRAVITY * dt;
            const ny = this.y + this.vy * dt;
            const land = surfaces.filter(s => s.y >= this.y - 1 && s.y <= ny && this.x >= s.x1 && this.x <= s.x2)
                .sort((a, b) => a.y - b.y)[0];
            if (land) {
                this.y = land.y;
                this.vy = 0;
                this._setState('sit');
            } else {
                this.y = ny;
                const floor = surfaces[0];
                if (this.y > floor.y) {
                    this.y = floor.y;
                    this._setState('sit');
                }
            }
            this._setSprite(this.facing < 0 ? 'walkL' : 'walkR', 1);
            break;
        }
        case 'walk': {
            const speed = WALK_SPEED * this._scale() / 2;
            this.x += this.facing * speed * dt;
            if (ground && (this.x < ground.x1 + 4 || this.x > ground.x2 - 4)) {
                if (ground.win && Math.random() < 0.45) {
                    this.x += this.facing * 8;   // step off the edge
                    this._setState('fall');
                } else {
                    this.facing = -this.facing;
                    this.x = Math.max(ground.x1 + 5, Math.min(ground.x2 - 5, this.x));
                }
            }
            this._animate(this.facing < 0 ? 'walkL' : 'walkR');
            if (this.stateTime > this.nextDecision)
                this._decide(surfaces);
            break;
        }
        case 'sit':
            this._setSprite(this.facing < 0 ? 'walkL' : 'walkR', 0);
            if (this.stateTime > this.nextDecision)
                this._decide(surfaces);
            break;
        case 'look':
            this._animate('talk');
            if (this.stateTime > 2.5)
                this._setState('sit');
            break;
        case 'sleep':
            this._animate('sleep', 900);
            break;
        case 'wake':
            this._animate('wake', 400);
            if (this.stateTime > 1.0)
                this._setState('sit');
            break;
        case 'emerge':
            this._playOnce('emerge', [0, 1, 2, 3, 4, 5, 6, 7], 120, () => this._setState('sit'));
            break;
        case 'dig':
            this._playOnce('emerge', [8, 9, 10], 140, () => {
                const target = this._digTarget;
                this.x = target.x;
                this.y = target.y;
                this._setState('emerge');
            });
            break;
        case 'chew':
            if (this.stateTime < 1.6)
                this._animate('scoot', 300);
            else
                this._animate('eat', 180);
            if (this.stateTime > 4.5)
                this._setState('sit');
            break;
        }

        if (this._settings.get_boolean('chatty') && now > this._chatterAt && this.state === 'sit') {
            this._chatterAt = now + 240 + Math.random() * 600;
            this.say(pick(LINES.chatter));
        }
        this._place();
    }

    _animate(key, ms = FRAME_MS) {
        if (this._frameTime >= ms) {
            this._frameTime = 0;
            this.frame++;
        }
        this._setSprite(key, this.frame);
    }

    _playOnce(key, frames, ms, done) {
        const i = Math.floor(this.stateTime * 1000 / ms);
        if (i >= frames.length) {
            done();
            return;
        }
        this._setSprite(key, frames[i]);
    }

    _setState(s) {
        this.state = s;
        this.stateTime = 0;
        this.frame = 0;
        this.nextDecision = 2 + Math.random() * 6;
    }

    _decide(surfaces) {
        const r = Math.random();
        if (r < 0.45) {
            this.facing = Math.random() < 0.5 ? -1 : 1;
            this._setState('walk');
        } else if (r < 0.65) {
            this._setState('sit');
        } else if (r < 0.75) {
            this._setState('look');
        } else if (r < 0.9 && surfaces.length > 1) {
            this.digTo(this._pickSpot(surfaces));
        } else {
            this._setState('sit');
            this.nextDecision = 8 + Math.random() * 10;
        }
    }

    // A spot away from the pointer, preferring window tops that aren't the focused window.
    _pickSpot(surfaces) {
        const [px] = global.get_pointer();
        const focus = global.display.focus_window;
        const options = surfaces.filter(s => s.win !== focus && s.x2 - s.x1 > 80);
        const s = pick(options.length ? options : surfaces);
        let x = s.x1 + 30 + Math.random() * Math.max(1, s.x2 - s.x1 - 60);
        if (Math.abs(x - px) < 150)
            x = px < (s.x1 + s.x2) / 2 ? Math.min(s.x2 - 30, px + 200) : Math.max(s.x1 + 30, px - 200);
        return {x, y: s.y};
    }

    digTo(spot) {
        if (this.state === 'dig' || this.state === 'emerge')
            return;
        this._digTarget = spot;
        this._setState('dig');
    }

    // ---- staying out of the way --------------------------------------------------------------

    _trackPointer(dt) {
        const [px, py, mods] = global.get_pointer();
        const [lx, ly] = this._lastPointer;
        this._lastPointer = [px, py];
        const moving = Math.hypot(px - lx, py - ly) > 1;
        if (moving)
            this._lastActive = GLib.get_monotonic_time();
        const info = this._spriteInfo || {w: 50, h: 40};
        const near = Math.abs(px - this.x) < info.w / 2 + NEAR_PX && py > this.y - info.h - NEAR_PX && py < this.y + 30;
        // Dragging something (a window, a file) through the dog: it gets out of the way at once.
        const dragging = (mods & Clutter.ModifierType.BUTTON1_MASK) !== 0;
        if (near && dragging && !['dig', 'emerge', 'fall'].includes(this.state)) {
            this.digTo(this._pickSpot(this._surfaces()));
            return;
        }
        if (near && moving && ['walk', 'sit'].includes(this.state))
            this._setState('look');   // it notices you, and waits to be petted
        if (this.state === 'sleep' && moving && near)
            this.wake();
    }

    _trackIdle() {
        const idleMs = global.backend.get_core_idle_monitor().get_idletime();
        const sleepAfter = this._settings.get_int('idle-sleep-minutes') * 60000;
        if (idleMs > sleepAfter && ['sit', 'walk', 'look'].includes(this.state)) {
            this._setState('sleep');
            if (this._settings.get_boolean('chatty'))
                this.say(pick(LINES.sleep));
        } else if (this.state === 'sleep' && idleMs < 1500) {
            this.wake();
        }
    }

    wake() {
        if (this.state !== 'sleep')
            return;
        this._setState('wake');
    }

    sleep() {
        this._setState('sleep');
    }

    // ---- reactions ---------------------------------------------------------------------------

    pet() {
        if (this.state === 'sleep') {
            this.wake();
            this.say(pick(LINES.wake));
            return;
        }
        this._setState('look');
        this.say(pick(LINES.pet));
        this._playSound('mus_dogappear');
    }

    notified() {
        if (this.state === 'sleep' || !this._settings.get_boolean('chatty'))
            return;
        this._setState('look');
        this.say(pick(LINES.notify));
    }

    windowClosed(rect) {
        const now = this._now();
        if (now < this._absorbReadyAt || this.state === 'sleep' || Math.random() > 0.35)
            return;
        this._absorbReadyAt = now + 600;
        const surfaces = this._surfaces();
        const cx = rect.x + rect.width / 2;
        const below = surfaces.filter(s => s.y >= rect.y + rect.height - 5 && cx >= s.x1 && cx <= s.x2)
            .sort((a, b) => a.y - b.y)[0] || surfaces[0];
        this._digTarget = {x: cx, y: below.y};
        this._afterEmerge = 'chew';
        this._setState('dig');
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1700, () => {
            if (this.state === 'sit' || this.state === 'emerge') {
                this._setState('chew');
                if (this._settings.get_boolean('chatty'))
                    this.say(pick(LINES.absorb));
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    // ---- talking -----------------------------------------------------------------------------

    say(text) {
        if (this._typeTimer)
            GLib.source_remove(this._typeTimer);
        let n = 0;
        this._bubble.text = '';
        this._bubbleShown = true;
        this._bubble.opacity = 255;
        this._placeBubble();
        this._typeTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 35, () => {
            n++;
            this._bubble.text = text.slice(0, n);
            this._placeBubble();
            if (n < text.length)
                return GLib.SOURCE_CONTINUE;
            this._typeTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 3500, () => {
                this._bubble.opacity = 0;
                this._bubbleShown = false;
                this._typeTimer = 0;
                return GLib.SOURCE_REMOVE;
            });
            return GLib.SOURCE_REMOVE;
        });
    }

    _placeBubble() {
        const [bw, bh] = this._bubble.get_size();
        const info = this._spriteInfo || {h: 40};
        const mon = Main.layoutManager.primaryMonitor;
        let x = Math.round(this.x - bw / 2);
        let y = Math.round(this.y - info.h - bh - 10);
        x = Math.max(mon.x + 8, Math.min(mon.x + mon.width - bw - 8, x));
        if (y < Main.panel.height + 6)
            y = Math.round(this.y + 8);
        this._bubble.set_position(x, y);
    }
}
