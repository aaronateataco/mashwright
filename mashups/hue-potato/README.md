# Hue Potato

**Hue joins Brotato.** Pick *Hue Potato* on Brotato's character select: a dark potato wearing Hue's
own hair, ear and eyes, carrying Hue's colour wheel.

- **Hue's colour wheel.** Hold Right Click / Space / a trigger to open it; time slows to Hue's 0.1×
  while you choose. Pick a colour and the arena floor takes it on. Enemies and enemy bullets *of that
  colour vanish* — they can't hurt you, and you can't hurt them. Switch back to bring them in range.
  Quick switch with Q / E (or mouse wheel, or the bumpers); G or the middle button returns to grey.
- **Hue's Laser Ring**, Hue Potato's own weapon: Hue's laser cannons orbit you, each firing Hue's
  laser beam at the next, so the beams make a spinning fence that closes in and opens out. Beams take
  the colours you've found; a beam the colour of the background vanishes and leaves a gap. Four
  tiers (3 to 6 cannons); scales with melee and elemental damage and attack speed.
- **Earn the colours like in Hue.** Start with Aqua and Purple. A colour fragment appears every other
  wave (Orange, Pink, Red, Blue, Yellow, Lime). Enemies only come in colours you've found.
- **Mum's letters.** Mum's intro letter opens the run, each region and each colour fragment brings her
  letter for it, and winning the run brings her last letter and PS, read aloud with subtitles from Hue
  in your language (English, French, Russian, German or Spanish). She never cuts herself off: a letter
  that comes while she is reading waits its turn.
- **Hue's laser gates** (from wave 3): two of Hue's laser cannons switch on at opposite edges of the
  arena and a laser wall burns between them. Switch to its colour to walk through.
- **Hue's skull boulders** (from wave 7) roll across the arena at you. Switch to a boulder's colour and
  it rolls straight through. Both hazards hurt you through Brotato's own damage (dodge, armour and
  invincibility frames count).
- **Hue's crates** take the place of Brotato's trees, each in a colour (and vanishing with it). They
  break with Hue's crate sound.
- **Dr Grey** appears for the final wave, with his music from Hue. Hue's dust motes drift over the
  arena.
- **A run through Hue's world.** Waves travel through the Village, Waterfall, Fire Caves, Temple,
  Mountains, Laboratory, University and Island, each with Hue's map icon and Hue's music.
- **Hue items in the shop:** Mum's Letter, Hue's Beaker, Mum's Goggles, Grey Butterfly, Village
  Lantern and Lighthouse Life Ring, with Hue icons. Several change how the wheel plays.
- Bosses, elites and loot aliens stay solid, like Hue's black objects.

Single player (Brotato's local co-op still works; the wheel follows the first controller/keyboard).

## Needs
- **Brotato** (Steam), version 1.1.15.x.
- **Hue** installed (Steam, GOG or Epic). Hue Potato reads Hue's art, music, sounds and Mum's letters
  from your own copy while the game runs; nothing from Hue is included. Without Hue the title screen
  says so and Hue Potato isn't offered. If Hue is somewhere unusual, put
  `[hue]` / `data_dir="D:/Games/Hue/Hue_Data"` in `%APPDATA%\Brotato\huepotato.cfg`.

## How it installs (Melty does all of this)
- `mods/HueBrotato-HuePotato.zip` — the Godot Mod Loader mod.
- `mods/huepotato-vgmstream/` — vgmstream, which decodes Hue's audio (see THIRD_PARTY.txt).
- `override.cfg` + `mods/huepotato_boot.gd` — Brotato's Steam build only loads Steam Workshop mods;
  this small boot script hands mods in `mods/` to Brotato's own built-in mod loader. No game file is
  changed, and removing these files restores the game exactly.

## Options
Put these under `[options]` in `%APPDATA%\Brotato\huepotato.cfg` (`true` / `false`):
- `hue_music` (true): Hue's region music in Hue Potato runs. Turn it off to keep Brotato's music,
  or a music mod's.
- `mum_letters` (true): Mum's voice letters with subtitles.
- `hue_items_in_shop` (true): the six Hue items in Brotato's shop pool.
- `colourblind_symbols` (false): Hue's colourblind symbol over each coloured enemy.
- `switch_wave` (true): the colour wave that sweeps out when the colour changes.
- `hue_hazards` (true): Hue's laser gates and skull boulders.
- `hue_crates` (true): Brotato's trees become Hue's crates.
- `hue_dust` (true): Hue's dust motes over the arena.

## Playing with other mods
- Works alongside other Godot Mod Loader mods (tested with Brotatogether loaded from the Workshop
  and a second mod in `mods/`). Only `main.gd` and `player.gd` are extended, and both extensions
  chain with other mods' extensions of the same scripts.
- Enemy and bullet colours go on top of any tint or transparency another mod sets, and are put back
  exactly afterwards; the floor tint and the wheel's slow-motion scale whatever was already set.
- Everything is off for other characters, so other character mods are unaffected.
- The boot script loads each mod zip in `mods/` that Brotato's Steam build skips, once, and leaves
  alone any mod already loaded (for example its Workshop copy) or disabled in the mod loader options.
- Online co-op mods (such as Brotatogether's online mode) aren't supported for Hue Potato runs yet:
  the colour wheel isn't synchronised between players.

## Credits
- Hue © Fiddlesticks / Curve Digital. Brotato © Blobfish. This is an unofficial fan mashup; it uses
  your own installed copies of both games.
- vgmstream by bnnm and contributors (ISC), with the libraries listed in THIRD_PARTY.txt.
- Built with Godot Mod Loader (built into Brotato) and the universal-modder toolkit.

## Building from source
    python3 tools/fetch_vendor.py      # vgmstream builds (Windows/Linux/macOS) into _vendor/
    python3 tools/gen.py               # sheets -> mod/.../generated/sheets.gd
    BROTATO_DECOMP=/path/to/your/decompiled/Brotato python3 tools/preflight.py
    python3 tools/build.py             # build/*.zip (Melty-format packages)
`preflight.py` checks the mod against a decompilation of your own copy of Brotato (not included);
`verify_hue_assets.py` checks the asset sheet against your own Hue install. The headless test project
in `tests/test_project` needs `entities/units/player/potato.png` copied from your Brotato.
