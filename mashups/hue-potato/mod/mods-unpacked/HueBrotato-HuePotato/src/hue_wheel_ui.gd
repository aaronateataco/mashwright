extends Control

# Draws Hue's colour wheel: a small one always in the corner, and the big one while it is held.
# Slices follow Hue's colour order; owned colours carry Hue's own colourblind symbols, colours not
# found yet are grey, and the centre is grey (hide nothing).

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")

var run = null            # the HueRun that owns this wheel
var symbols := {}         # colour id -> Texture (Hue's symbol)
var symbol_bg: Texture = null
var hint := ""
var _font: Font = null
var _open_amount := 0.0   # 0 closed .. 1 open (animated in real time)
var _last_ms := 0


func _ready() -> void:
	anchor_right = 1.0
	anchor_bottom = 1.0
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_font = load("res://resources/fonts/actual/base/font_22.tres")
	_last_ms = OS.get_ticks_msec()


func _process(_delta: float) -> void:
	var now := OS.get_ticks_msec()
	var dt := (now - _last_ms) / 1000.0
	_last_ms = now
	var target: float = 1.0 if run.wheel_open else 0.0
	_open_amount = move_toward(_open_amount, target, dt * 7.0)
	update()


func big_center() -> Vector2:
	return rect_size / 2.0


func slice_at(screen_pos: Vector2) -> String:
	var v := screen_pos - big_center()
	if v.length() < D.T("wheel_inner_px"):
		return D.GREY
	return slice_for_direction(v)


static func slice_for_direction(v: Vector2) -> String:
	var order: Array = D.wheel_order()
	var n := order.size()
	var a: float = fposmod(v.angle() + PI / 2.0 + PI / n, TAU)
	return order[int(a / (TAU / n)) % n]


func _draw() -> void:
	var r_small := D.T("hud_wheel_radius_px")
	var margin := D.T("hud_margin_px")
	var small_c := Vector2(margin + r_small, rect_size.y - margin - r_small)
	_draw_wheel(small_c, r_small, r_small * 0.45, false)
	if hint != "" and _font:
		draw_string(_font, small_c + Vector2(r_small + 12, 6), hint, Color(1, 1, 1, 0.85))
	if _open_amount > 0.01:
		var e := _ease(_open_amount)
		draw_rect(Rect2(Vector2.ZERO, rect_size), Color(0, 0, 0, 0.25 * e))
		_draw_wheel(big_center(), D.T("wheel_radius_px") * e, D.T("wheel_inner_px") * e, true)
		if _font and e > 0.9:
			var key: String = "HUE_COLOUR_GREY" if run.wheel_hover == D.GREY else D.colour_row(run.wheel_hover).name_key
			var label := tr(key)
			var w := _font.get_string_size(label).x
			draw_string(_font, big_center() + Vector2(-w / 2.0, D.T("wheel_radius_px") * 1.15 + 30), label, Color.white)


func _draw_wheel(c: Vector2, r_out: float, r_in: float, big: bool) -> void:
	var order: Array = D.wheel_order()
	var n := order.size()
	var span := TAU / n
	for i in n:
		var id: String = order[i]
		var owned: bool = run.owned.has(id)
		var col: Color = D.colour_of(id) if owned else Color(0.32, 0.32, 0.34)
		var a_mid: float = -PI / 2.0 + i * span
		var grow := 1.0
		if big and id == run.wheel_hover and owned:
			grow = 1.15
		elif id == run.bg:
			grow = 1.08
		var ro := r_out * grow
		_segment(c, r_in, ro, a_mid - span / 2.0 + 0.03, a_mid + span / 2.0 - 0.03, col)
		if id == run.bg:
			_segment_outline(c, r_in, ro, a_mid - span / 2.0 + 0.03, a_mid + span / 2.0 - 0.03, Color.white, 3.0 if big else 2.0)
		if big and owned and symbols.has(id):
			var tex: Texture = symbols[id]
			var at := c + Vector2(cos(a_mid), sin(a_mid)) * (r_in + ro) / 2.0
			var s := (ro - r_in) * 0.62
			var sz := tex.get_size() * (s / max(tex.get_width(), tex.get_height()))
			draw_texture_rect(tex, Rect2(at - sz / 2.0, sz), false, Color(1, 1, 1, 0.95))
	var centre_col := D.colour_of(D.GREY)
	draw_circle(c, r_in * 0.9, Color(0.1, 0.1, 0.12, 0.9))
	draw_circle(c, r_in * 0.72, centre_col if run.bg == D.GREY or (big and run.wheel_hover == D.GREY) else D.colour_of(run.bg))
	if big and run.wheel_hover == D.GREY:
		draw_arc(c, r_in * 0.8, 0, TAU, 32, Color.white, 2.0)


func _segment(c: Vector2, r_in: float, r_out: float, a0: float, a1: float, col: Color) -> void:
	var pts := PoolVector2Array()
	var steps := 10
	for k in steps + 1:
		var a: float = lerp(a0, a1, float(k) / steps)
		pts.append(c + Vector2(cos(a), sin(a)) * r_out)
	for k in range(steps, -1, -1):
		var a: float = lerp(a0, a1, float(k) / steps)
		pts.append(c + Vector2(cos(a), sin(a)) * r_in)
	draw_colored_polygon(pts, col)


func _segment_outline(c: Vector2, r_in: float, r_out: float, a0: float, a1: float, col: Color, w: float) -> void:
	var pts := PoolVector2Array()
	var steps := 10
	for k in steps + 1:
		var a: float = lerp(a0, a1, float(k) / steps)
		pts.append(c + Vector2(cos(a), sin(a)) * r_out)
	for k in range(steps, -1, -1):
		var a: float = lerp(a0, a1, float(k) / steps)
		pts.append(c + Vector2(cos(a), sin(a)) * r_in)
	pts.append(pts[0])
	draw_polyline(pts, col, w, true)


static func _ease(t: float) -> float:
	return 1.0 - pow(1.0 - t, 3.0)
