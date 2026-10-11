extends Reference

# Read-only access to the generated sheet rows (generated/sheets.gd). Everything the systems use
# comes from here, so the sheets stay the single source of truth.

const Sheets = preload("res://mods-unpacked/HueBrotato-HuePotato/generated/sheets.gd")

const MOD_ID = "HueBrotato-HuePotato"
const MOD_DIR = "res://mods-unpacked/HueBrotato-HuePotato/"
const CHARACTER_ROW = "hue_potato"
const GREY = "grey"


static func T(id: String) -> float:
	return float(Sheets.TUNING[id].value)


static func asset(id: String) -> Dictionary:
	return Sheets.HUE_ASSETS[id]


static func colour_row(id: String) -> Dictionary:
	return Sheets.COLOURS[id]


static func colour_of(id: String) -> Color:
	if id == GREY or not Sheets.COLOURS.has(id):
		var g = T("floor_grey")
		return Color(g, g, g)
	var rgb: Array = Sheets.COLOURS[id].rgb
	return Color8(rgb[0], rgb[1], rgb[2])


# Colour ids in wheel order (Hue's HueColorNames order).
static func wheel_order() -> Array:
	var ids := []
	ids.resize(Sheets.COLOURS_ORDER.size())
	for id in Sheets.COLOURS_ORDER:
		ids[Sheets.COLOURS[id].wheel_index] = id
	return ids


# Colours the player owns at the start of a wave (fragments from earlier waves are collected).
static func colours_owned_at_wave_start(wave: int) -> Array:
	var owned := []
	for id in wheel_order():
		var unlock: int = Sheets.COLOURS[id].unlock_wave
		if unlock == 0 or unlock < wave:
			owned.append(id)
	return owned


# The colour whose fragment appears during this wave, or "".
static func fragment_for_wave(wave: int) -> String:
	for id in Sheets.COLOURS_ORDER:
		if Sheets.COLOURS[id].unlock_wave == wave:
			return id
	return ""


static func region_for_wave(wave: int) -> Dictionary:
	var last := 0
	for id in Sheets.REGIONS_ORDER:
		last = max(last, Sheets.REGIONS[id].wave_to)
	var w := wave
	if w > last and T("endless_cycle") > 0.5:
		w = ((w - 1) % last) + 1
	for id in Sheets.REGIONS_ORDER:
		var r: Dictionary = Sheets.REGIONS[id]
		if w >= r.wave_from and w <= r.wave_to:
			return r
	return Sheets.REGIONS[Sheets.REGIONS_ORDER[Sheets.REGIONS_ORDER.size() - 1]]


static func character() -> Dictionary:
	return Sheets.CHARACTER[CHARACTER_ROW]


static func synergy_for_item(item_row_id: String) -> Dictionary:
	var syn_id: String = Sheets.ITEMS[item_row_id].synergy
	if syn_id == "none":
		return {}
	return Sheets.SYNERGIES[syn_id]


static func enemy_rule(match_kind: String) -> Dictionary:
	for id in Sheets.ENEMY_RULES_ORDER:
		if Sheets.ENEMY_RULES[id].match == match_kind:
			return Sheets.ENEMY_RULES[id]
	return {}
