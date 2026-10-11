"use strict";
// Mashwright UI: talks to the local server's JSON API with the session token.
const TOKEN = document.querySelector('meta[name="mashwright-token"]').content;
let state = { games: [], mashups: [] };

async function api(path, body, raw) {
  const opts = { method: body === undefined ? "GET" : "POST", headers: { "X-Mashwright-Token": TOKEN } };
  if (raw) { opts.body = raw; opts.headers["Content-Type"] = "application/octet-stream"; }
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

const $ = (s, root = document) => root.querySelector(s);
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
}
function toast(msg, bad) {
  const t = $("#toast"); t.textContent = msg; t.className = bad ? "bad" : ""; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 4500);
}

// ---- look: GNOME's Adwaita on Linux; inside the native GNOME window the header bar is native ----
const params = new URLSearchParams(location.search);
const root = document.documentElement;
root.dataset.theme = document.querySelector('meta[name="mashwright-theme"]').content;
if (params.get("shell") === "gnome") root.dataset.shell = "gnome";
// Called by the GNOME window with the desktop's dark setting and accent colour.
window.mashwrightTheme = ({ dark, accent }) => {
  root.dataset.scheme = dark ? "dark" : "light";
  if (accent) root.style.setProperty("--accent-bg", accent);
};
function tellShell(msg) {
  try { window.webkit.messageHandlers.mashwright.postMessage(msg); } catch (e) { /* not in the GNOME window */ }
}

// ---- tabs ----
function selectTab(name) {
  document.querySelectorAll('nav [role="tab"]').forEach(t => t.setAttribute("aria-selected", t.dataset.tab === name));
  document.querySelectorAll('[role="tabpanel"]').forEach(p => (p.hidden = p.id !== "panel-" + name));
  if (name === "log") loadLog();
}
window.mashwrightSelectTab = selectTab;
window.mashwrightRescan = () => refresh(true);
document.querySelectorAll('nav [role="tab"]').forEach(tab => tab.addEventListener("click", () => {
  selectTab(tab.dataset.tab);
  tellShell({ tab: tab.dataset.tab });
}));
const goTab = name => { selectTab(name); tellShell({ tab: name }); };

// ---- data ----
async function refresh(rescan) {
  try {
    state = rescan ? await api("/api/rescan", {}) : await api("/api/state");
    $("#version").textContent = state.version;
    renderMashups(); renderGames(); renderDiscover();
  } catch (e) { toast(e.message, true); }
}

function runnerBadge(g) {
  const r = g.runner.startsWith("emulator") ? "emulator" : g.runner;
  const label = { native: "Native", proton: "Proton", wine: "Wine", emulator: "Emulator", device: "Device" }[r] || r;
  return el("span", { class: "badge " + r }, label);
}

function renderMashups() {
  const box = $("#mashups"); box.replaceChildren();
  $("#no-mashups").hidden = state.mashups.length > 0;
  for (const m of state.mashups) {
    const r = m.recipe, installed = m.status.installed;
    const choices = {};
    const needs = el("ul", { class: "needs" });
    for (const g of r.games) {
      const found = m.candidates[g.slug] || [];
      let item;
      if (found.length > 1) {
        const sel = el("select", { "aria-label": "Which copy of " + g.slug, onchange: e => (choices[g.slug] = e.target.value) },
          found.map(f => el("option", { value: f.key }, `${f.title} (${f.store}${f.runner !== "native" ? ", " + f.runner : ""})`)));
        choices[g.slug] = found[0].key;
        item = [el("span", { class: "dot ok" }), sel];
      } else if (found.length === 1) {
        item = [el("span", { class: "dot ok" }), `${found[0].title}`, runnerBadge(found[0])];
      } else {
        const where = g.emulator ? ` (needs a ${PLATFORM_NAMES[g.emulator.system] || g.emulator.system} emulator)` : "";
        item = [el("span", { class: "dot " + (g.optional ? "opt" : "no") }), `${g.title || g.slug} — not found${where}${g.optional ? " (optional)" : ""}`];
      }
      needs.append(el("li", {}, item));
    }
    const bar = el("div", { class: "progress", hidden: true }, el("div"));
    const run = async (label, path, body) => {
      try {
        const { job } = await api(path, body);
        bar.hidden = false;
        await watchJob(job, bar.firstChild, label);
      } catch (e) { toast(e.message, true); }
      bar.hidden = true; // ---- Discover ----
const art = (key, kind) => `/art/game/${encodeURIComponent(key)}/${kind}?t=${encodeURIComponent(TOKEN)}`;
const cover = id => `/art/mashup/${encodeURIComponent(id)}?t=${encodeURIComponent(TOKEN)}`;
let heroIndex = 0, heroTimer = null;

function gameTile(g, slug, cls) {
  // A game's icon from its store artwork, or its initials on a tile.
  const kind = g && g.extra && g.extra.art && (g.extra.art.icon ? "icon" : g.extra.art.capsule ? "capsule" : null);
  if (kind) return el("img", { class: cls, src: art(g.key, kind), alt: g.title, title: g.title });
  const name = (g && g.title) || slug;
  return el("span", { class: cls + " initials", title: name }, name.split(/\W+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join(""));
}

function mashupArt(m) {
  if (m.recipe.cover) return cover(m.recipe.id);
  const primary = m.recipe.games.find(g => g.role === "primary") || m.recipe.games[0];
  const g = (m.candidates[primary.slug] || [])[0];
  return g && g.extra.art && g.extra.art.hero ? art(g.key, "hero") : null;
}

async function mainAction(m) {
  const r = m.recipe;
  try {
    if (m.desktop && m.status.installed) {
      await api("/api/desktop", { id: r.id, on: !m.desktop.enabled });
      toast(m.desktop.enabled ? `${r.title} is off` : `${r.title} is on`); refresh(); return;
    }
    if (m.status.installed) { toast((await api("/api/launch", { id: r.id })).message); return; }
    if (!m.ready) { toast("Missing: " + m.missing.join(", "), true); return; }
    const { job } = await api("/api/install", { id: r.id, choices: {} });
    toast(`Installing ${r.title}…`);
    const fake = document.createElement("div");
    await watchJob(job, fake, `${r.title} is ready to play`);
    // ---- Online catalog (a JSON index in a GitHub repo, packages in GitHub Releases) ----
let catalog = null;
async function loadCatalog(force) {
  try { catalog = (await api("/api/catalog" + (force ? "?refresh=1" : ""))).mashups; }
  catch (e) { catalog = []; }
  renderCatalog();
}
function renderCatalog() {
  const shelf = $("#shelf-catalog"); if (!shelf) return;
  shelf.replaceChildren();
  if (catalog === null) { shelf.append(el("p", { class: "muted" }, "Loading the catalog…")); return; }
  if (!catalog.length) { shelf.append(el("p", { class: "muted" }, "No online catalog yet.")); return; }
  for (const e of catalog) {
    const label = e.update ? "Update" : e.in_library ? "In library" : "Get";
    const card = el("div", { class: "tile catalog-tile" },
      e.cover_url ? el("img", { src: `/art/catalog/${encodeURIComponent(e.id)}?t=${encodeURIComponent(TOKEN)}`, alt: "" }) : el("div", { class: "tile-fallback" }),
      el("span", { class: "chip" }, "v" + (e.version || "?")),
      el("div", { class: "tile-title" }, el("span", {}, e.title),
        el("span", { class: "tile-sub" }, (e.games || []).map(g => g.title || g.slug).join(" + ")),
        el("span", { class: "tile-actions" },
          el("button", { class: "pill", disabled: e.in_library && !e.update, onclick: async ev => {
            ev.stopPropagation();
            try { const { job } = await api("/api/catalog/get", { id: e.id }); toast(`Getting ${e.title}…`);
                  await watchJob(job, document.createElement("div"), `${e.title} is ready`); await refresh(); loadCatalog(); }
            catch (err) { toast(err.message, true); } } }, label),
          e.links && e.links.melty ? el("a", { class: "linkout", href: e.links.melty, target: "_blank", rel: "noopener" }, "On Melty") : null)));
    shelf.append(card);
  }
}

// ---- Melty through Wine (Linux) ----
async function loadMelty() {
  let st;
  try { st = await api("/api/melty"); } catch (e) { return; }
  const card = $("#melty-card");
  card.hidden = !st.supported;
  const btn = $("#melty-btn");
  btn.textContent = st.installed ? "Open Melty" : "Set up Melty";
  btn.onclick = async () => {
    try {
      if (st.installed) { toast((await api("/api/melty/open", {})).message); return; }
      const bar = card.querySelector(".progress"); bar.hidden = false;
      const { job } = await api("/api/melty/setup", {});
      await watchJob(job, bar.firstChild, "Melty is ready");
      bar.hidden = true; loadMelty();
    } catch (e) { toast(e.message, true); }
  };
}

refresh();
loadCatalog();
loadMelty();
  } catch (e) { toast(e.message, true); }
}

function renderDiscover() {
  const hero = $("#hero"); hero.replaceChildren();
  const list = state.mashups;
  if (!list.length) {
    hero.append(el("div", { class: "hero-empty" }, el("h2", {}, "Make two games one"),
      el("p", {}, "Add a .mashwright or Melty-format package to get started."),
      el("button", { onclick: () => goTab("add") }, "Add a mashup")));
  } else {
    heroIndex = heroIndex % list.length;
    list.forEach((m, i) => {
      const r = m.recipe, img = mashupArt(m);
      const tiles = [];
      r.games.forEach((g, gi) => {
        if (gi) tiles.push(el("span", { class: "plus", "aria-hidden": "true" }, "+"));
        tiles.push(gameTile((m.candidates[g.slug] || [])[0], g.title || g.slug, "hero-icon"));
      });
      hero.append(el("article", { class: "slide" + (i === heroIndex ? " active" : ""), "aria-hidden": i !== heroIndex,
                                  "aria-label": `${i + 1} of ${list.length}: ${r.title}` },
        img ? el("img", { class: "slide-bg", src: img, alt: "" }) : el("div", { class: "slide-bg fallback" }),
        el("div", { class: "slide-shade" }),
        el("div", { class: "slide-body" },
          el("div", { class: "hero-icons" }, tiles),
          el("h2", {}, r.title),
          el("p", { class: "by" }, (r.authors || []).join(", ") || "\u00a0"),
          el("button", { class: "pill big", onclick: () => mainAction(m) },
            m.desktop && m.status.installed ? (m.desktop.enabled ? "On your desktop ✓" : "Turn on")
              : m.status.installed ? "▶  Play" : m.ready ? "Install" : "Missing games"))));
    });
    if (list.length > 1) {
      const go = d => { heroIndex = (heroIndex + d + list.length) % list.length; renderDiscover(); };
      hero.append(el("button", { class: "hero-nav prev", "aria-label": "Previous", onclick: () => go(-1) }, "‹"),
                  el("button", { class: "hero-nav next", "aria-label": "Next", onclick: () => go(1) }, "›"),
                  el("div", { class: "dots" }, list.map((_, i) => el("button", { class: i === heroIndex ? "on" : "",
                    "aria-label": `Show ${i + 1}`, onclick: () => { heroIndex = i; renderDiscover(); } }))));
      clearTimeout(heroTimer);
      heroTimer = setTimeout(() => { if (!$("#panel-discover").hidden) go(1); }, 8000);
    }
  }
  const shelf = $("#shelf-mashups"); shelf.replaceChildren();
  for (const m of list) {
    const img = mashupArt(m);
    shelf.append(el("button", { class: "tile", onclick: () => goTab("mashups"), "aria-label": m.recipe.title },
      img ? el("img", { src: img, alt: "" }) : el("div", { class: "tile-fallback" }),
      el("span", { class: "chip" }, m.desktop ? (m.desktop.enabled ? "On your desktop" : "Desktop · off")
        : m.status.installed ? "Installed" : "v" + m.recipe.version),
      el("span", { class: "tile-title" }, m.recipe.title)));
  }
  if (!list.length) shelf.append(el("p", { class: "muted" }, "Nothing here yet."));
  renderCatalog();
  const games = $("#shelf-games"); games.replaceChildren();
  for (const g of state.games.filter(g => g.install_dir)) {
    const a = g.extra.art || {};
    games.append(el("div", { class: "capsule", title: g.title },
      a.capsule ? el("img", { src: art(g.key, "capsule"), alt: g.title }) : el("div", { class: "capsule-fallback" }, g.title),
      el("span", { class: "capsule-badge" }, PLATFORM_NAMES[g.platform] || g.platform)));
  }
  if (!games.children.length) games.append(el("p", { class: "muted" }, "No games found yet — try Rescan."));
}

// ---- Online catalog (a JSON index in a GitHub repo, packages in GitHub Releases) ----
let catalog = null;
async function loadCatalog(force) {
  try { catalog = (await api("/api/catalog" + (force ? "?refresh=1" : ""))).mashups; }
  catch (e) { catalog = []; }
  renderCatalog();
}
function renderCatalog() {
  const shelf = $("#shelf-catalog"); if (!shelf) return;
  shelf.replaceChildren();
  if (catalog === null) { shelf.append(el("p", { class: "muted" }, "Loading the catalog…")); return; }
  if (!catalog.length) { shelf.append(el("p", { class: "muted" }, "No online catalog yet.")); return; }
  for (const e of catalog) {
    const label = e.update ? "Update" : e.in_library ? "In library" : "Get";
    const card = el("div", { class: "tile catalog-tile" },
      e.cover_url ? el("img", { src: `/art/catalog/${encodeURIComponent(e.id)}?t=${encodeURIComponent(TOKEN)}`, alt: "" }) : el("div", { class: "tile-fallback" }),
      el("span", { class: "chip" }, "v" + (e.version || "?")),
      el("div", { class: "tile-title" }, el("span", {}, e.title),
        el("span", { class: "tile-sub" }, (e.games || []).map(g => g.title || g.slug).join(" + ")),
        el("span", { class: "tile-actions" },
          el("button", { class: "pill", disabled: e.in_library && !e.update, onclick: async ev => {
            ev.stopPropagation();
            try { const { job } = await api("/api/catalog/get", { id: e.id }); toast(`Getting ${e.title}…`);
                  await watchJob(job, document.createElement("div"), `${e.title} is ready`); await refresh(); loadCatalog(); }
            catch (err) { toast(err.message, true); } } }, label),
          e.links && e.links.melty ? el("a", { class: "linkout", href: e.links.melty, target: "_blank", rel: "noopener" }, "On Melty") : null)));
    shelf.append(card);
  }
}

// ---- Melty through Wine (Linux) ----
async function loadMelty() {
  let st;
  try { st = await api("/api/melty"); } catch (e) { return; }
  const card = $("#melty-card");
  card.hidden = !st.supported;
  const btn = $("#melty-btn");
  btn.textContent = st.installed ? "Open Melty" : "Set up Melty";
  btn.onclick = async () => {
    try {
      if (st.installed) { toast((await api("/api/melty/open", {})).message); return; }
      const bar = card.querySelector(".progress"); bar.hidden = false;
      const { job } = await api("/api/melty/setup", {});
      await watchJob(job, bar.firstChild, "Melty is ready");
      bar.hidden = true; loadMelty();
    } catch (e) { toast(e.message, true); }
  };
}

refresh();
loadCatalog();
loadMelty();
    };
    const actions = el("div", { class: "actions" },
      installed && m.desktop
        ? [el("button", { onclick: async () => { try { await api("/api/desktop", { id: r.id, on: !m.desktop.enabled });
                toast(m.desktop.enabled ? `${r.title} is off` : `${r.title} is on (new installs need a log out and in)`); refresh(); }
              catch (e) { toast(e.message, true); } } }, m.desktop.enabled ? "Turn off" : "Turn on"),
           el("button", { class: "ghost", onclick: async () => { try { toast((await api("/api/desktop/prefs", { id: r.id })).message); } catch (e) { toast(e.message, true); } } }, "Preferences"),
           el("button", { class: "ghost", onclick: () => run("Uninstalled", "/api/uninstall", { id: r.id }) }, "Uninstall")]
      : installed
        ? [el("button", { onclick: async () => { try { toast((await api("/api/launch", { id: r.id })).message); } catch (e) { toast(e.message, true); } } }, "Play"),
           el("button", { class: "ghost", onclick: () => run("Uninstalled", "/api/uninstall", { id: r.id }) }, "Uninstall")]
        : [el("button", { disabled: !m.ready, onclick: () => run("Installed", "/api/install", { id: r.id, choices }) }, "Install"),
           el("button", { class: "danger", onclick: async () => { if (!confirm(`Remove ${r.title} from your library?`)) return;
             try { await api("/api/remove", { id: r.id }); refresh(); } catch (e) { toast(e.message, true); } } }, "Remove")]);
    box.append(el("article", { class: "card" },
      el("h2", {}, r.title, " ", el("span", { class: "ver" }, "v" + r.version), installed ? [" ", el("span", { class: "badge installed" }, "Installed")] : null,
        r.source === "melty-format package" ? [" ", el("span", { class: "badge", title: "Opened from a Melty-format recipe.json package" }, "Melty format")] : null),
      r.description ? el("p", { class: "desc" }, r.description.replace(/[#*_`>]/g, "").slice(0, 400)) : null,
      needs,
      m.warnings.map(w => el("p", { class: "warn" }, w)),
      fitView(m.fit),
      installed && m.status.changed.length ? el("p", { class: "warn" }, `${m.status.changed.length} file(s) changed since install`) : null,
      actions, bar));
  }
}

// How the mashup's binaries fit the chosen game (native Linux, Proton, Windows, hybrid packages).
function fitView(fit) {
  if (!fit || (!fit.notes.length && !fit.advice.length)) return null;
  const label = { adjusted: `Adjusted for ${PLATFORM_NAMES[fit.target] || fit.target}`, warning: "Check before playing",
                  ok: "Fits", blocked: "Won't work here" }[fit.status] || fit.status;
  return el("details", { class: "fit " + fit.status },
    el("summary", {}, el("span", { class: "badge fit-" + fit.status }, label)),
    el("ul", {}, fit.notes.map(n => el("li", {}, n)), fit.advice.map(a => el("li", { class: "advice" }, a))));
}

async function watchJob(id, barFill, doneLabel) {
  for (;;) {
    const j = await api("/api/jobs/" + id);
    barFill.style.width = Math.round((j.progress || 0) * 100) + "%";
    if (j.state === "done") { toast(doneLabel); return; }
    if (j.state === "failed") throw new Error(j.message);
    await new Promise(r => setTimeout(r, 300));
  }
}

const PLATFORM_NAMES = { windows: "Windows", linux: "Linux", macos: "macOS", switch: "Switch", android: "Android", ios: "iOS",
  gamecube: "GameCube", wii: "Wii", "3ds": "3DS", wiiu: "Wii U", psp: "PSP", ps1: "PS1", ps2: "PS2", ps3: "PS3" };
function renderGames() {
  const q = $("#game-search").value.toLowerCase();
  const groups = {};
  for (const g of state.games) {
    if (q && !(g.title.toLowerCase().includes(q) || g.key.includes(q))) continue;
    (groups[g.store] = groups[g.store] || []).push(g);
  }
  const names = { steam: "Steam", epic: "Epic Games", gog: "GOG", heroic: "Heroic", lutris: "Lutris", itch: "itch.io",
                  custom: "Added by you", switch: "Nintendo Switch (emulators / SD card)", emulator: "Emulators", android: "Android", ios: "iOS" };
  const box = $("#games"); box.replaceChildren();
  if (!Object.keys(groups).length) box.append(el("p", { class: "empty" }, "No games found."));
  for (const [store, list] of Object.entries(groups)) {
    box.append(el("div", { class: "group" }, el("h3", {}, names[store] || store),
      list.map(g => el("div", { class: "gamerow" }, el("span", { class: "t" }, g.title), runnerBadge(g),
        el("span", { class: "badge" }, PLATFORM_NAMES[g.platform] || g.platform), el("span", { class: "p" }, g.install_dir || g.store_id)))));
  }
}
$("#game-search").addEventListener("input", renderGames);
$("#rescan").addEventListener("click", () => refresh(true));

// ---- import ----
async function upload(file) {
  try {
    const { recipe } = await api("/api/import-upload", undefined, file);
    toast(`Added ${recipe.title}`); // ---- Discover ----
const art = (key, kind) => `/art/game/${encodeURIComponent(key)}/${kind}?t=${encodeURIComponent(TOKEN)}`;
const cover = id => `/art/mashup/${encodeURIComponent(id)}?t=${encodeURIComponent(TOKEN)}`;
let heroIndex = 0, heroTimer = null;

function gameTile(g, slug, cls) {
  // A game's icon from its store artwork, or its initials on a tile.
  const kind = g && g.extra && g.extra.art && (g.extra.art.icon ? "icon" : g.extra.art.capsule ? "capsule" : null);
  if (kind) return el("img", { class: cls, src: art(g.key, kind), alt: g.title, title: g.title });
  const name = (g && g.title) || slug;
  return el("span", { class: cls + " initials", title: name }, name.split(/\W+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join(""));
}

function mashupArt(m) {
  if (m.recipe.cover) return cover(m.recipe.id);
  const primary = m.recipe.games.find(g => g.role === "primary") || m.recipe.games[0];
  const g = (m.candidates[primary.slug] || [])[0];
  return g && g.extra.art && g.extra.art.hero ? art(g.key, "hero") : null;
}

async function mainAction(m) {
  const r = m.recipe;
  try {
    if (m.desktop && m.status.installed) {
      await api("/api/desktop", { id: r.id, on: !m.desktop.enabled });
      toast(m.desktop.enabled ? `${r.title} is off` : `${r.title} is on`); refresh(); return;
    }
    if (m.status.installed) { toast((await api("/api/launch", { id: r.id })).message); return; }
    if (!m.ready) { toast("Missing: " + m.missing.join(", "), true); return; }
    const { job } = await api("/api/install", { id: r.id, choices: {} });
    toast(`Installing ${r.title}…`);
    const fake = document.createElement("div");
    await watchJob(job, fake, `${r.title} is ready to play`);
    // ---- Online catalog (a JSON index in a GitHub repo, packages in GitHub Releases) ----
let catalog = null;
async function loadCatalog(force) {
  try { catalog = (await api("/api/catalog" + (force ? "?refresh=1" : ""))).mashups; }
  catch (e) { catalog = []; }
  renderCatalog();
}
function renderCatalog() {
  const shelf = $("#shelf-catalog"); if (!shelf) return;
  shelf.replaceChildren();
  if (catalog === null) { shelf.append(el("p", { class: "muted" }, "Loading the catalog…")); return; }
  if (!catalog.length) { shelf.append(el("p", { class: "muted" }, "No online catalog yet.")); return; }
  for (const e of catalog) {
    const label = e.update ? "Update" : e.in_library ? "In library" : "Get";
    const card = el("div", { class: "tile catalog-tile" },
      e.cover_url ? el("img", { src: `/art/catalog/${encodeURIComponent(e.id)}?t=${encodeURIComponent(TOKEN)}`, alt: "" }) : el("div", { class: "tile-fallback" }),
      el("span", { class: "chip" }, "v" + (e.version || "?")),
      el("div", { class: "tile-title" }, el("span", {}, e.title),
        el("span", { class: "tile-sub" }, (e.games || []).map(g => g.title || g.slug).join(" + ")),
        el("span", { class: "tile-actions" },
          el("button", { class: "pill", disabled: e.in_library && !e.update, onclick: async ev => {
            ev.stopPropagation();
            try { const { job } = await api("/api/catalog/get", { id: e.id }); toast(`Getting ${e.title}…`);
                  await watchJob(job, document.createElement("div"), `${e.title} is ready`); await refresh(); loadCatalog(); }
            catch (err) { toast(err.message, true); } } }, label),
          e.links && e.links.melty ? el("a", { class: "linkout", href: e.links.melty, target: "_blank", rel: "noopener" }, "On Melty") : null)));
    shelf.append(card);
  }
}

// ---- Melty through Wine (Linux) ----
async function loadMelty() {
  let st;
  try { st = await api("/api/melty"); } catch (e) { return; }
  const card = $("#melty-card");
  card.hidden = !st.supported;
  const btn = $("#melty-btn");
  btn.textContent = st.installed ? "Open Melty" : "Set up Melty";
  btn.onclick = async () => {
    try {
      if (st.installed) { toast((await api("/api/melty/open", {})).message); return; }
      const bar = card.querySelector(".progress"); bar.hidden = false;
      const { job } = await api("/api/melty/setup", {});
      await watchJob(job, bar.firstChild, "Melty is ready");
      bar.hidden = true; loadMelty();
    } catch (e) { toast(e.message, true); }
  };
}

refresh();
loadCatalog();
loadMelty();
  } catch (e) { toast(e.message, true); }
}

function renderDiscover() {
  const hero = $("#hero"); hero.replaceChildren();
  const list = state.mashups;
  if (!list.length) {
    hero.append(el("div", { class: "hero-empty" }, el("h2", {}, "Make two games one"),
      el("p", {}, "Add a .mashwright or Melty-format package to get started."),
      el("button", { onclick: () => goTab("add") }, "Add a mashup")));
  } else {
    heroIndex = heroIndex % list.length;
    list.forEach((m, i) => {
      const r = m.recipe, img = mashupArt(m);
      const tiles = [];
      r.games.forEach((g, gi) => {
        if (gi) tiles.push(el("span", { class: "plus", "aria-hidden": "true" }, "+"));
        tiles.push(gameTile((m.candidates[g.slug] || [])[0], g.title || g.slug, "hero-icon"));
      });
      hero.append(el("article", { class: "slide" + (i === heroIndex ? " active" : ""), "aria-hidden": i !== heroIndex,
                                  "aria-label": `${i + 1} of ${list.length}: ${r.title}` },
        img ? el("img", { class: "slide-bg", src: img, alt: "" }) : el("div", { class: "slide-bg fallback" }),
        el("div", { class: "slide-shade" }),
        el("div", { class: "slide-body" },
          el("div", { class: "hero-icons" }, tiles),
          el("h2", {}, r.title),
          el("p", { class: "by" }, (r.authors || []).join(", ") || "\u00a0"),
          el("button", { class: "pill big", onclick: () => mainAction(m) },
            m.desktop && m.status.installed ? (m.desktop.enabled ? "On your desktop ✓" : "Turn on")
              : m.status.installed ? "▶  Play" : m.ready ? "Install" : "Missing games"))));
    });
    if (list.length > 1) {
      const go = d => { heroIndex = (heroIndex + d + list.length) % list.length; renderDiscover(); };
      hero.append(el("button", { class: "hero-nav prev", "aria-label": "Previous", onclick: () => go(-1) }, "‹"),
                  el("button", { class: "hero-nav next", "aria-label": "Next", onclick: () => go(1) }, "›"),
                  el("div", { class: "dots" }, list.map((_, i) => el("button", { class: i === heroIndex ? "on" : "",
                    "aria-label": `Show ${i + 1}`, onclick: () => { heroIndex = i; renderDiscover(); } }))));
      clearTimeout(heroTimer);
      heroTimer = setTimeout(() => { if (!$("#panel-discover").hidden) go(1); }, 8000);
    }
  }
  const shelf = $("#shelf-mashups"); shelf.replaceChildren();
  for (const m of list) {
    const img = mashupArt(m);
    shelf.append(el("button", { class: "tile", onclick: () => goTab("mashups"), "aria-label": m.recipe.title },
      img ? el("img", { src: img, alt: "" }) : el("div", { class: "tile-fallback" }),
      el("span", { class: "chip" }, m.desktop ? (m.desktop.enabled ? "On your desktop" : "Desktop · off")
        : m.status.installed ? "Installed" : "v" + m.recipe.version),
      el("span", { class: "tile-title" }, m.recipe.title)));
  }
  if (!list.length) shelf.append(el("p", { class: "muted" }, "Nothing here yet."));
  const games = $("#shelf-games"); games.replaceChildren();
  for (const g of state.games.filter(g => g.install_dir)) {
    const a = g.extra.art || {};
    games.append(el("div", { class: "capsule", title: g.title },
      a.capsule ? el("img", { src: art(g.key, "capsule"), alt: g.title }) : el("div", { class: "capsule-fallback" }, g.title),
      el("span", { class: "capsule-badge" }, PLATFORM_NAMES[g.platform] || g.platform)));
  }
  if (!games.children.length) games.append(el("p", { class: "muted" }, "No games found yet — try Rescan."));
}

// ---- Online catalog (a JSON index in a GitHub repo, packages in GitHub Releases) ----
let catalog = null;
async function loadCatalog(force) {
  try { catalog = (await api("/api/catalog" + (force ? "?refresh=1" : ""))).mashups; }
  catch (e) { catalog = []; }
  renderCatalog();
}
function renderCatalog() {
  const shelf = $("#shelf-catalog"); if (!shelf) return;
  shelf.replaceChildren();
  if (catalog === null) { shelf.append(el("p", { class: "muted" }, "Loading the catalog…")); return; }
  if (!catalog.length) { shelf.append(el("p", { class: "muted" }, "No online catalog yet.")); return; }
  for (const e of catalog) {
    const label = e.update ? "Update" : e.in_library ? "In library" : "Get";
    const card = el("div", { class: "tile catalog-tile" },
      e.cover_url ? el("img", { src: `/art/catalog/${encodeURIComponent(e.id)}?t=${encodeURIComponent(TOKEN)}`, alt: "" }) : el("div", { class: "tile-fallback" }),
      el("span", { class: "chip" }, "v" + (e.version || "?")),
      el("div", { class: "tile-title" }, el("span", {}, e.title),
        el("span", { class: "tile-sub" }, (e.games || []).map(g => g.title || g.slug).join(" + ")),
        el("span", { class: "tile-actions" },
          el("button", { class: "pill", disabled: e.in_library && !e.update, onclick: async ev => {
            ev.stopPropagation();
            try { const { job } = await api("/api/catalog/get", { id: e.id }); toast(`Getting ${e.title}…`);
                  await watchJob(job, document.createElement("div"), `${e.title} is ready`); await refresh(); loadCatalog(); }
            catch (err) { toast(err.message, true); } } }, label),
          e.links && e.links.melty ? el("a", { class: "linkout", href: e.links.melty, target: "_blank", rel: "noopener" }, "On Melty") : null)));
    shelf.append(card);
  }
}

// ---- Melty through Wine (Linux) ----
async function loadMelty() {
  let st;
  try { st = await api("/api/melty"); } catch (e) { return; }
  const card = $("#melty-card");
  card.hidden = !st.supported;
  const btn = $("#melty-btn");
  btn.textContent = st.installed ? "Open Melty" : "Set up Melty";
  btn.onclick = async () => {
    try {
      if (st.installed) { toast((await api("/api/melty/open", {})).message); return; }
      const bar = card.querySelector(".progress"); bar.hidden = false;
      const { job } = await api("/api/melty/setup", {});
      await watchJob(job, bar.firstChild, "Melty is ready");
      bar.hidden = true; loadMelty();
    } catch (e) { toast(e.message, true); }
  };
}

refresh();
loadCatalog();
loadMelty();
    goTab("mashups");
  } catch (e) { toast(e.message, true); }
}
const drop = $("#drop"), fileIn = $("#file");
drop.addEventListener("click", () => fileIn.click());
drop.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileIn.click(); } });
fileIn.addEventListener("change", () => fileIn.files[0] && upload(fileIn.files[0]));
drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", e => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
$("#import-path").addEventListener("submit", async e => {
  e.preventDefault();
  try { const { recipe } = await api("/api/import", { path: e.target.path.value }); toast(`Added ${recipe.title}`); e.target.reset(); refresh(); goTab("mashups"); }
  catch (err) { toast(err.message, true); }
});
$("#custom").addEventListener("submit", async e => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  try { const { game } = await api("/api/custom-game", f); toast(`Added ${game.title}`); e.target.reset(); refresh(); }
  catch (err) { toast(err.message, true); }
});

async function loadLog() {
  try { $("#log").textContent = (await api("/api/log")).lines.join("\n") || "Nothing yet."; } catch (e) { toast(e.message, true); }
}

// ---- Discover ----
const art = (key, kind) => `/art/game/${encodeURIComponent(key)}/${kind}?t=${encodeURIComponent(TOKEN)}`;
const cover = id => `/art/mashup/${encodeURIComponent(id)}?t=${encodeURIComponent(TOKEN)}`;
let heroIndex = 0, heroTimer = null;

function gameTile(g, slug, cls) {
  // A game's icon from its store artwork, or its initials on a tile.
  const kind = g && g.extra && g.extra.art && (g.extra.art.icon ? "icon" : g.extra.art.capsule ? "capsule" : null);
  if (kind) return el("img", { class: cls, src: art(g.key, kind), alt: g.title, title: g.title });
  const name = (g && g.title) || slug;
  return el("span", { class: cls + " initials", title: name }, name.split(/\W+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join(""));
}

function mashupArt(m) {
  if (m.recipe.cover) return cover(m.recipe.id);
  const primary = m.recipe.games.find(g => g.role === "primary") || m.recipe.games[0];
  const g = (m.candidates[primary.slug] || [])[0];
  return g && g.extra.art && g.extra.art.hero ? art(g.key, "hero") : null;
}

async function mainAction(m) {
  const r = m.recipe;
  try {
    if (m.desktop && m.status.installed) {
      await api("/api/desktop", { id: r.id, on: !m.desktop.enabled });
      toast(m.desktop.enabled ? `${r.title} is off` : `${r.title} is on`); refresh(); return;
    }
    if (m.status.installed) { toast((await api("/api/launch", { id: r.id })).message); return; }
    if (!m.ready) { toast("Missing: " + m.missing.join(", "), true); return; }
    const { job } = await api("/api/install", { id: r.id, choices: {} });
    toast(`Installing ${r.title}…`);
    const fake = document.createElement("div");
    await watchJob(job, fake, `${r.title} is ready to play`);
    // ---- Online catalog (a JSON index in a GitHub repo, packages in GitHub Releases) ----
let catalog = null;
async function loadCatalog(force) {
  try { catalog = (await api("/api/catalog" + (force ? "?refresh=1" : ""))).mashups; }
  catch (e) { catalog = []; }
  renderCatalog();
}
function renderCatalog() {
  const shelf = $("#shelf-catalog"); if (!shelf) return;
  shelf.replaceChildren();
  if (catalog === null) { shelf.append(el("p", { class: "muted" }, "Loading the catalog…")); return; }
  if (!catalog.length) { shelf.append(el("p", { class: "muted" }, "No online catalog yet.")); return; }
  for (const e of catalog) {
    const label = e.update ? "Update" : e.in_library ? "In library" : "Get";
    const card = el("div", { class: "tile catalog-tile" },
      e.cover_url ? el("img", { src: `/art/catalog/${encodeURIComponent(e.id)}?t=${encodeURIComponent(TOKEN)}`, alt: "" }) : el("div", { class: "tile-fallback" }),
      el("span", { class: "chip" }, "v" + (e.version || "?")),
      el("div", { class: "tile-title" }, el("span", {}, e.title),
        el("span", { class: "tile-sub" }, (e.games || []).map(g => g.title || g.slug).join(" + ")),
        el("span", { class: "tile-actions" },
          el("button", { class: "pill", disabled: e.in_library && !e.update, onclick: async ev => {
            ev.stopPropagation();
            try { const { job } = await api("/api/catalog/get", { id: e.id }); toast(`Getting ${e.title}…`);
                  await watchJob(job, document.createElement("div"), `${e.title} is ready`); await refresh(); loadCatalog(); }
            catch (err) { toast(err.message, true); } } }, label),
          e.links && e.links.melty ? el("a", { class: "linkout", href: e.links.melty, target: "_blank", rel: "noopener" }, "On Melty") : null)));
    shelf.append(card);
  }
}

// ---- Melty through Wine (Linux) ----
async function loadMelty() {
  let st;
  try { st = await api("/api/melty"); } catch (e) { return; }
  const card = $("#melty-card");
  card.hidden = !st.supported;
  const btn = $("#melty-btn");
  btn.textContent = st.installed ? "Open Melty" : "Set up Melty";
  btn.onclick = async () => {
    try {
      if (st.installed) { toast((await api("/api/melty/open", {})).message); return; }
      const bar = card.querySelector(".progress"); bar.hidden = false;
      const { job } = await api("/api/melty/setup", {});
      await watchJob(job, bar.firstChild, "Melty is ready");
      bar.hidden = true; loadMelty();
    } catch (e) { toast(e.message, true); }
  };
}

refresh();
loadCatalog();
loadMelty();
  } catch (e) { toast(e.message, true); }
}

function renderDiscover() {
  const hero = $("#hero"); hero.replaceChildren();
  const list = state.mashups;
  if (!list.length) {
    hero.append(el("div", { class: "hero-empty" }, el("h2", {}, "Make two games one"),
      el("p", {}, "Add a .mashwright or Melty-format package to get started."),
      el("button", { onclick: () => goTab("add") }, "Add a mashup")));
  } else {
    heroIndex = heroIndex % list.length;
    list.forEach((m, i) => {
      const r = m.recipe, img = mashupArt(m);
      const tiles = [];
      r.games.forEach((g, gi) => {
        if (gi) tiles.push(el("span", { class: "plus", "aria-hidden": "true" }, "+"));
        tiles.push(gameTile((m.candidates[g.slug] || [])[0], g.title || g.slug, "hero-icon"));
      });
      hero.append(el("article", { class: "slide" + (i === heroIndex ? " active" : ""), "aria-hidden": i !== heroIndex,
                                  "aria-label": `${i + 1} of ${list.length}: ${r.title}` },
        img ? el("img", { class: "slide-bg", src: img, alt: "" }) : el("div", { class: "slide-bg fallback" }),
        el("div", { class: "slide-shade" }),
        el("div", { class: "slide-body" },
          el("div", { class: "hero-icons" }, tiles),
          el("h2", {}, r.title),
          el("p", { class: "by" }, (r.authors || []).join(", ") || "\u00a0"),
          el("button", { class: "pill big", onclick: () => mainAction(m) },
            m.desktop && m.status.installed ? (m.desktop.enabled ? "On your desktop ✓" : "Turn on")
              : m.status.installed ? "▶  Play" : m.ready ? "Install" : "Missing games"))));
    });
    if (list.length > 1) {
      const go = d => { heroIndex = (heroIndex + d + list.length) % list.length; renderDiscover(); };
      hero.append(el("button", { class: "hero-nav prev", "aria-label": "Previous", onclick: () => go(-1) }, "‹"),
                  el("button", { class: "hero-nav next", "aria-label": "Next", onclick: () => go(1) }, "›"),
                  el("div", { class: "dots" }, list.map((_, i) => el("button", { class: i === heroIndex ? "on" : "",
                    "aria-label": `Show ${i + 1}`, onclick: () => { heroIndex = i; renderDiscover(); } }))));
      clearTimeout(heroTimer);
      heroTimer = setTimeout(() => { if (!$("#panel-discover").hidden) go(1); }, 8000);
    }
  }
  const shelf = $("#shelf-mashups"); shelf.replaceChildren();
  for (const m of list) {
    const img = mashupArt(m);
    shelf.append(el("button", { class: "tile", onclick: () => goTab("mashups"), "aria-label": m.recipe.title },
      img ? el("img", { src: img, alt: "" }) : el("div", { class: "tile-fallback" }),
      el("span", { class: "chip" }, m.desktop ? (m.desktop.enabled ? "On your desktop" : "Desktop · off")
        : m.status.installed ? "Installed" : "v" + m.recipe.version),
      el("span", { class: "tile-title" }, m.recipe.title)));
  }
  if (!list.length) shelf.append(el("p", { class: "muted" }, "Nothing here yet."));
  const games = $("#shelf-games"); games.replaceChildren();
  for (const g of state.games.filter(g => g.install_dir)) {
    const a = g.extra.art || {};
    games.append(el("div", { class: "capsule", title: g.title },
      a.capsule ? el("img", { src: art(g.key, "capsule"), alt: g.title }) : el("div", { class: "capsule-fallback" }, g.title),
      el("span", { class: "capsule-badge" }, PLATFORM_NAMES[g.platform] || g.platform)));
  }
  if (!games.children.length) games.append(el("p", { class: "muted" }, "No games found yet — try Rescan."));
}

// ---- Online catalog (a JSON index in a GitHub repo, packages in GitHub Releases) ----
let catalog = null;
async function loadCatalog(force) {
  try { catalog = (await api("/api/catalog" + (force ? "?refresh=1" : ""))).mashups; }
  catch (e) { catalog = []; }
  renderCatalog();
}
function renderCatalog() {
  const shelf = $("#shelf-catalog"); if (!shelf) return;
  shelf.replaceChildren();
  if (catalog === null) { shelf.append(el("p", { class: "muted" }, "Loading the catalog…")); return; }
  if (!catalog.length) { shelf.append(el("p", { class: "muted" }, "No online catalog yet.")); return; }
  for (const e of catalog) {
    const label = e.update ? "Update" : e.in_library ? "In library" : "Get";
    const card = el("div", { class: "tile catalog-tile" },
      e.cover_url ? el("img", { src: `/art/catalog/${encodeURIComponent(e.id)}?t=${encodeURIComponent(TOKEN)}`, alt: "" }) : el("div", { class: "tile-fallback" }),
      el("span", { class: "chip" }, "v" + (e.version || "?")),
      el("div", { class: "tile-title" }, el("span", {}, e.title),
        el("span", { class: "tile-sub" }, (e.games || []).map(g => g.title || g.slug).join(" + ")),
        el("span", { class: "tile-actions" },
          el("button", { class: "pill", disabled: e.in_library && !e.update, onclick: async ev => {
            ev.stopPropagation();
            try { const { job } = await api("/api/catalog/get", { id: e.id }); toast(`Getting ${e.title}…`);
                  await watchJob(job, document.createElement("div"), `${e.title} is ready`); await refresh(); loadCatalog(); }
            catch (err) { toast(err.message, true); } } }, label),
          e.links && e.links.melty ? el("a", { class: "linkout", href: e.links.melty, target: "_blank", rel: "noopener" }, "On Melty") : null)));
    shelf.append(card);
  }
}

// ---- Melty through Wine (Linux) ----
async function loadMelty() {
  let st;
  try { st = await api("/api/melty"); } catch (e) { return; }
  const card = $("#melty-card");
  card.hidden = !st.supported;
  const btn = $("#melty-btn");
  btn.textContent = st.installed ? "Open Melty" : "Set up Melty";
  btn.onclick = async () => {
    try {
      if (st.installed) { toast((await api("/api/melty/open", {})).message); return; }
      const bar = card.querySelector(".progress"); bar.hidden = false;
      const { job } = await api("/api/melty/setup", {});
      await watchJob(job, bar.firstChild, "Melty is ready");
      bar.hidden = true; loadMelty();
    } catch (e) { toast(e.message, true); }
  };
}

refresh();
loadCatalog();
loadMelty();
