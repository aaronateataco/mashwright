# Hue Potato — MODLOG

Brotato × Hue mashup for Melty. Journal of facts, decisions and dead ends.

## Versions (this PC, 2026-10-07)
- Brotato 1.1.15.4 (Steam app 1942280), Godot 3.x custom ("3.7"), GDScript 1.0, pck not encrypted.
  Install: `G:\SteamLibrary\steamapps\common\Brotato`. Saves: `%APPDATA%\Brotato\<steamid>`; logs `%APPDATA%\Brotato\logs`.
- Built-in Godot Mod Loader **6.3.0** (in Brotato.pck). Melty's "godot-mod-loader v7.0.1" is the Godot-4 self-setup zip:
  loose `addons/` files only, no override.cfg → inert in Brotato (pck copy wins). Harmless.
- Hue (Steam 383270), Unity **5.3.6f1**, Mono, serialized file format **v15, no type trees**, little-endian.
  Install: `G:\SteamLibrary\steamapps\common\Hue\Hue_Data`.
- vgmstream r2117 (win64) for FSB5 Vorbis → WAV. ISC licence; bundles FFmpeg/mpg123 (LGPL, unmodified DLLs), libvorbis/speex/celt (BSD), atrac9 (MIT), g719.

## Route
- Godot Mod Loader 6.3 mod (zip with `mods-unpacked/HueBrotato-HuePotato/…`), script extensions + runtime-built resources.
- **Steam builds only load subscribed Workshop items** (`_custom_features="steam"` → options profile `steam.tres` with
  `steam_workshop_enabled = true`; `{game}/mods` is never scanned). Verified in game: a test zip in `{game}/mods` was ignored.
- Fix (verified in game): `{game}/override.cfg` adds autoload `HuePotatoBoot="*res://mods/huepotato_boot.gd"`.
  Godot resolves `res://` paths missing from the pck to loose files next to the exe, and override.cfg autoloads are
  instanced after the pck's own (so after ModLoader finished). The boot script hands every `{game}/mods/*.zip` that the
  loader skipped to ModLoader's own init path. No game file is modified.
- Hue content is read at runtime from the player's Hue install (Steam library lookup / Melty settings file). Nothing shipped.

## Hue data facts
- Colours: `HueColour.GenerateHashTable()` (Lime 145,235,0 · Aqua 0,177,233 · Blue 38,49,255 · Purple 172,0,255 ·
  Pink 244,59,166 · Red 255,20,27 · Orange 255,138,0 · Yellow 255,205,0).
- Wheel: hold → `Time.timeScale = 0.1`, `UIWheel/open`, slice chime per colour (`a_hue colorwheel 1..8`).
- Mum's voice letters `N-VO-<Colour>` (resources.assets) numbered in unlock order: Aqua, Purple, Orange, Pink, Red, Blue, Yellow, Lime.
  Subtitles: TextAsset `HueText` (CSV key,EN,FR,RU,DE,ES), keys `VO/<Colour><n>`.
- Textures: mostly ARGB32 (fmt 5) and DXT5 (fmt 12); data in `.resS` via StreamingInfo. Unity rows bottom-up.
- Sprites (v15): textureRect = last 44 bytes − (rect16, rectOffset8, settingsRaw4, uvTransform16); texture PPtr after atlasTags.
- AudioClip: m_Resource (source string, u64 offset, u64 size) into `.resource` → FSB5.

## Decisions
- Host Brotato (primary); Hue role "secondary" (not in Melty catalog).
- Character "Hue Potato": dark potato + Hue's real hair/ear/eyes; only he has the wheel ("hide to dodge").
- Colours earned by wave (Aqua+Purple at start, then Orange w3, Pink w5, Red w7, Blue w9, Yellow w11, Lime w13).
- Regions → Hue map icons + music per wave span. Fragment pickup plays Mum's letter (voice + subtitles).
- Solo first. Bosses, elites, loot aliens and charmed enemies stay colourless (like Hue's black objects).

## Dead ends
- `{game}/mods` alone does not load on Steam (see Route).
- UnityPy's astc_encoder DLL fails to import on this PC → stubbed (Hue has no ASTC textures).

## Melty
- Draft listing: modId f19f626b-e79d-4903-8bdc-42236e73df73, slug hue-potato, Studio https://melty.gg/studio/f19f626b-e79d-4903-8bdc-42236e73df73
- Licence MIT, remixes allowed, credited to the publisher's Melty name (chosen by the owner 2026-10-07).
- Packages: HuePotato-Mod.zip (outer zip; Melty can't place an unextracted archive) -> {game}/mods, HuePotato-Boot.zip -> {game}, HuePotato-vgmstream.zip -> {game}/mods. one_click_check: yes.
- Gotchas found in game: InputService.enable/disable_gamepad_movement reloads the InputMap (mod re-adds actions); reloading a compiled .gdc subclass wipes it (don't); a saved run is restored inside ProgressData._ready, so register the character synchronously in mod_main._ready.
- Brotato's CrashReporter disables all mods on the next start when the last engine log has an ERROR line naming mods-unpacked. Saved runs store appearance texture paths, so runtime textures live at res://huepotato_runtime/ (a failed lookup can't trip it).

## Polish + compatibility (2026-10-07 evening)
- Boot loads mods/ zip by zip, skips already-loaded zips/mods, respects disabled_mods, runs once; avoids the loader helper's mods-unpacked error when that folder doesn't exist yet.
- Tint/alpha/layer changes multiply onto and restore other mods' values; floor/time scale relative. Verified with a test mod that extends main.gd and tints enemies/floor (CompatProbe, scratch only): all checks passed.
- Options sheet + huepotato.cfg [options]; colour-change wave; letters pause with Brotato's pause; run-lost hides wheel and stops letters.
- Hue's Ink Ring weapon (weapons sheet): fist scene + script extending MeleeWeapon (fine: our script is new, not a reloaded vanilla subclass); swirls are duplicated hitboxes, pulsed on cooldown; ring breathes (playtest: enemies hugging the potato sat inside a fixed ring). Not looted; Hue Potato's first starting weapon.

## Laser Ring replaces the Ink Ring (2026-10-07 night)
- Owner clarified the ring should be Hue's lasers, not the title-screen ink. hue_assets: LaserBeam (sharedassets63 pid 4), LaserCanon (pid 3), LaserCanon-mask (pid 5); ink rows removed.
- src/hue_laser_ring.gd: 3-6 cannons (by tier) orbit and breathe; beam i joins cannon i to i+1, colour = owned[i % n]; rectangle hitbox per beam (extents follow the chord), pulsed on cooldown; background-colour beam fades + hitbox off. Beam strip trimmed + FLAG_REPEAT and scrolled via region_rect.
- Hue's cannon mask is red: multiplying it by a colour turns aqua/blue rims black, so the registry makes a whitened copy.
- In game: hits counted, background beams harmless (probe 49 pass / 0 fail), tooltip/name/damage tracking OK, saved-run resume OK. Test run ended; dev install removed.
## More Hue (2026-10-09)
- Owner asked for more Hue, polish, a fix for "invulnerable to all monsters", and a burst-picked cover. The invulnerability was the old test probe's own pl.disable_hurtbox() (test only, never in the mod): Brotato re-enables enemy hitboxes every frame, HueTint only switches them off while hidden. New probe records every hit instead (FAIL if a hidden enemy/bullet/hazard hurts) and heals when low; DebugService.disable_saving so tests never leave a saved run.
- New sheets: hazards (laser_gate w3+, skull_boulder w7+), letters (Intro w1, Water w3, Fire w5, Temple w7, Mountains w9, Tech w11, TechEnd w12, UniversityStart w13; UniversityEnd + PS on a win). Letters queue (Mum never cuts herself off). Crates replace trees (neutral_respawned + child node), Dr Grey banner + DrGreyAppears sting on wave nb_of_waves, Hue dust motes (CPUParticles2D under the entities). Options hue_hazards/hue_crates/hue_dust.
- Hazard damage: overlap/hitbox.tscn instance on layer 4 (what the player hurtbox's mask 20 listens to), from = null (all Brotato handlers guard it).
- Compile check without the games: C:\Users\Aaron\BrotatoDecomp is a full Godot 3 project; a junction mods-unpacked -> our mod plus hue_check.tscn loads every script (Godot 3.6.3 headless). The decomp's ModLoader also loads the mod, so extensions/main.gd sometimes reports a duplicate member: an artefact of loading it twice.
- G: (Brotato + Hue) was disconnected during this work; asset verification and in-game tests wait for it.