extends "res://weapons/melee/melee_weapon.gd"

# Hue's Laser Ring: Hue's laser cannons (read from the player's copy of Hue) orbit Hue Potato, each
# firing Hue's laser beam at the next, so the beams make a spinning fence. The beams take the
# colours found in turn round the ring. A beam the colour of the background vanishes and leaves a
# gap, as lasers do in Hue.
#
# Built on Brotato's fist weapon scene: Brotato computes this weapon's damage, crits, knockback and
# attack speed exactly as for any melee weapon, and each beam carries a copy of the weapon's hitbox
# with those numbers. A beam only hurts an enemy when it enters it, so each beam's hitbox pulses on
# the weapon's (attack-speed-scaled) cooldown to keep zapping enemies it is touching.

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")
const DEFAULT_COLOURS = ["aqua", "purple"]
const GLOW_ALPHA = 0.3
const GLOW_WIDTH = 2.2
const RIM_SCALE = 1.2

var _row := {}
var _hp = null
var _colours_built := []
var _emitters := []    # each: {"node": Node2D, "rim": Sprite}
var _beams := []       # each: {"node": Node2D, "core": Sprite, "glow": Sprite, "hitbox": Area2D, "shape": RectangleShape2D, "colour": String, "alpha": float}
var _angle := 0.0
var _breathe := 0.0
var _scroll := 0.0
var _pulse_left := 0.0
var _pulsing := false


func _ready() -> void:
	_hp = Engine.get_meta("hue_potato") if Engine.has_meta("hue_potato") else null
	for id in D.Sheets.WEAPONS_ORDER:
		if D.Sheets.WEAPONS[id].tier == tier:
			_row = D.Sheets.WEAPONS[id]
	if _row.empty():
		_row = D.Sheets.WEAPONS[D.Sheets.WEAPONS_ORDER[0]]
	# The fist sprite stays (Brotato's outline/highlight code expects it) but is invisible: the
	# lasers are what you see.
	sprite.self_modulate.a = 0.0


# No punch: the lasers do the hitting.
func should_shoot() -> bool:
	return false


func init_stats(at_wave_begin: bool = true) -> void:
	.init_stats(at_wave_begin)
	for beam in _beams:
		_copy_hitbox(beam.hitbox)


# Runs before Brotato's weapon _physics_process (derived levels first in Godot 3).
func _physics_process(delta: float) -> void:
	if not is_instance_valid(_parent):
		return
	var colours := _colours()
	if colours != _colours_built or _emitters.empty():
		_rebuild(colours)
	_angle += _row.spin_speed * delta
	_breathe += D.T("laser_breathe_speed") * delta
	_scroll += D.T("laser_scroll_speed") * delta
	# The fence closes in on the potato and opens out again, so it sweeps enemies at every
	# distance, including ones pressed right against Hue Potato.
	var depth := D.T("laser_breathe_depth")
	var radius: float = _row.ring_radius * (1.0 - depth * (0.5 + 0.5 * sin(_breathe)))
	_pulse(delta)
	var centre: Vector2 = _parent.global_position
	var n := _emitters.size()
	var corners := []
	for i in n:
		var a: float = _angle + TAU * i / n
		corners.append(centre + Vector2(cos(a), sin(a)) * radius)
	for i in n:
		var from: Vector2 = corners[i]
		var to: Vector2 = corners[(i + 1) % n]
		var emitter: Dictionary = _emitters[i]
		var beam: Dictionary = _beams[i]
		# Each cannon points its nozzle (down in Hue's image) at the next cannon.
		emitter.node.global_position = from
		emitter.node.rotation = (to - from).angle() - PI / 2.0
		_place_beam(beam, from, to, centre, delta)
		emitter.rim.modulate.a = beam.alpha


func _place_beam(beam: Dictionary, from: Vector2, to: Vector2, centre: Vector2, delta: float) -> void:
	var length := from.distance_to(to)
	var mid := (from + to) / 2.0
	beam.node.global_position = mid
	beam.node.rotation = (to - from).angle()
	var tex: Texture = beam.core.texture
	if tex != null:
		var s: float = float(_row.beam_width) / tex.get_height()
		var region := Rect2(_scroll / s, 0, length / s, tex.get_height())
		beam.core.region_rect = region
		beam.glow.region_rect = region
	beam.shape.extents = Vector2(length / 2.0, _row.beam_width / 2.0)
	var hidden: bool = _hp != null and _hp.is_hidden_colour(beam.colour)
	var target: float = _hp.tuning("hidden_enemy_alpha") if (hidden and _hp != null) else 1.0
	beam.alpha = move_toward(beam.alpha, target, 9.0 * delta)
	beam.core.modulate.a = beam.alpha
	beam.glow.modulate.a = beam.alpha * GLOW_ALPHA
	var out := mid - centre
	beam.hitbox.set_knockback(out.normalized() if out.length() > 0.1 else Vector2.RIGHT, current_stats.knockback, current_stats.knockback_piercing)
	if hidden or _pulsing:
		beam.hitbox.disable()
	else:
		beam.hitbox.enable()


# Turn every beam's hitbox off for one physics frame each cooldown, so enemies a beam is still
# touching are zapped again when it comes back on.
func _pulse(delta: float) -> void:
	if _pulsing:
		_pulsing = false
		return
	_pulse_left -= 60.0 * delta
	if _pulse_left <= 0.0:
		_pulse_left = max(4.0, float(current_stats.cooldown))
		_pulsing = true


func _colours() -> Array:
	if _hp != null and _hp.run != null and not _hp.run.owned.empty():
		return _hp.run.owned
	return DEFAULT_COLOURS


func _rebuild(colours: Array) -> void:
	for emitter in _emitters:
		emitter.node.queue_free()
	for beam in _beams:
		beam.node.queue_free()
	_emitters.clear()
	_beams.clear()
	_colours_built = colours.duplicate()
	var n: int = _row.emitters
	# Beams first so the cannons draw over the beam ends.
	for i in n:
		_beams.append(_make_beam(colours[i % colours.size()]))
	for i in n:
		_emitters.append(_make_emitter(_beams[i].colour))


func _make_beam(colour_id: String) -> Dictionary:
	var node := Node2D.new()
	node.set_as_toplevel(true)
	add_child(node)
	var c := D.colour_of(colour_id)
	var tex: Texture = _hp.registry.laser_beam_texture if (_hp != null and _hp.registry != null) else null
	var s: float = float(_row.beam_width) / tex.get_height() if tex != null else 1.0
	var glow := _beam_sprite(tex, Color(c.r, c.g, c.b, GLOW_ALPHA), Vector2(s, s * GLOW_WIDTH))
	node.add_child(glow)
	var core := _beam_sprite(tex, c, Vector2(s, s))
	node.add_child(core)
	var hb: Area2D = _hitbox.duplicate()
	node.add_child(hb)
	hb.position = Vector2.ZERO
	hb.rotation = 0.0
	var shape := RectangleShape2D.new()
	var collision: CollisionShape2D = hb.get_node("Collision")
	collision.shape = shape
	collision.position = Vector2.ZERO
	collision.rotation = 0.0
	_copy_hitbox(hb)
	return {"node": node, "core": core, "glow": glow, "hitbox": hb, "shape": shape, "colour": colour_id, "alpha": 1.0}


func _beam_sprite(tex: Texture, tint: Color, scale_by: Vector2) -> Sprite:
	var spr := Sprite.new()
	spr.texture = tex
	spr.region_enabled = true
	spr.scale = scale_by
	spr.modulate = tint
	return spr


# Hue's laser cannon: the black body over its colour rim (Hue's mask image) in the beam's colour.
func _make_emitter(colour_id: String) -> Dictionary:
	var node := Node2D.new()
	node.set_as_toplevel(true)
	add_child(node)
	var rim := Sprite.new()
	var body := Sprite.new()
	if _hp != null and _hp.textures.has(_row.emitter_asset):
		var body_tex: Texture = _hp.textures[_row.emitter_asset]
		var fit: float = float(_row.emitter_size) / body_tex.get_height()
		body.texture = body_tex
		body.scale = Vector2(fit, fit)
		rim.texture = _hp.registry.laser_rim_texture
		# Hue's mask is only a few pixels bigger than the cannon; widen it so the colour reads at
		# Brotato's scale.
		rim.scale = Vector2(fit, fit) * RIM_SCALE
	rim.self_modulate = D.colour_of(colour_id)
	node.add_child(rim)
	node.add_child(body)
	return {"node": node, "rim": rim}


func _copy_hitbox(hb: Area2D) -> void:
	hb.set_damage(_hitbox.damage, Hitbox.HitboxArgs.new().set_from_weapon_stats(current_stats))
	hb.effect_scale = _hitbox.effect_scale
	hb.speed_percent_modifier = _hitbox.speed_percent_modifier
	hb.effects = _hitbox.effects
	hb.projectiles_on_hit = _hitbox.projectiles_on_hit
	hb.damage_tracking_key_hash = _hitbox.damage_tracking_key_hash
	hb.from = self
	hb.active = true
	hb.deals_damage = true
