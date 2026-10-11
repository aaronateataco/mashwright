extends Node2D

# One of Hue's laser gates: two laser cannons on opposite edges of the arena with Hue's beam between
# them, a line across the whole arena. It flickers faintly while it warms up, then burns for the
# sheet's active_s. Touching the live beam hurts Hue Potato, unless the background is the beam's
# colour: then it has vanished, as in Hue, and can be walked through.

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")
const GLOW_ALPHA = 0.3
const GLOW_WIDTH = 2.4
const FADE_S = 0.35

var hp = null
var run = null
var hazards = null
var row := {}
var colour_id := ""
var damage := 1

var _length := 0.0
var _t := 0.0
var _scroll := 0.0
var _beam: Sprite = null
var _glow: Sprite = null
var _hitbox: Area2D = null
var _cannons := []
var _shown := 0.0        # 0..1 how much of the gate exists (fades in and out)
var _alpha := 0.0
var _started := false


# Picks a line across the arena away from the player. Vertical most of the time, like the laser
# walls in Hue; sometimes horizontal.
func place(player_pos: Vector2) -> bool:
	var z: Rect2 = hazards.zone()
	var margin := D.T("hazard_edge_margin_px")
	var clear := D.T("hazard_player_clearance_px")
	var vertical := randf() < 0.7
	for _attempt in 10:
		if vertical:
			var x := rand_range(z.position.x + 120, z.end.x - 120)
			if abs(x - player_pos.x) < clear:
				continue
			_set_line(Vector2(x, z.position.y + margin), Vector2(x, z.end.y - margin))
			return true
		var y := rand_range(z.position.y + 120, z.end.y - 120)
		if abs(y - player_pos.y) < clear:
			continue
		_set_line(Vector2(z.position.x + margin, y), Vector2(z.end.x - margin, y))
		return true
	return false


func _set_line(from: Vector2, to: Vector2) -> void:
	global_position = (from + to) / 2.0
	rotation = (to - from).angle()
	_length = from.distance_to(to)


func _ready() -> void:
	var c := D.colour_of(colour_id)
	var tex: Texture = hp.registry.laser_beam_texture
	var s: float = float(row.size_px) / tex.get_height()
	_glow = _beam_sprite(tex, Color(c.r, c.g, c.b, 0.0), Vector2(s, s * GLOW_WIDTH))
	_beam = _beam_sprite(tex, Color(c.r, c.g, c.b, 0.0), Vector2(s, s))
	_hitbox = hazards.make_hitbox(damage)
	add_child(_hitbox)
	var shape := RectangleShape2D.new()
	shape.extents = Vector2(_length / 2.0, row.size_px / 2.0)
	var collision: CollisionShape2D = _hitbox.get_node("Collision")
	collision.shape = shape
	collision.disabled = true
	var _e := _hitbox.connect("hit_something", self, "_on_hit")
	for end in [-1, 1]:
		var cannon: Node2D = hazards.make_cannon(c, 44.0)
		cannon.position = Vector2(end * _length / 2.0, 0)
		# Both cannons aim along the beam, towards each other.
		cannon.rotation = 0.0 if end < 0 else PI
		cannon.modulate.a = 0.0
		add_child(cannon)
		_cannons.append(cannon)


func _beam_sprite(tex: Texture, tint: Color, scale_by: Vector2) -> Sprite:
	var spr := Sprite.new()
	spr.texture = tex
	spr.region_enabled = true
	spr.region_rect = Rect2(0, 0, _length / scale_by.x, tex.get_height())
	spr.scale = scale_by
	spr.modulate = tint
	add_child(spr)
	return spr


func _physics_process(delta: float) -> void:
	_t += delta
	var warn: float = row.warn_s
	var active: float = row.active_s
	var live: bool = _t >= warn and _t < warn + active
	if live and not _started:
		_started = true
		hp.audio.play_sound(row.start_sound)
	var target_shown := 0.0 if _t >= warn + active else 1.0
	_shown = move_toward(_shown, target_shown, delta / FADE_S)
	if _t >= warn + active and _shown <= 0.0:
		queue_free()
		return
	var hidden: bool = hp.is_hidden_colour(colour_id)
	var a := 1.0
	if not live:
		# Warming up: a faint flickering line shows where the gate will be.
		a = D.T("hazard_warn_alpha") * (0.6 + 0.4 * sin(_t * 24.0))
	if hidden:
		a = min(a, D.T("hidden_enemy_alpha"))
	_alpha = move_toward(_alpha, a * _shown, 6.0 * delta)
	_scroll += D.T("laser_scroll_speed") * delta
	var tex_h: float = _beam.texture.get_height()
	var s: float = float(row.size_px) / tex_h
	var region := Rect2(_scroll / s, 0, _length / s, tex_h)
	_beam.region_rect = region
	_glow.region_rect = region
	_beam.modulate.a = _alpha
	_glow.modulate.a = _alpha * GLOW_ALPHA
	for cannon in _cannons:
		cannon.modulate.a = _shown
		cannon.get_node("Rim").modulate.a = D.T("hidden_enemy_alpha") if hidden else 1.0
	var collision: CollisionShape2D = _hitbox.get_node("Collision")
	var should_hurt: bool = live and not hidden and _shown >= 1.0
	if collision.disabled == should_hurt:
		collision.set_deferred("disabled", not should_hurt)


func _on_hit(_thing, _damage) -> void:
	hp.audio.play_sound(row.hit_sound)
