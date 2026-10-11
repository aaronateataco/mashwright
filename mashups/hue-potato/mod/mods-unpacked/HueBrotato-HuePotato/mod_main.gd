extends Node

# Hue Potato: Hue (the game) in Brotato. Hue joins the roster as a potato wearing Hue's own hair,
# ear and eyes, with Hue's colour wheel: enemies and bullets the colour of the background vanish.
# Everything from Hue (art, music, sounds, Mum's letters) is read from the player's own copy of Hue
# while the game runs; see src/hue_content.gd. Design data lives in ../../sheets (generated into
# generated/sheets.gd).

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")
const Content = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_content.gd")
const Registry = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_registry.gd")
const Audio = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_audio.gd")
const Overlay = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_overlay.gd")
const Run = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_run.gd")

const LOG_NAME = "HuePotato"
# Only scripts no compiled Brotato script inherits from: when the boot script loads the mod, the
# loader applies extensions after Brotato's autoloads, and subclasses compiled by then would keep
# the old parent (reloading a compiled .gdc wipes it). Enemies and bullets are handled by child
# nodes and the run controller instead.
const EXTENSIONS = ["extensions/main.gd", "extensions/player.gd"]
const TITLE_SCENE = "res://ui/menus/title_screen/title_screen.tscn"
const RUN_SCENES = ["res://main.tscn", "res://ui/menus/shop/shop.tscn", "res://ui/menus/shop/coop_shop.tscn"]
# Mum keeps reading her last letter over Brotato's end screen.
const END_SCENES = ["res://ui/menus/run/end_run.tscn", "res://ui/menus/run/coop_end_run.tscn"]
const INPUT_CONSTANTS = {
	"KEY_SPACE": KEY_SPACE, "KEY_SHIFT": KEY_SHIFT, "KEY_E": KEY_E, "KEY_Q": KEY_Q, "KEY_G": KEY_G,
	"BUTTON_RIGHT": BUTTON_RIGHT, "BUTTON_MIDDLE": BUTTON_MIDDLE,
	"BUTTON_WHEEL_UP": BUTTON_WHEEL_UP, "BUTTON_WHEEL_DOWN": BUTTON_WHEEL_DOWN,
	"JOY_L": JOY_L, "JOY_R": JOY_R, "JOY_L2": JOY_L2, "JOY_R2": JOY_R2, "JOY_L3": JOY_L3,
}

var content = null
var registry = null
var audio = null
var overlay = null
var run = null                  # the HueRun of the wave being played, if any
var last_bg: String = D.GREY    # background colour carried from wave to wave
var hazard_hinted := {}         # hazard id -> its hint banner was shown this run
var _options := ConfigFile.new()
var textures := {}              # hue asset id -> Texture (icons, glow, symbol disc)
var symbol_textures := {}       # colour id -> Texture (Hue's colourblind symbol)
var _scene_check_ms := 0
var _in_run_scene := false
var _in_letter_scene := false


func _init() -> void:
	for ext in EXTENSIONS:
		ModLoaderMod.install_script_extension(D.MOD_DIR + ext)
	_add_translations()
	_add_input_actions()
	var _err := _options.load("user://huepotato.cfg")
	var shown := []
	for id in D.Sheets.OPTIONS_ORDER:
		shown.append("%s=%s" % [id, opt(id)])
	ModLoaderLog.info("Options: " + PoolStringArray(shown).join(", "), LOG_NAME)
	Engine.set_meta("hue_potato", self)
	ModLoaderLog.info("Hue Potato ready to read Hue", LOG_NAME)


func _ready() -> void:
	pause_mode = PAUSE_MODE_PROCESS
	content = Content.new()
	add_child(content)
	audio = Audio.new()
	audio.content = content
	add_child(audio)
	overlay = Overlay.new()
	add_child(overlay)
	audio.connect("letter_line", overlay, "show_subtitle")
	content.connect("art_ready", self, "_on_art_ready")
	# Before ProgressData._ready restores a saved run (which may be a Hue Potato run).
	content.start()


func _process(_delta: float) -> void:
	# Brotato reloads the InputMap from project settings when gamepad movement toggles.
	if not InputMap.has_action(D.Sheets.INPUT_ORDER[0]):
		_add_input_actions()
	var now := OS.get_ticks_msec()
	if now < _scene_check_ms:
		return
	_scene_check_ms = now + 400
	var scene := get_tree().current_scene
	var path: String = scene.filename if scene else ""
	var in_run := RUN_SCENES.has(path)
	var in_letter_scene := in_run or END_SCENES.has(path)
	if _in_run_scene and not in_run:
		audio.stop_music()
		last_bg = D.GREY
	if _in_letter_scene and not in_letter_scene:
		audio.stop_letter()
	_in_run_scene = in_run
	_in_letter_scene = in_letter_scene
	var missing: bool = content.state == Content.STATE_MISSING or content.state == Content.STATE_FAILED
	overlay.set_notice(tr("HUE_MISSING") if missing and path == TITLE_SCENE else "")


func _on_art_ready(ok: bool) -> void:
	if not ok:
		ModLoaderLog.warning("Hue Potato is not offered: %s" % ("Hue is not installed" if content.state == Content.STATE_MISSING else content.error), LOG_NAME)
		return
	for id in content.images:
		var t := ImageTexture.new()
		t.create_from_image(content.images[id], Texture.FLAG_FILTER)
		textures[id] = t
	for colour_id in D.Sheets.COLOURS_ORDER:
		symbol_textures[colour_id] = textures[D.colour_row(colour_id).symbol]
	registry = Registry.new()
	registry.register(content, opt("hue_items_in_shop"))
	ModLoaderLog.success("Hue Potato registered; %d Hue items %s" % [registry.items.size(), "in the shop" if opt("hue_items_in_shop") else "kept out of the shop (option)"], LOG_NAME)


# ---- used by the extensions and the run controller ------------------------------------------

func is_hue_run() -> bool:
	if registry == null:
		return false
	for i in RunData.get_player_count():
		if registry.is_hue_character(RunData.get_player_character(i)):
			return true
	return false


func is_hue_character(c) -> bool:
	return registry != null and registry.is_hue_character(c)


func start_wave(main) -> Node:
	run = Run.new()
	run.setup(self, main)
	main.add_child(run)
	return run


func end_wave(r) -> void:
	if run == r:
		run = null


func run_active() -> bool:
	return run != null


func is_hidden_colour(colour_id: String) -> bool:
	return run != null and colour_id != "" and colour_id == run.bg


func enemy_takes_colour(enemy) -> bool:
	var kind := "default"
	if "is_elite" in enemy:
		kind = "boss"
	elif enemy.is_loot:
		kind = "loot"
	elif enemy.get_charmed_by_player_index() >= 0:
		kind = "charmed"
	var rule: Dictionary = D.enemy_rule(kind)
	return not rule.empty() and rule.coloured


func colour(colour_id: String) -> Color:
	return D.colour_of(colour_id)


func tuning(id: String) -> float:
	return D.T(id)


func dead_layer_textures() -> Array:
	return registry.dead_layer_textures.values() if registry else []


# A player option from [options] in user://huepotato.cfg, defaulting to the options sheet.
func opt(id: String) -> bool:
	return bool(_options.get_value("options", id, D.Sheets.OPTIONS[id].default))


func play_letter(colour_id: String) -> void:
	if not opt("mum_letters"):
		return
	var row: Dictionary = D.colour_row(colour_id)
	audio.play_letter(row.letter_vo, row.letter_text_key, row.letter_lines)


# Mum's story letters (letters sheet) for the start of a wave, or 0 for the end of a won run.
func play_story_letters(wave: int) -> void:
	if not opt("mum_letters"):
		return
	var due := []
	for id in D.Sheets.LETTERS_ORDER:
		var row: Dictionary = D.Sheets.LETTERS[id]
		if row.wave == wave:
			due.append(row)
	due.sort_custom(self, "_by_order")
	if wave == 0:
		audio.stop_letter()
	for row in due:
		audio.play_letter(row.asset, row.text_key, row.lines)


static func _by_order(a: Dictionary, b: Dictionary) -> bool:
	return a.order < b.order




# ---- setup ----------------------------------------------------------------------------------

func _add_translations() -> void:
	var t := Translation.new()
	t.locale = "en"
	for id in D.Sheets.STRINGS_ORDER:
		t.add_message(id, D.Sheets.STRINGS[id].en)
	TranslationServer.add_translation(t)


func _add_input_actions() -> void:
	for id in D.Sheets.INPUT_ORDER:
		var row: Dictionary = D.Sheets.INPUT[id]
		if InputMap.has_action(id):
			continue
		InputMap.add_action(id, 0.5)
		for k in row.keys:
			var e := InputEventKey.new()
			e.scancode = INPUT_CONSTANTS[k]
			InputMap.action_add_event(id, e)
		for b in row.mouse_buttons:
			var e := InputEventMouseButton.new()
			e.button_index = INPUT_CONSTANTS[b]
			InputMap.action_add_event(id, e)
		for b in row.joy_buttons:
			var e := InputEventJoypadButton.new()
			e.button_index = INPUT_CONSTANTS[b]
			e.device = -1
			InputMap.action_add_event(id, e)
