extends Node

# Hue's crate in place of one of Brotato's trees (a child node of the tree, so no Brotato script is
# replaced). The crate takes a colour Hue Potato has found; with the background in that colour it
# vanishes like everything in Hue: it fades, can't be hit and leaves the layer weapons aim at. It
# breaks with Hue's crate sound. The tree's own picture, tint and layer are put back if the crate
# is cleared.

const NAME = "HueCrate"
const NEUTRAL_BIT = 1

var hp = null
var tree = null
var colour_id := ""
var hidden := false
var _alpha := 1.0
var _base_texture: Texture = null
var _base_tint := Color.white
var _base_alpha := 1.0
var _took_layer_bit := 0


static func on(p_tree):
	return p_tree.get_node_or_null(NAME)


func assign(p_hp, p_colour_id: String, texture: Texture) -> void:
	clear()
	hp = p_hp
	tree = get_parent()
	colour_id = p_colour_id
	_base_texture = tree.sprite.texture
	_base_tint = tree.sprite.self_modulate
	_base_alpha = tree.modulate.a
	tree.sprite.texture = texture
	var c: Color = hp.colour(colour_id)
	tree.sprite.self_modulate = Color(c.r * 1.1, c.g * 1.1, c.b * 1.1)
	if not tree.is_connected("died", self, "_on_died"):
		var _e = tree.connect("died", self, "_on_died")


func clear() -> void:
	if tree == null or colour_id == "":
		return
	if hidden:
		_set_hidden(false)
	tree.sprite.texture = _base_texture
	tree.sprite.self_modulate = _base_tint
	tree.modulate.a = _base_alpha
	_alpha = 1.0
	colour_id = ""


func _physics_process(delta: float) -> void:
	if colour_id == "" or tree == null or tree.dead or hp == null:
		return
	var hide: bool = hp.is_hidden_colour(colour_id)
	if hide != hidden:
		_set_hidden(hide)
	var target: float = hp.tuning("hidden_enemy_alpha") if hidden else 1.0
	_alpha = move_toward(_alpha, target, hp.tuning("fade_speed") * delta)
	tree.modulate.a = _base_alpha * _alpha


func _set_hidden(h: bool) -> void:
	hidden = h
	if h:
		_took_layer_bit = tree.collision_layer & NEUTRAL_BIT
		tree.collision_layer &= ~NEUTRAL_BIT
		tree._hurtbox.disable()
	else:
		tree.collision_layer |= _took_layer_bit
		_took_layer_bit = 0
		if not tree.dead:
			tree._hurtbox.enable()


func _on_died(_unit, _args) -> void:
	if colour_id != "" and hp != null:
		hp.audio.play_sound("sfx_crate_break")
