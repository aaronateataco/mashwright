extends Node2D

# A colour fragment lying in the arena: Hue's colourblind disc in the fragment's colour with Hue's
# symbol on it, over Hue's soft glow.

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")

var colour_id := ""
var symbol: Texture = null
var disc: Texture = null
var glow: Texture = null
var _t := 0.0


func _process(delta: float) -> void:
	_t += delta
	update()


func _draw() -> void:
	var size := D.T("fragment_size_px")
	var c := D.colour_of(colour_id)
	var bob := Vector2(0, sin(_t * 3.0) * 4.0)
	var pulse := 0.75 + 0.25 * sin(_t * 4.0)
	if glow:
		var g := size * 2.6 * pulse
		draw_texture_rect(glow, Rect2(bob - Vector2(g, g) / 2.0, Vector2(g, g)), false, Color(c.r, c.g, c.b, 0.7))
	if disc:
		draw_texture_rect(disc, Rect2(bob - Vector2(size, size) / 2.0, Vector2(size, size)), false, c)
	else:
		draw_circle(bob, size / 2.0, c)
	if symbol:
		var s := size * 0.6
		var sz := symbol.get_size() * (s / max(symbol.get_width(), symbol.get_height()))
		draw_texture_rect(symbol, Rect2(bob - sz / 2.0, sz), false, Color.white)
