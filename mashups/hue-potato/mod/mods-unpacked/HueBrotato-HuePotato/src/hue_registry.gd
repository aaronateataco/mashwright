extends Reference

# Builds Brotato resources from the sheets plus the art read from Hue, and registers them:
# Hue Potato in the character list and the Hue items in the shop pool.

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")
const Art = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_art.gd")
# Not under res://mods-unpacked: Brotato's CrashReporter disables every mod on the next start if the
# engine log has an error naming mods-unpacked, and a saved Hue Potato run loaded without the mod
# (Hue uninstalled, mods off) would log one for each of these paths.
const RUNTIME_PATH = "res://huepotato_runtime/"
const FIST_DATA = "res://weapons/melee/fist/1/fist_data.tres"
const FIST_STATS = "res://weapons/melee/fist/1/fist_stats.tres"
const FIST_SCENE = "res://weapons/melee/fist/fist.tscn"

var character: Resource = null
var items := {}               # item row id -> ItemData
var weapons := {}             # weapons row id -> WeaponData (Laser Ring tiers)
var laser_beam_texture: ImageTexture = null  # Hue's beam strip, repeating
var laser_rim_texture: ImageTexture = null   # Hue's cannon mask, whitened
var crate_texture: ImageTexture = null       # Hue's crate, tree-sized
var layer_textures := {}      # layer id -> ImageTexture
var dead_layer_textures := {} # layer id -> ImageTexture
var _keep := []               # textures must stay alive: saves refer to them by resource path


func register(content, items_in_shop: bool) -> void:
	for layer_id in content.layer_images:
		layer_textures[layer_id] = _texture(content.layer_images[layer_id], "layer_" + layer_id)
	for layer_id in content.dead_layer_images:
		dead_layer_textures[layer_id] = _texture(content.dead_layer_images[layer_id], "dead_" + layer_id)

	_build_weapons(content)
	character = _build_character(content)
	ItemService.characters.append(character)

	for item_id in D.Sheets.ITEMS_ORDER:
		var item = _build_item(D.Sheets.ITEMS[item_id], content.item_icon_images[item_id])
		items[item_id] = item
		if items_in_shop:
			ItemService.add_mod_item(item)

	# Unlocks Hue Potato and gives it Brotato's per-zone difficulty records. At startup ProgressData
	# does this itself right after loading the save.
	if ProgressData.is_inside_tree():
		ProgressData.add_unlocked_by_default()


func is_hue_character(c) -> bool:
	return c != null and c.my_id == D.character().my_id


func item_row_for(my_id: String) -> String:
	for item_id in D.Sheets.ITEMS_ORDER:
		if D.Sheets.ITEMS[item_id].my_id == my_id:
			return item_id
	return ""


func _build_character(content) -> Resource:
	var row: Dictionary = D.character()
	var c = CharacterData.new()
	c.my_id = row.my_id
	c.name = row.name_key
	c.unlocked_by_default = row.unlocked_by_default
	c.can_be_looted = true
	c.tier = row.tier
	c.value = 1
	c.icon = _texture(content.portrait_image, "portrait")
	c.effects = _effects_for(row.effects)
	c.tracking_text = ""
	c.is_lockable = true
	c.max_nb = -1
	c.tags = []
	var appearances := [_appearance({"position": "OTHER", "depth": row.body_layer_depth}, _texture(content.body_image, "body"))]
	for layer_id in row.layers:
		appearances.append(_appearance(D.Sheets.LAYERS[layer_id], layer_textures[layer_id]))
	c.item_appearances = appearances
	c.wanted_tags = row.wanted_tags.duplicate()
	c.banned_item_groups = []
	c.banned_items = [] if row.banned_items == ["none"] else row.banned_items.duplicate()
	c.banned_upgrades = []
	var starting := [weapons[row.signature_weapon]]
	for path in row.starting_weapons:
		starting.append(load(path))
	c.starting_weapons = starting
	c.starting_items = []
	c._generate_hashes()
	return c


# Hue's Laser Ring: four tiers built from Brotato's fist (scene, stats and sounds) with the weapons
# sheet's numbers. Registered in ItemService.weapons so saves and upgrades find it, but never looted,
# so it stays Hue Potato's own weapon.
func _build_weapons(content) -> void:
	var fist_data: Resource = load(FIST_DATA)
	var fist_stats: Resource = load(FIST_STATS)
	var scene := _laser_ring_scene()
	var icon := _texture(content.weapon_icon_image, "icon_laser_ring")
	# Hue's beam strip, trimmed and repeating so the ring can ripple it along each beam.
	var ring: Dictionary = D.Sheets.WEAPONS[D.Sheets.WEAPONS_ORDER[0]]
	var strip: Image = content.images[ring.beam_asset]
	strip = strip.get_rect(strip.get_used_rect())
	laser_beam_texture = ImageTexture.new()
	laser_beam_texture.create_from_image(strip, Texture.FLAG_FILTER | Texture.FLAG_REPEAT)
	laser_beam_texture.take_over_path(RUNTIME_PATH + "laser_beam.png")
	# Hue's cannon mask is drawn in red; whiten it so it can take any colour.
	var rim: Image = content.images[ring.emitter_mask_asset].duplicate()
	Art._colourize(rim, Color.white)
	laser_rim_texture = _texture(rim, "laser_rim")
	# Hue's crate, sized like Brotato's tree, with a dark outline in Brotato's style; the run tints
	# each one a colour.
	var crate: Image = content.images["spr_crate"]
	crate = Art._scaled(crate, D.T("crate_height_px") / crate.get_height())
	crate_texture = _texture(Art._outlined(Art._padded(crate, 3), Color(0.08, 0.08, 0.1), 3), "crate")
	var order: Array = D.Sheets.WEAPONS_ORDER.duplicate()
	order.invert()
	for id in order:
		var row: Dictionary = D.Sheets.WEAPONS[id]
		var stats = fist_stats.duplicate()
		stats.damage = row.damage
		stats.cooldown = row.cooldown
		stats.crit_chance = row.crit_chance
		stats.crit_damage = row.crit_damage
		stats.knockback = row.knockback
		stats.max_range = row.ring_radius
		stats.scaling_stats = row.scaling_stats.duplicate(true)
		var w = fist_data.duplicate()
		w.my_id = row.my_id
		w.weapon_id = row.weapon_id
		w.name = row.name_key
		w.tier = row.tier
		w.value = row.value
		w.icon = icon
		w.scene = scene
		w.stats = stats
		w.sets = []
		w.effects = _text_effect(row.text_key)
		w.can_be_looted = false
		w.unlocked_by_default = true
		w.add_to_chars_as_starting = []
		w.upgrades_into = weapons[row.upgrades_into] if row.upgrades_into != "none" else null
		w._generate_hashes()
		weapons[id] = w
		ItemService.weapons.append(w)
	for id in weapons:
		if weapons[id].upgrades_into != null:
			weapons[id].upgrades_into.previous_upgrade = weapons[id]


func _laser_ring_scene() -> PackedScene:
	var base: PackedScene = load(FIST_SCENE)
	var node = base.instance()
	var mat = node.outline_shader_mat
	node.set_script(load(D.MOD_DIR + "src/hue_laser_ring.gd"))
	node.outline_shader_mat = mat
	var scene := PackedScene.new()
	var _err := scene.pack(node)
	node.free()
	scene.take_over_path(RUNTIME_PATH + "laser_ring.tscn")
	_keep.append(scene)
	return scene


func _text_effect(text_key: String) -> Array:
	var e = Effect.new()
	e.key = ""
	e.text_key = text_key
	e.value = 0
	e.custom_key = ""
	e.storage_method = Effect.StorageMethod.SUM
	e.effect_sign = Effect.Sign.NEUTRAL
	e.custom_args = []
	e._generate_hashes()
	return [e]


func _build_item(row: Dictionary, icon_image: Image) -> Resource:
	var it = ItemData.new()
	it.my_id = row.my_id
	it.name = row.name_key
	it.unlocked_by_default = true
	it.can_be_looted = true
	it.tier = row.tier
	it.value = row.value
	it.icon = _texture(icon_image, "icon_" + row.id)
	it.effects = _effects_for(row.effects)
	it.max_nb = row.max_nb
	it.tags = row.tags.duplicate()
	it.item_appearances = []
	it.is_lockable = true
	it._generate_hashes()
	return it


func _effects_for(effect_ids: Array) -> Array:
	var out := []
	for effect_id in effect_ids:
		var row: Dictionary = D.Sheets.EFFECTS[effect_id]
		var e = Effect.new()
		e.key = row.key if row.kind == "stat" else ""
		e.text_key = row.text_key if row.text_key != "none" else ""
		e.value = row.value
		e.custom_key = ""
		e.storage_method = Effect.StorageMethod.SUM
		e.effect_sign = Effect.Sign[row.effect_sign]
		e.custom_args = []
		e._generate_hashes()
		out.append(e)
	return out


func _appearance(layer: Dictionary, texture: Texture) -> Resource:
	var a = ItemAppearanceData.new()
	a.sprite = texture
	a.position = ItemAppearanceData.Position[layer.position]
	a.display_priority = ItemAppearanceData.Priority.VERY_HIGH
	a.depth = layer.depth
	a.is_character_appearance = true
	return a


# Runtime textures get a stable res:// path: Brotato saves refer to textures by path, and
# load() of that path then returns this cached texture.
func _texture(img: Image, name: String) -> ImageTexture:
	var t := ImageTexture.new()
	t.create_from_image(img, Texture.FLAG_FILTER)
	t.take_over_path(RUNTIME_PATH + name + ".png")
	_keep.append(t)
	return t
