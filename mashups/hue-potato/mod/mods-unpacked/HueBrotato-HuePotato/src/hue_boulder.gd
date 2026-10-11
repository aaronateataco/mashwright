extends Node2D

# One of Hue's skull boulders, rolling straight across the arena towards where Hue Potato was when
# it set off. Its path shows faintly first; then it rolls until it leaves the arena. It hurts Hue
# Potato on contact, unless the background is its colour: then it has vanished, as in Hue, and
# rolls straight through.

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")
const FADE_S = 0.3
const AIM_JITTER_PX = 90.0

var hp = null
var run = null
var hazards = null
var row := {}
var colour_id := ""
var damage := 1

var _dir := Vector2.RIGHT
var _start := Vector2.ZERO
var _path_len := 0.0
var _t := 0.0
var _travelled := 0.0
var _alpha := 0.0
var _rolling := false
var _skull: Sprite = null
var _path: Line2D = null
var _hitbox: Area2D = null


# Starts on a random edge of the arena, aimed at (near) Hue Potato.
func place(player_pos: Vector2) -> bool:
	var z: Rect2 = hazards.zone()
	var r: float = row.size_px / 2.0
	var clear := D.T("hazard_player_clearance_px")
	for _attempt in 10:
		var start := Vector2.ZERO
		match randi() % 4:
			0: start = Vector2(z.position.x - r, rand_range(z.position.y, z.end.y))
			1: start = Vector2(z.end.x + r, rand_range(z.position.y, z.end.y))
			2: start = Vector2(rand_range(z.position.x, z.end.x), z.position.y - r)
			_: start = Vector2(rand_range(z.position.x, z.end.x), z.end.y + r)
		if start.distance_to(player_pos) < clear * 2.0:
			continue
		var aim := player_pos + Vector2(rand_range(-1, 1), rand_range(-1, 1)) * AIM_JITTER_PX
		_dir = (aim - start).normalized()
		_start = start
		_path_len = _exit_distance(z.grow(r * 2.0), start, _dir)
		global_position = start
		return true
	return false


# How far from `from` along `dir` until the boulder is out of `rect`.
static func _exit_distance(rect: Rect2, from: Vector2, dir: Vector2) -> float:
	var best := 1e9
	if dir.x > 0.001:
		best = min(best, (rect.end.x - from.x) / dir.x)
	elif dir.x < -0.001:
		best = min(best, (rect.position.x - from.x) / dir.x)
	if dir.y > 0.001:
		best = min(best, (rect.end.y - from.y) / dir.y)
	elif dir.y < -0.001:
		best = min(best, (rect.position.y - from.y) / dir.y)
	return best


func _ready() -> void:
	var c := D.colour_of(colour_id)
	var r: float = row.size_px / 2.0
	_path = Line2D.new()
	_path.width = row.size_px * 0.7
	_path.default_color = Color(c.r, c.g, c.b, 0.0)
	_path.points = PoolVector2Array([Vector2.ZERO, _dir * _path_len])
	_path.set_as_toplevel(true)
	_path.global_position = _start
	add_child(_path)
	_skull = Sprite.new()
	var tex: Texture = hp.textures.get(row.asset)
	if tex != null:
		_skull.texture = tex
		_skull.scale = Vector2.ONE * (float(row.size_px) / max(tex.get_width(), tex.get_height()))
	_skull.self_modulate = Color(c.r * 1.15, c.g * 1.15, c.b * 1.15)
	_skull.modulate.a = 0.0
	add_child(_skull)
	_hitbox = hazards.make_hitbox(damage)
	add_child(_hitbox)
	var shape := CircleShape2D.new()
	shape.radius = r * 0.8
	var collision: CollisionShape2D = _hitbox.get_node("Collision")
	collision.shape = shape
	collision.disabled = true
	var _e := _hitbox.connect("hit_something", self, "_on_hit")


func _physics_process(delta: float) -> void:
	_t += delta
	var hidden: bool = hp.is_hidden_colour(colour_id)
	if not _rolling and _t >= row.warn_s:
		_rolling = true
		hp.audio.play_sound(row.start_sound)
	if _rolling:
		var step: float = row.speed_px_s * delta
		_travelled += step
		global_position += _dir * step
		# Rolls: turn by the distance over the radius.
		_skull.rotation += step / (row.size_px / 2.0) * sign(_dir.x if abs(_dir.x) > 0.2 else 1.0)
		if _travelled >= _path_len:
			queue_free()
			return
	var warn_a := D.T("hazard_warn_alpha") * (0.6 + 0.4 * sin(_t * 10.0))
	var path_a: float = warn_a if not _rolling else max(0.0, _path.default_color.a - delta / FADE_S)
	_path.default_color.a = path_a * (0.4 if hidden else 1.0)
	var target := 1.0
	if not _rolling:
		target = min(1.0, _t / FADE_S) * 0.6
	if hidden:
		target = min(target, D.T("hidden_enemy_alpha"))
	_alpha = move_toward(_alpha, target, 6.0 * delta)
	_skull.modulate.a = _alpha
	var collision: CollisionShape2D = _hitbox.get_node("Collision")
	var should_hurt: bool = _rolling and not hidden
	if collision.disabled == should_hurt:
		collision.set_deferred("disabled", not should_hurt)


func _on_hit(_thing, _damage) -> void:
	hp.audio.play_sound(row.hit_sound)
