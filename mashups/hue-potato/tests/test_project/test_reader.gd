extends SceneTree

# Headless test of the Unity reader + texture decoder against the real Hue install.
# Run: godot --no-window -s test_reader.gd -- <Hue_Data> <out_dir>
# The mod sources are mounted at res://mods-unpacked via a junction made by run_tests.ps1.

const Reader = preload("res://mods-unpacked/HueBrotato-HuePotato/src/unity_reader.gd")
const Tex = preload("res://mods-unpacked/HueBrotato-HuePotato/src/tex_decode.gd")
const Sheets = preload("res://mods-unpacked/HueBrotato-HuePotato/generated/sheets.gd")

var failures := 0


func _init() -> void:
	var args := OS.get_cmdline_args()
	var hue_data: String = args[args.size() - 2]
	var out_dir: String = args[args.size() - 1]
	var readers := {}
	var t0 := OS.get_ticks_msec()
	for id in Sheets.HUE_ASSETS_ORDER:
		var row: Dictionary = Sheets.HUE_ASSETS[id]
		var r = _reader(readers, hue_data, row.file)
		if r == null:
			_fail(id, "cannot open " + row.file)
			continue
		match row.kind:
			"texture":
				var t: Dictionary = r.read_texture(row.path_id)
				if t.empty():
					_fail(id, r.error)
					continue
				if t.name != row.unity_name or "%dx%d" % [t.width, t.height] != row.size:
					_fail(id, "got %s %dx%d" % [t.name, t.width, t.height])
				var step := 4 if t.width > 400 else 1
				var img: Image = Tex.decode_full(t, step)
				img.save_png(out_dir.plus_file(id + ".png"))
			"sprite":
				var s: Dictionary = r.read_sprite(row.path_id)
				if s.empty():
					_fail(id, r.error)
					continue
				var size := "%dx%d" % [int(round(s.rect.size.x)), int(round(s.rect.size.y))]
				if s.name != row.unity_name or size != row.size:
					_fail(id, "got %s %s" % [s.name, size])
				var tr = _reader(readers, hue_data, r.external_file(s.texture_file_id))
				var t: Dictionary = tr.read_texture(s.texture_path_id)
				if t.empty():
					_fail(id, "atlas: " + tr.error)
					continue
				var img: Image = Tex.decode_region(t, s.rect)
				img.save_png(out_dir.plus_file(id + ".png"))
				if s.rotation != 0:
					_fail(id, "rotated sprite (%d)" % s.rotation)
			"audio":
				var a: Dictionary = r.read_audio_clip(row.path_id)
				if a.empty():
					_fail(id, r.error)
					continue
				if a.name != row.unity_name or "%.1f" % a.length != row.size:
					_fail(id, "got %s %.1f" % [a.name, a.length])
				var bytes: PoolByteArray = r.read_audio_bytes(a)
				if bytes.size() != a.size or bytes.subarray(0, 3).get_string_from_ascii() != "FSB5":
					_fail(id, "audio bytes not FSB5 (%d of %d)" % [bytes.size(), a.size])
			"text":
				var text: String = r.read_text_asset(row.path_id)
				if text.length() < 1000 or text.find("VO/Aqua0") < 0:
					_fail(id, "text table missing VO lines")
	print("checked %d assets in %d ms, %d failure(s)" % [Sheets.HUE_ASSETS_ORDER.size(), OS.get_ticks_msec() - t0, failures])
	quit(1 if failures > 0 else 0)


func _reader(cache: Dictionary, hue_data: String, file: String):
	if not cache.has(file):
		var r = Reader.new()
		if not r.open(hue_data.plus_file(file)):
			print("open failed: ", r.error)
			cache[file] = null
		else:
			cache[file] = r
	return cache[file]


func _fail(id: String, msg: String) -> void:
	failures += 1
	print("FAIL ", id, ": ", msg)
