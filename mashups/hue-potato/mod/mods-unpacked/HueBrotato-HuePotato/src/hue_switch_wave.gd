extends Node2D

# A ring of the new background colour sweeping out from Hue Potato, after Hue's own radial colour
# reveal. Drawn just above the arena floor (below enemies) and timed in real seconds, so it plays
# at full speed even while the wheel's slow-motion eases off.

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")

var colour := Color.white
var _start_ms := 0


func _ready() -> void:
	_start_ms = OS.get_ticks_msec()


func _process(_delta: float) -> void:
	var t: float = (OS.get_ticks_msec() - _start_ms) / 1000.0 / max(0.05, D.T("switch_wave_s"))
	if t >= 1.0:
		queue_free()
		return
	update()


func _draw() -> void:
	var t: float = clamp((OS.get_ticks_msec() - _start_ms) / 1000.0 / max(0.05, D.T("switch_wave_s")), 0.0, 1.0)
	var eased: float = 1.0 - pow(1.0 - t, 2.0)
	var r: float = D.T("switch_wave_radius_px") * eased
	var a: float = D.T("switch_wave_alpha") * (1.0 - t)
	draw_circle(Vector2.ZERO, r, Color(colour.r, colour.g, colour.b, a * 0.25))
	draw_arc(Vector2.ZERO, r, 0.0, TAU, 96, Color(colour.r, colour.g, colour.b, a), 26.0 * (1.0 - t) + 4.0, true)
