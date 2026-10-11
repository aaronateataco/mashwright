extends Node2D

# Hue's obstacles in a Hue Potato wave (hazards sheet): laser gates and skull boulders. Each takes a
# colour Hue Potato has found and vanishes while the background is that colour, so the wheel gets
# you through them as it does in Hue. They hurt Hue Potato through Brotato's own damage: a hitbox on
# the enemy-attack layer, so dodge, armour and invincibility frames all apply. Enemies ignore them.

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")
const LaserGate = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_laser_gate.gd")
const Boulder = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_boulder.gd")
const HITBOX_SCENE = "res://overlap/hitbox.tscn"
const ENEMY_ATTACK_LAYER = 4   # Utils.ENEMIES_BIT: what the player's hurtbox listens to
const LAST_SECONDS_FREE = 3.0  # nothing new in the closing seconds of a wave

var hp = null
var run = null
var _next_s := {}   # hazard id -> seconds until the next one may appear
var _live := {}     # hazard id -> nodes still out


func _ready() -> void:
	for id in D.Sheets.HAZARDS_ORDER:
		# A short grace at the start of a wave, then the sheet's rhythm.
		_next_s[id] = D.Sheets.HAZARDS[id].interval_s * 0.5
		_live[id] = []


func _physics_process(delta: float) -> void:
	if not hp.opt("hue_hazards") or run.wave_lost():
		return
	var timer: Timer = run.main._wave_timer
	if is_instance_valid(timer) and not timer.is_stopped() and timer.time_left < LAST_SECONDS_FREE:
		return
	for id in D.Sheets.HAZARDS_ORDER:
		var row: Dictionary = D.Sheets.HAZARDS[id]
		if run.wave < row.first_wave:
			continue
		var still := []
		for node in _live[id]:
			if is_instance_valid(node):
				still.append(node)
		_live[id] = still
		_next_s[id] -= delta
		if _next_s[id] > 0.0 or still.size() >= count_for(row, run.wave):
			continue
		_next_s[id] = row.interval_s * rand_range(0.8, 1.2)
		spawn(id)


static func count_for(row: Dictionary, wave: int) -> int:
	var extra := int((wave - row.first_wave) / row.count_per_waves)
	return int(min(row.count_max, row.count_base + extra))


static func damage_for(row: Dictionary, wave: int) -> int:
	return int(round(row.damage_base + row.damage_per_wave * wave))


# Also used by the test probe to put a hazard out on demand.
func spawn(id: String) -> Node:
	var player = run.first_live_player()
	if player == null or run.owned.empty():
		return null
	var row: Dictionary = D.Sheets.HAZARDS[id]
	var node: Node2D = LaserGate.new() if id == "laser_gate" else Boulder.new()
	node.hp = hp
	node.run = run
	node.row = row
	node.colour_id = run.owned[randi() % run.owned.size()]
	node.damage = damage_for(row, run.wave)
	node.hazards = self
	if not node.place(player.global_position):
		node.free()
		return null
	run.main.add_child_below_node(run.main._tile_map, node)
	_live[id].append(node)
	if not hp.hazard_hinted.has(id):
		hp.hazard_hinted[id] = true
		hp.overlay.show_banner(_icon(id, row), tr(row.name_key), tr(row.hint_key))
	return node


func _icon(id: String, row: Dictionary) -> Texture:
	if id == "laser_gate" and not hp.registry.weapons.empty():
		return hp.registry.weapons.values()[0].icon
	return hp.textures.get(row.asset)


func make_hitbox(damage: int) -> Area2D:
	var hb: Area2D = load(HITBOX_SCENE).instance()
	hb.collision_layer = ENEMY_ATTACK_LAYER
	hb.collision_mask = 0
	hb.damage = damage
	hb.deals_damage = true
	hb.active = true
	hb.set_meta("hue_hazard", true)
	return hb


static func zone() -> Rect2:
	var lo: Vector2 = ZoneService.current_zone_min_position
	var hi: Vector2 = ZoneService.current_zone_max_position
	return Rect2(lo, hi - lo)


# Hue's laser cannon: black body over a colour rim, nozzle along +x.
func make_cannon(colour: Color, height: float) -> Node2D:
	var node := Node2D.new()
	var rim := Sprite.new()
	var body := Sprite.new()
	var ring: Dictionary = D.Sheets.WEAPONS[D.Sheets.WEAPONS_ORDER[0]]
	var body_tex: Texture = hp.textures.get(ring.emitter_asset)
	if body_tex != null:
		var fit: float = height / body_tex.get_height()
		body.texture = body_tex
		body.scale = Vector2(fit, fit)
		rim.texture = hp.registry.laser_rim_texture
		rim.scale = Vector2(fit, fit) * 1.2
	# Hue's image has the nozzle pointing down (+y); turn it to +x.
	body.rotation = -PI / 2.0
	rim.rotation = -PI / 2.0
	rim.self_modulate = colour
	rim.name = "Rim"
	node.add_child(rim)
	node.add_child(body)
	return node
