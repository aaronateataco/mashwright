// The dog: a small actor in the Shell's chrome layer that walks along the tops of your windows and
// the bottom of the screen, naps when you're away, and keeps out of your way.

import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Meta from 'gi://Meta';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {TextBox} from './textbox.js';

const TICK_MS = 50;
const FRAME_MS = 260;
const GRAVITY = 1800;      // px/s²
const WALK_SPEED = 46;     // px/s at scale 2
const NEAR_PX = 90;

export const SPRITES = {
    walkL: 'spr_tobdogl', walkR: 'spr_tobdogr', sleep: 'spr_sleepdog', wake: 'spr_wakedog',
    talk: 'spr_tobdogl_talk', emerge: 'spr_emergentdog', scoot: 'spr_tobydogscoot_small',
    eat: 'spr_tobydogeat_small', pile: 'spr_tobdog_pile', treat: 'spr_dogtreat',
};

export const SOUNDS = {bark: 'snd_pombark', blip: 'SND_TXT2', squeak: 'snd_squeak', item: 'snd_item'};

export const LINES = {
    pet: ['* (You pet the dog.)', '* (The dog wags its tail.)', '* (Bark!)', '* (The dog seems very pleased.)'],
    chatter: ['* (The dog is guarding your windows.)', '* (The dog found a comfy title bar.)',
        "* (It's a small, white dog.)", '* (The dog sniffs your desktop.)', '* (The dog is doing its best.)'],
    notify: ['* (A message! The dog pretends to read it.)', '* (The dog barks at the notification.)'],
    absorb: ['* (The dog absorbed the window.)', '* (The dog chews on what is left of the window.)'],
    treat: ['* (The dog ate the treat.)', '* (The dog enjoyed the treat very much.)', '* (Crunch.)'],
    sleep: ['* (The dog fell asleep.)'],
    wake: ['* (The dog wakes up.)'],
};

function pick(list) {
    return list[Math.floor(Math.random() * list.length)];
}

export class Dog {
    constructor({index, dir, settings, playSound, font, startAt}) {
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
        this._box = new TextBox(font, dir);
        this._bubble = this._box.actor;
        this._bubbleShown = false;
        Main.layoutManager.addChrome(this._bubble, {trackFullscreen: true});

        const wa = Main.layoutManager.getWorkAreaForMonitor(Main.layoutManager.primaryIndex);
        this.x = wa.x + wa.width * (0.2 + Math.random() * 0.6);
        this.y = wa.y + wa.height;
        // Back where it was last time, if that spot is still on a screen.
        if (startAt && Main.layoutManager.monitors.some(m =>
            startAt[0] >= m.x && startAt[0] < m.x + m.width && startAt[1] > m.y && startAt[1] <= m.y + m.height)) {
            this.x = startAt[0];
            this.y = startAt[1];
        }
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
        this._pointerMovedAt = this._now();
        this._tickCount = 0;
        // Out of the way in the Activities overview.
        Main.overview.connectObject('showing', () => this._setHidden(true), 'hidden', () => this._setHidden(false), this);
        // A new workspace: the dog digs over to it (popping up somewhere sensible there).
        global.workspace_manager.connectObject('active-workspace-changed', () => {
            this._surfCache = null;
            if (this.state !== 'sleep')
                GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
                    this._surfCache = null;
                    this.digTo(this._pickSpot(this._surfaces()));
                    return GLib.SOURCE_REMOVE;
                });
        }, this);
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, TICK_MS, () => {
            try {
                this._tick(TICK_MS / 1000);
            } catch (e) {
                logError(e, 'DogDesk tick');
            }
            return GLib.SOURCE_CONTINUE;
        });
    }

    _setHidden(hidden) {
        this.actor.opacity = hidden ? 0 : 255;
        this.actor.reactive = !hidden;
        if (hidden)
            this._bubble.opacity = 0;
        else if (this._bubbleShown)
            this._bubble.opacity = 255;
    }

    destroy() {
        Main.overview.disconnectObject(this);
        global.workspace_manager.disconnectObject(this);
        if (this._timer)
            GLib.source_remove(this._timer);
        if (this._typeTimer)
            GLib.source_remove(this._typeTimer);
        this._timer = this._typeTimer = 0;
        this.actor.destroy();
        this._box.destroy();
        this._treat?.destroy();
        this._treat = null;
    }

    _now() {
        return GLib.get_monotonic_time() / 1e6;
    }

    _scale() {
        return this._settings.get_int('scale');
    }

    // The monitor the dog is on (it can live on any of them).
    _monitor() {
        const monitors = Main.layoutManager.monitors;
        const i = monitors.findIndex(m => this.x >= m.x && this.x < m.x + m.width && this.y > m.y && this.y <= m.y + m.height + 2);
        return i >= 0 ? i : Main.layoutManager.primaryIndex;
    }

    _workArea() {
        return Main.layoutManager.getWorkAreaForMonitor(this._monitor());
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
        const now = GLib.get_monotonic_time();
        if (this._surfCache && now - this._surfCache.at < 200000)
            return this._surfCache.list;
        const list = this._computeSurfaces();
        this._surfCache = {at: now, list};
        return list;
    }

    _floorFor(surfaces, x) {
        const floors = surfaces.filter(s => s.floor);
        return floors.find(s => x >= s.x1 && x < s.x2) || floors[0];
    }

    _computeSurfaces() {
        const out = Main.layoutManager.monitors.map((_m, i) => {
            const a = Main.layoutManager.getWorkAreaForMonitor(i);
            return {x1: a.x, x2: a.x + a.width, y: a.y + a.height, win: null, floor: true};
        });
        const ws = global.workspace_manager.get_active_workspace();
        const wins = global.display.sort_windows_by_stacking(
            global.get_window_actors().map(a => a.meta_window).filter(w =>
                w && !w.minimized && w.get_window_type() === Meta.WindowType.NORMAL &&
                w.located_on_workspace(ws) && !w.is_fullscreen() && w.showing_on_its_workspace()));
        const rects = wins.map(w => w.get_frame_rect());
        wins.forEach((w, i) => {
            const r = rects[i];
            const wa = Main.layoutManager.getWorkAreaForMonitor(w.get_monitor());
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
        // Asleep it barely moves: think five times less often.
        this._tickCount++;
        if (this.state === 'sleep' && this._tickCount % 5)
            return;
        if (this.state === 'sleep')
            dt *= 5;
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
                const floor = this._floorFor(surfaces, this.x);
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
        case 'sleep': {
            // In winter a long nap turns the dog into a little snow pile, as in Snowdin.
            const month = new Date().getMonth();
            if ((month === 11 || month <= 1) && this.stateTime > 20)
                this._setSprite('pile', 0);
            else
                this._animate('sleep', 900);
            break;
        }
        case 'wake':
            this._animate('wake', 400);
            if (this.stateTime > 1.0)
                this._setState('sit');
            break;
        case 'emerge':
            this._playOnce('emerge', [0, 1, 2, 3, 4, 5, 6, 7], 120,
                () => this._setState(this._treat && this._treat.landed ? 'fetch' : 'sit'));
            break;
        case 'dig':
            this._playOnce('emerge', [8, 9, 10], 140, () => {
                const target = this._digTarget;
                this.x = target.x;
                this.y = target.y;
                this._setState('emerge');
            });
            break;
        case 'fetch': {
            // Off to the treat.
            const tr = this._treat;
            if (!tr || !tr.landed) {
                this._animate('talk');
                break;
            }
            if (Math.abs(this.y - tr.y) > 3) {
                if (this.state === 'fetch' && this.stateTime > 0.3)
                    this.digTo({x: tr.x - this.facing * 20, y: tr.y});
                break;
            }
            const dx = tr.x - this.x;
            if (Math.abs(dx) < 14) {
                this._treat.actor.destroy();
                this._treat = null;
                this._setState('chew');
                this.stateTime = 1.6;   // straight to eating
                this._playSound(SOUNDS.squeak);
                if (this._settings.get_boolean('chatty'))
                    this.say(pick(LINES.treat));
                break;
            }
            this.facing = dx < 0 ? -1 : 1;
            this.x += this.facing * WALK_SPEED * 1.8 * this._scale() / 2 * dt;
            this._animate(this.facing < 0 ? 'walkL' : 'walkR', 150);
            break;
        }
        case 'chew':
            if (this.stateTime < 1.6)
                this._animate('scoot', 300);
            else
                this._animate('eat', 180);
            if (this.stateTime > 4.5)
                this._setState('sit');
            break;
        }

        if (this._settings.get_boolean('chatty') && now > this._chatterAt && this.state === 'sit' && !this._userFocused()) {
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

    // Typing or watching something: the keyboard is busy but the pointer is still.
    _userFocused() {
        const idleMs = global.backend.get_core_idle_monitor().get_idletime();
        return idleMs < 3000 && this._now() - this._pointerMovedAt > 4;
    }

    _decide(surfaces) {
        if (this._userFocused()) {
            this._setState('sit');
            this.nextDecision = 10 + Math.random() * 10;
            return;
        }
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
        if (moving) {
            this._lastActive = GLib.get_monotonic_time();
            this._pointerMovedAt = this._now();
        }
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
        const hour = new Date().getHours();
        const night = hour >= 23 || hour < 6;
        const sleepAfter = this._settings.get_int('idle-sleep-minutes') * 60000 / (night ? 3 : 1);
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
        this._playSound(SOUNDS.bark);
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
            .sort((a, b) => a.y - b.y)[0] || this._floorFor(surfaces, cx);
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

    // A treat falls from the top bar (above the pointer, or above the dog) and the dog goes for it.
    giveTreat() {
        const info = this._index[SPRITES.treat];
        if (!info || this._treat)
            return;
        // Tossed a little way ahead of the dog, so it trots over for it.
        const mon = Main.layoutManager.monitors[this._monitor()];
        let x = this.x + this.facing * (120 + Math.random() * 120);
        if (x < mon.x + 40 || x > mon.x + mon.width - 40)
            x = this.x - this.facing * (120 + Math.random() * 120);
        x = Math.max(mon.x + 40, Math.min(mon.x + mon.width - 40, x));
        const actor = new St.Widget({width: info.w, height: info.h, reactive: false});
        const file = GLib.build_filenamev([this._dir, `${SPRITES.treat}_0.png`]);
        actor.set_style(`background-image: url("file://${file}"); background-size: ${info.w}px ${info.h}px;`);
        Main.layoutManager.addChrome(actor, {trackFullscreen: true});
        const treat = {actor, x, y: mon.y + Main.panel.height + info.h, vy: 0, landed: false, info};
        actor.set_position(Math.round(treat.x - info.w / 2), Math.round(treat.y - info.h));
        this._treat = treat;
        const step = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 16, () => {
            if (this._treat !== treat)
                return GLib.SOURCE_REMOVE;
            const surfaces = this._surfaces();
            treat.vy += GRAVITY * 0.016;
            const ny = treat.y + treat.vy * 0.016;
            const land = surfaces.filter(s => s.y >= treat.y - 1 && s.y <= ny && treat.x >= s.x1 && treat.x <= s.x2)
                .sort((a, b) => a.y - b.y)[0];
            treat.y = land ? land.y : ny;
            actor.set_position(Math.round(treat.x - info.w / 2), Math.round(treat.y - info.h));
            if (land) {
                treat.landed = true;
                return GLib.SOURCE_REMOVE;
            }
            return GLib.SOURCE_CONTINUE;
        });
        if (this.state === 'sleep')
            this._setState('wake');
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            if (this._treat === treat)
                this._setState('fetch');
            return GLib.SOURCE_REMOVE;
        });
        // A treat nobody eats (the dog can't reach it) disappears after a while.
        GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 30, () => {
            if (this._treat === treat) {
                treat.actor.destroy();
                this._treat = null;
                if (this.state === 'fetch')
                    this._setState('sit');
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    position() {
        return [Math.round(this.x), Math.round(this.y)];
    }

    // ---- talking -----------------------------------------------------------------------------

    say(text) {
        if (this._typeTimer)
            GLib.source_remove(this._typeTimer);
        let n = 0;
        this._box.setText(text);
        this._box.reveal(0);
        this._bubbleShown = true;
        this._bubble.opacity = 0;
        // Show it once it has its size and its place (next frame), never in a corner first.
        GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._placeBubble();
            if (this._bubbleShown && this.actor.opacity)
                this._bubble.opacity = 255;
            return GLib.SOURCE_REMOVE;
        });
        this._typeTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 40, () => {
            n++;
            this._box.reveal(n);
            if (n % 3 === 1 && text[n - 1] !== ' ')
                this._playSound(SOUNDS.blip);
            this._placeBubble();
            if (n < this._box.length)
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
        const [, , bw, bh] = this._bubble.get_preferred_size();
        const info = this._spriteInfo || {h: 40};
        const mon = Main.layoutManager.monitors[this._monitor()];
        let x = Math.round(this.x - bw / 2);
        let y = Math.round(this.y - info.h - bh - 10);
        x = Math.max(mon.x + 8, Math.min(mon.x + mon.width - bw - 8, x));
        if (y < mon.y + Main.panel.height + 6)
            y = Math.round(this.y + 8);
        this._bubble.set_position(x, y);
    }
}
