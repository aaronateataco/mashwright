extends Node

# Hue's colour on one Brotato enemy (a child node, so no Brotato script is replaced). The enemy gets
# an outline and tint in its colour. When the background is that colour it vanishes like objects in
# Hue: it fades to a ghost, its hitbox and hurtbox switch off, and it leaves the targetable physics
# layer so weapons, turrets and pets ignore it. Runs after the enemy's own _physics_process (child
# after parent), so Brotato's per-frame hitbox re-enable is undone in the same frame.
#
# Other mods may tint enemies or move them between layers too, so this multiplies onto whatever
# tint and opacity it found, restores exactly those, and only ever touches the enemies-layer bit.

const NAME = "HueTint"
const ENEMIES_BIT = 4

var hp = null
var enemy = null
var colour_id := ""
var hidden := false
var _alpha := 1.0
var _outline := Color(0, 0, 0, 0)
var _base_tint := Color.white
var _base_alpha := 1.0
var _applied_tint := Color.white
var _took_layer_bit := 0
var _took_mask_bit := 0
var _symbol: Sprite = null
var _charm_check_ms := 0


static func on(p_enemy):
	return p_enemy.get_node_or_null(NAME)


func assign(p_hp, p_colour_id: String) -> void:
	clear()
	hp = p_hp
	enemy = get_parent()
	colour_id = p_colour_id
	var c: Color = hp.colour(colour_id)
	_base_tint = enemy.sprite.self_modulate
	_base_alpha = enemy.modulate.a
	_applied_tint = _base_tint * Color.white.linear_interpolate(c, hp.tuning("enemy_tint_mix"))
	enemy.sprite.self_modulate = _applied_tint
	_outline = c
	if not enemy.has_outline(c):
		enemy.add_outline(c)
	if hp.opt("colourblind_symbols"):
		_symbol = Sprite.new()
		_symbol.texture = hp.symbol_textures.get(colour_id)
		_symbol.scale = Vector2.ONE * hp.tuning("symbol_scale")
		_symbol.position = Vector2(0, -70)
		_symbol.modulate = Color(1, 1, 1, 0.9)
		enemy.add_child(_symbol)


func clear() -> void:
	if enemy == null or colour_id == "":
		return
	if hidden:
		_set_hidden(false)
	if _outline.a > 0.0:
		enemy.remove_outline(_outline)
		_outline = Color(0, 0, 0, 0)
	# Put back what was there, unless another mod has set its own tint since.
	if enemy.sprite.self_modulate == _applied_tint:
		enemy.sprite.self_modulate = _base_tint
	if is_equal_approx(enemy.modulate.a, _base_alpha * _alpha):
		enemy.modulate.a = _base_alpha
	_alpha = 1.0
	if _symbol != null and is_instance_valid(_symbol):
		_symbol.queue_free()
	_symbol = null
	colour_id = ""


func _physics_process(delta: float) -> void:
	if colour_id == "" or enemy == null:
		return
	if enemy.dead or hp == null or not hp.run_active():
		clear()
		return
	var now := OS.get_ticks_msec()
	if now >= _charm_check_ms:
		_charm_check_ms = now + 400
		if enemy.get_charmed_by_player_index() >= 0:
			clear()
			return
	var hide: bool = hp.is_hidden_colour(colour_id)
	if hide != hidden:
		_set_hidden(hide)
	if hidden:
		enemy._hitbox.disable()
	var target: float = hp.tuning("hidden_enemy_alpha") if hidden else 1.0
	_alpha = move_toward(_alpha, target, hp.tuning("fade_speed") * delta)
	enemy.modulate.a = _base_alpha * _alpha


func _set_hidden(h: bool) -> void:
	hidden = h
	if h:
		_took_layer_bit = enemy.collision_layer & ENEMIES_BIT
		_took_mask_bit = enemy.collision_mask & ENEMIES_BIT
		enemy.collision_layer &= ~ENEMIES_BIT
		enemy.collision_mask &= ~ENEMIES_BIT
		enemy._hurtbox.disable()
		enemy._hitbox.disable()
	else:
		enemy.collision_layer |= _took_layer_bit
		enemy.collision_mask |= _took_mask_bit
		_took_layer_bit = 0
		_took_mask_bit = 0
		if not enemy.dead:
			enemy._hurtbox.enable()
