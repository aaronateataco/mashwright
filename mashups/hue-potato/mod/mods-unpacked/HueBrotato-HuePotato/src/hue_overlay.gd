extends CanvasLayer

# Screen-space text that outlives a wave: Mum's letter subtitles, the region banner with Hue's map
# icon, and notices (Hue missing, audio still being read). Uses Brotato's own fonts.

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")
const FONT_PATH = "res://resources/fonts/actual/base/font_26_outline.tres"
const FONT_SMALL_PATH = "res://resources/fonts/actual/base/font_22.tres"

var _subtitle_box: PanelContainer
var _subtitle: Label
var _banner: PanelContainer
var _banner_icon: TextureRect
var _banner_title: Label
var _banner_sub: Label
var _banner_until := 0
var _notice: Label


func _ready() -> void:
	layer = 110
	pause_mode = PAUSE_MODE_PROCESS
	var font: Font = load(FONT_PATH)
	var small: Font = load(FONT_SMALL_PATH)
	var sub_font = font.duplicate() if font else null
	if sub_font is DynamicFont:
		sub_font.size = int(D.T("subtitle_font_size"))

	var root := Control.new()
	root.anchor_right = 1.0
	root.anchor_bottom = 1.0
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)

	_subtitle_box = PanelContainer.new()
	_subtitle_box.add_stylebox_override("panel", _panel_style(0.72))
	_subtitle_box.anchor_left = 0.5
	_subtitle_box.anchor_right = 0.5
	_subtitle_box.anchor_top = 1.0
	_subtitle_box.anchor_bottom = 1.0
	_subtitle_box.margin_left = -460
	_subtitle_box.margin_right = 460
	_subtitle_box.margin_top = -150
	_subtitle_box.margin_bottom = -70
	_subtitle_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_subtitle_box.hide()
	root.add_child(_subtitle_box)
	_subtitle = Label.new()
	_subtitle.autowrap = true
	_subtitle.align = Label.ALIGN_CENTER
	_subtitle.valign = Label.VALIGN_CENTER
	if sub_font:
		_subtitle.add_font_override("font", sub_font)
	_subtitle_box.add_child(_subtitle)

	_banner = PanelContainer.new()
	_banner.add_stylebox_override("panel", _panel_style(0.6))
	_banner.anchor_left = 0.5
	_banner.anchor_right = 0.5
	_banner.margin_left = -230
	_banner.margin_right = 230
	_banner.margin_top = 120
	_banner.margin_bottom = 300
	_banner.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_banner.hide()
	root.add_child(_banner)
	var box := VBoxContainer.new()
	box.alignment = BoxContainer.ALIGN_CENTER
	_banner.add_child(box)
	_banner_icon = TextureRect.new()
	_banner_icon.expand = true
	_banner_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_banner_icon.rect_min_size = Vector2(200, 110)
	box.add_child(_banner_icon)
	_banner_title = Label.new()
	_banner_title.align = Label.ALIGN_CENTER
	if font:
		_banner_title.add_font_override("font", font)
	box.add_child(_banner_title)
	_banner_sub = Label.new()
	_banner_sub.align = Label.ALIGN_CENTER
	if small:
		_banner_sub.add_font_override("font", small)
	box.add_child(_banner_sub)

	_notice = Label.new()
	_notice.autowrap = true
	_notice.align = Label.ALIGN_CENTER
	_notice.anchor_left = 0.5
	_notice.anchor_right = 0.5
	_notice.margin_left = -520
	_notice.margin_right = 520
	_notice.margin_top = 12
	_notice.margin_bottom = 80
	if small:
		_notice.add_font_override("font", small)
	_notice.add_color_override("font_color", Color(1, 0.86, 0.5))
	root.add_child(_notice)


func _process(_delta: float) -> void:
	if _banner.visible:
		var left := _banner_until - OS.get_ticks_msec()
		_banner.modulate.a = clamp(left / 500.0, 0.0, 1.0)
		if left <= 0:
			_banner.hide()


func show_subtitle(text: String) -> void:
	_subtitle.text = text
	_subtitle_box.visible = text != ""


func show_banner(icon: Texture, title: String, subtitle: String) -> void:
	_banner_icon.texture = icon
	_banner_title.text = title
	_banner_sub.text = subtitle
	_banner.modulate.a = 1.0
	_banner.show()
	_banner_until = OS.get_ticks_msec() + int(D.T("banner_seconds") * 1000)


func set_notice(text: String) -> void:
	_notice.text = text


static func _panel_style(alpha: float) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = Color(0.06, 0.06, 0.08, alpha)
	s.corner_radius_top_left = 10
	s.corner_radius_top_right = 10
	s.corner_radius_bottom_left = 10
	s.corner_radius_bottom_right = 10
	s.content_margin_left = 18
	s.content_margin_right = 18
	s.content_margin_top = 10
	s.content_margin_bottom = 10
	return s
