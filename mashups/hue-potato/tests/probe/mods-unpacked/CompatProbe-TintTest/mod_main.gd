extends Node

# Test-only mod (never shipped): behaves like another visual mod (extends main.gd, tints enemies
# and the floor) and checks Hue Potato in the real game. Settings come from probe.cfg next to the
# probe zip's folder (see CFG) under [probe]: mode ("test" | "showcase"), autostart, starting_wave,
# wave_duration, quit_after_s, cycle_s, spawn_hazards, hazard_every_s, ring_tier, capture_every_s,
# capture_dir, capture_max, capture_start_s. Runs never save while the probe is installed.

const CFG_NAME = "huepotato_probe.cfg"
const TITLE = "res://ui/menus/title_screen/title_screen.tscn"
const CHAR_SELECT = "res://ui/menus/run/character_selection.tscn"

var cfg := ConfigFile.new()
var _started := false
var _step_ms := 0
var _quit_at_ms := 0


func _init() -> void:
	ModLoaderMod.install_script_extension("res://mods-unpacked/CompatProbe-TintTest/extensions/main.gd")
	# The config sits next to the game executable (the probe is installed alongside the game).
	var _e := cfg.load(OS.get_executable_path().get_base_dir().plus_file("mods").plus_file(CFG_NAME))
	Engine.set_meta("hue_probe", self)
	ModLoaderLog.info("PROBE init mode=%s" % setting("mode", "test"), "CompatProbe")


func _ready() -> void:
	pause_mode = PAUSE_MODE_PROCESS
	DebugService.disable_saving = true
	DebugService.starting_wave = int(setting("starting_wave", 1))
	DebugService.custom_wave_duration = int(setting("wave_duration", -1))
	DebugService.invulnerable = false
	var q := float(setting("quit_after_s", 0.0))
	if q > 0.0:
		_quit_at_ms = OS.get_ticks_msec() + int(q * 1000)
	ModLoaderLog.info("PROBE debug: wave %d, duration %d, no saving, quit after %s s" % [DebugService.starting_wave, DebugService.custom_wave_duration, q], "CompatProbe")


func setting(key: String, default):
	return cfg.get_value("probe", key, default)


func _process(_delta: float) -> void:
	var now := OS.get_ticks_msec()
	if _quit_at_ms > 0 and now >= _quit_at_ms:
		ModLoaderLog.info("PROBE quitting (quit_after_s)", "CompatProbe")
		get_tree().quit()
		return
	_give_ring()
	if not bool(setting("autostart", false)) or _started or now < _step_ms:
		return
	var scene := get_tree().current_scene
	if scene == null:
		return
	var hp = Engine.get_meta("hue_potato") if Engine.has_meta("hue_potato") else null
	if hp == null or hp.registry == null:
		return
	_step_ms = now + 1500
	ModLoaderLog.info("PROBE autostart: on %s" % scene.filename, "CompatProbe")
	if scene.filename == MenuData.title_screen_scene or scene.filename == TITLE:
		ModLoaderLog.info("PROBE autostart: title -> character selection", "CompatProbe")
		var _e := get_tree().change_scene(MenuData.character_selection_scene)
	elif scene.filename == MenuData.character_selection_scene or scene.filename == CHAR_SELECT:
		_start_run(hp)


# Starts a Hue Potato run the way Brotato's selection screens do (character, weapon, difficulty 0).
func _start_run(hp) -> void:
	var hue = null
	for c in ItemService.characters:
		if hp.is_hue_character(c):
			hue = c
	if hue == null:
		ModLoaderLog.info("PROBE FAIL: Hue Potato is not in ItemService.characters", "CompatProbe")
		_started = true
		return
	_started = true
	RunData.reset()
	RunData.add_character(hue, 0)
	if RunData.some_player_has_weapon_slots():
		var weapon = hue.starting_weapons[0] if hue.starting_weapons.size() > 0 else null
		var tier := int(setting("ring_tier", 0))
		if tier > 0:
			for w in ItemService.weapons:
				if w.my_id == "weapon_hue_laser_ring_%d" % tier:
					weapon = w
		if weapon != null:
			var _w = RunData.add_weapon(weapon, 0, true)
	RunData.add_starting_items_and_weapons()
	RunData.current_difficulty = 0
	RunData.reset_elites_spawn()
	RunData.init_elites_spawn()
	RunData.init_events_nightmare()
	RunData.enabled_dlcs = ProgressData.get_active_dlc_ids()
	RunData.init_bosses_spawn()
	RunData.current_run_accessibility_settings = ProgressData.settings.enemy_scaling.duplicate()
	ModLoaderLog.info("PROBE autostart: Hue Potato run at wave %d" % RunData.current_wave, "CompatProbe")
	var _e := get_tree().change_scene(MenuData.game_scene)


# Without autostart, hand the chosen Laser Ring tier to the next run through DebugService.
func _give_ring() -> void:
	var tier := int(setting("ring_tier", 0))
	if tier <= 0 or bool(setting("autostart", false)) or not DebugService.debug_weapons.empty():
		return
	for w in ItemService.weapons:
		if w.my_id == "weapon_hue_laser_ring_%d" % tier:
			DebugService.debug_weapons = [w]
			DebugService.remove_starting_weapons = true
