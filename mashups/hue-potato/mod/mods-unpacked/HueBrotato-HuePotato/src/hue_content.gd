extends Node

# Reads Hue's content from the player's own copy of Hue while Brotato runs: art is decoded on a
# thread at startup, Hue's text table (Mum's letters, five languages) is parsed, and audio is
# decoded on demand by the bundled vgmstream into memory. Nothing from Hue ships with the mod.

signal art_ready(ok)
signal audio_ready(asset_id)

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")
const Reader = preload("res://mods-unpacked/HueBrotato-HuePotato/src/unity_reader.gd")
const Tex = preload("res://mods-unpacked/HueBrotato-HuePotato/src/tex_decode.gd")
const Art = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_art.gd")
const Locator = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_locator.gd")

const STATE_SEARCHING = "searching"
const STATE_LOADING = "loading"
const STATE_READY = "ready"
const STATE_MISSING = "missing"
const STATE_FAILED = "failed"
const LANG_COLUMNS = {"en": 1, "fr": 2, "ru": 3, "de": 4, "es": 5}
const POTATO_PATH = "res://entities/units/player/potato.png"
const BIG_TEXTURE_PX = 400

var state := STATE_SEARCHING
var hue_data := ""
var error := ""
var log_lines := []

var images := {}             # hue asset id -> Image
var layer_images := {}       # layer id -> Image on the 150x150 potato canvas
var dead_layer_images := {}  # layer id -> Image (dead variant) for layers that have one
var portrait_image: Image = null
var body_image: Image = null
var weapon_icon_image: Image = null
var item_icon_images := {}   # item row id -> Image 96x96
var text_table := {}         # HueText key -> PoolStringArray [key, en, fr, ru, de, es]

var streams := {}            # audio asset id -> AudioStreamSample
var _readers := {}
var _reader_mutex := Mutex.new()
var _potato: Image = null
var _art_thread: Thread = null

var _audio_thread: Thread = null
var _audio_mutex := Mutex.new()
var _audio_sem := Semaphore.new()
var _audio_queue := []
var _audio_pending := {}
var _audio_failed := {}
var _quit := false
var _vgmstream := ""


# The bundled vgmstream for this OS: Windows build at the folder root, Linux and macOS builds in
# subfolders.
static func vgmstream_path(dir: String) -> String:
	match OS.get_name():
		"Windows", "UWP":
			return dir.plus_file("vgmstream-cli.exe")
		"OSX":
			return dir.plus_file("macos/vgmstream-cli")
	return dir.plus_file("linux/vgmstream-cli")


func start() -> void:
	var loc = Locator.new()
	hue_data = loc.find_hue_data()
	if hue_data == "":
		state = STATE_MISSING
		_log("Hue not found. Looked in: %s" % str(loc.tried))
		emit_signal("art_ready", false)
		return
	_log("Hue found at " + hue_data)
	_vgmstream = vgmstream_path(OS.get_executable_path().get_base_dir().plus_file("mods/huepotato-vgmstream"))
	if not File.new().file_exists(_vgmstream):
		_log("vgmstream not found at %s: Hue's audio is unavailable" % _vgmstream)
	elif OS.get_name() != "Windows":
		# Archive tools don't always keep the executable bit.
		var _code := OS.execute("chmod", ["+x", _vgmstream], true)
	var tex: Texture = load(POTATO_PATH)
	_potato = tex.get_data() if tex else null
	state = STATE_LOADING
	# Synchronous: Brotato restores a saved run while its autoloads start, and that run may be a
	# Hue Potato run, so the character must exist first (about a second of Hue reading).
	_art_thread_main(null)
	_audio_thread = Thread.new()
	_audio_thread.start(self, "_audio_thread_main", null)


func _exit_tree() -> void:
	_quit = true
	_audio_sem.post()
	if _art_thread and _art_thread.is_active():
		_art_thread.wait_to_finish()
	if _audio_thread and _audio_thread.is_active():
		_audio_thread.wait_to_finish()


# ---- text -----------------------------------------------------------------------------------

# A line of Hue's own text in the player's Brotato language (Hue has EN/FR/RU/DE/ES).
func hue_text(key: String) -> String:
	if not text_table.has(key):
		return ""
	var row: PoolStringArray = text_table[key]
	var lang: String = TranslationServer.get_locale().substr(0, 2)
	var col: int = LANG_COLUMNS.get(lang, 1)
	if col < row.size() and row[col] != "":
		return row[col]
	return row[1] if row.size() > 1 else ""


static func _parse_csv(text: String) -> Dictionary:
	var table := {}
	var row := PoolStringArray()
	var field := ""
	var quoted := false
	var i := 0
	var n := text.length()
	while i < n:
		var ch: String = text[i]
		if quoted:
			if ch == "\"":
				if i + 1 < n and text[i + 1] == "\"":
					field += "\""
					i += 1
				else:
					quoted = false
			else:
				field += ch
		elif ch == "\"":
			quoted = true
		elif ch == ",":
			row.append(field)
			field = ""
		elif ch == "\n" or ch == "\r":
			if ch == "\r" and i + 1 < n and text[i + 1] == "\n":
				i += 1
			row.append(field)
			field = ""
			if row.size() > 1 and row[0] != "":
				table[row[0]] = row
			row = PoolStringArray()
		else:
			field += ch
		i += 1
	if field != "" or row.size() > 0:
		row.append(field)
		if row.size() > 1:
			table[row[0]] = row
	return table


# ---- art (thread) ---------------------------------------------------------------------------

func _art_thread_main(_unused) -> void:
	var t0 := OS.get_ticks_msec()
	var ok := true
	for id in D.Sheets.HUE_ASSETS_ORDER:
		var row: Dictionary = D.asset(id)
		if row.kind == "texture" or row.kind == "sprite":
			var img = _load_image(row)
			if img == null:
				ok = false
				error = "could not read %s (%s): %s" % [id, row.unity_name, error]
				break
			images[id] = img
		elif row.kind == "text":
			var r = _reader(row.file)
			if r == null:
				ok = false
				break
			text_table = _parse_csv(r.read_text_asset(row.path_id))
	if ok:
		ok = _compose()
	if _art_thread == null:
		_art_done(ok, OS.get_ticks_msec() - t0)
	else:
		call_deferred("_art_done", ok, OS.get_ticks_msec() - t0)


func _load_image(row: Dictionary):
	var r = _reader(row.file)
	if r == null:
		return null
	if row.kind == "texture":
		var t: Dictionary = r.read_texture(row.path_id)
		if t.empty() or not Tex.supported(t.format):
			error = r.error if t.empty() else "texture format %d" % t.format
			return null
		var step: int = 4 if t.width > BIG_TEXTURE_PX else 1
		return Tex.decode_full(t, step)
	var s: Dictionary = r.read_sprite(row.path_id)
	if s.empty():
		error = r.error
		return null
	var tr = _reader(r.external_file(s.texture_file_id))
	if tr == null:
		return null
	var atlas: Dictionary = tr.read_texture(s.texture_path_id)
	if atlas.empty() or not Tex.supported(atlas.format):
		error = tr.error if atlas.empty() else "atlas format %d" % atlas.format
		return null
	return Tex.decode_region(atlas, s.rect)


func _compose() -> bool:
	var ch: Dictionary = D.character()
	var tint := Color8(ch.body_tint[0], ch.body_tint[1], ch.body_tint[2])
	for layer_id in D.Sheets.LAYERS_ORDER:
		var layer: Dictionary = D.Sheets.LAYERS[layer_id]
		layer_images[layer_id] = Art.layer_image(images[layer.asset], layer)
		if layer.dead_asset != "none":
			dead_layer_images[layer_id] = Art.layer_image(images[layer.dead_asset], layer)
	if _potato == null:
		error = "Brotato's potato image is missing"
		return false
	# Hue's dark silhouette on Brotato's own potato body, worn as a layer so menus show it too.
	body_image = _potato.duplicate()
	if body_image.get_format() != Image.FORMAT_RGBA8:
		body_image.convert(Image.FORMAT_RGBA8)
	Art._tint(body_image, tint)
	var portrait_layers := []
	for layer_id in ch.icon_layers:
		portrait_layers.append(layer_images[layer_id])
	portrait_image = Art.portrait(_potato, tint, portrait_layers)
	var ring: Dictionary = D.Sheets.WEAPONS[D.Sheets.WEAPONS_ORDER[0]]
	var ring_colours := []
	for colour_id in ["aqua", "purple", "orange"]:
		ring_colours.append(D.colour_of(colour_id))
	weapon_icon_image = Art.laser_ring_icon(images[ring.beam_asset], images[ring.emitter_asset], images[ring.emitter_mask_asset], ring_colours)
	for item_id in D.Sheets.ITEMS_ORDER:
		var item: Dictionary = D.Sheets.ITEMS[item_id]
		var second = images[item.icon2] if item.icon2 != "none" else null
		item_icon_images[item_id] = Art.item_icon(images[item.icon], item.icon_region, second, Color8(item.icon_tint[0], item.icon_tint[1], item.icon_tint[2]))
	return true


func _art_done(ok: bool, ms: int) -> void:
	if _art_thread != null:
		_art_thread.wait_to_finish()
	state = STATE_READY if ok else STATE_FAILED
	_log("Hue art %s in %d ms (%d images)%s" % ["read" if ok else "FAILED", ms, images.size(), "" if ok else ": " + error])
	emit_signal("art_ready", ok)
	if ok:
		# Short sounds first so the wheel and fragments have their voices early.
		for row_id in D.Sheets.SOUNDS_ORDER:
			for asset_id in D.Sheets.SOUNDS[row_id].assets:
				request_audio(asset_id)
		for colour_id in D.wheel_order():
			request_audio(D.colour_row(colour_id).chime)


# ---- audio (thread) -------------------------------------------------------------------------

func has_audio(asset_id: String) -> bool:
	return streams.has(asset_id)


func request_audio(asset_id: String) -> void:
	if state != STATE_READY or streams.has(asset_id) or _audio_pending.has(asset_id) or _audio_failed.has(asset_id):
		return
	_audio_pending[asset_id] = true
	_audio_mutex.lock()
	_audio_queue.append(asset_id)
	_audio_mutex.unlock()
	_audio_sem.post()


func release_audio(asset_id: String) -> void:
	streams.erase(asset_id)


func _audio_thread_main(_unused) -> void:
	while true:
		_audio_sem.wait()
		if _quit:
			return
		_audio_mutex.lock()
		var id = _audio_queue.pop_front() if not _audio_queue.empty() else null
		_audio_mutex.unlock()
		if id == null:
			continue
		var t0 := OS.get_ticks_msec()
		var result = _decode_audio(id)
		call_deferred("_audio_done", id, result, OS.get_ticks_msec() - t0)


func _decode_audio(id: String):
	var row: Dictionary = D.asset(id)
	var r = _reader(row.file)
	if r == null:
		return "cannot open " + row.file
	var clip: Dictionary = r.read_audio_clip(row.path_id)
	if clip.empty():
		return r.error
	var bytes: PoolByteArray = r.read_audio_bytes(clip)
	if bytes.size() != clip.size:
		return "short read of %s" % clip.source
	var tmp := OS.get_user_data_dir().plus_file("huepotato/tmp")
	Directory.new().make_dir_recursive(tmp)
	var fsb := tmp.plus_file(id + ".fsb")
	var wav := tmp.plus_file(id + ".wav")
	var f := File.new()
	if f.open(fsb, File.WRITE) != OK:
		return "cannot write " + fsb
	f.store_buffer(bytes)
	f.close()
	var code := OS.execute(_vgmstream, ["-o", wav, fsb], true)
	var stream = _wav_to_stream(wav)
	var dir := Directory.new()
	dir.remove(fsb)
	dir.remove(wav)
	if stream == null:
		return "vgmstream exit %d" % code
	return stream


static func _wav_to_stream(path: String):
	var f := File.new()
	if not f.file_exists(path) or f.open(path, File.READ) != OK:
		return null
	var bytes := f.get_buffer(f.get_len())
	f.close()
	if bytes.size() < 44 or bytes.subarray(0, 3).get_string_from_ascii() != "RIFF":
		return null
	var b := StreamPeerBuffer.new()
	b.data_array = bytes
	var channels := 0
	var rate := 0
	var bits := 0
	var data := PoolByteArray()
	var pos := 12
	while pos + 8 <= bytes.size():
		var chunk := bytes.subarray(pos, pos + 3).get_string_from_ascii()
		b.seek(pos + 4)
		var size := b.get_u32()
		if chunk == "fmt ":
			b.seek(pos + 10)
			channels = b.get_u16()
			rate = b.get_u32()
			b.seek(pos + 22)
			bits = b.get_u16()
		elif chunk == "data":
			var end: int = int(min(pos + 8 + size, bytes.size()))
			data = bytes.subarray(pos + 8, end - 1)
		pos += 8 + size + (size & 1)
	if bits != 16 or channels < 1 or data.empty():
		return null
	var s := AudioStreamSample.new()
	s.format = AudioStreamSample.FORMAT_16_BITS
	s.stereo = channels == 2
	s.mix_rate = rate
	s.data = data
	return s


func _audio_done(id: String, result, ms: int) -> void:
	_audio_pending.erase(id)
	if result is AudioStreamSample:
		streams[id] = result
		_log("audio %s ready in %d ms (%.1f s)" % [id, ms, result.get_length()])
		emit_signal("audio_ready", id)
	else:
		_audio_failed[id] = true
		_log("audio %s FAILED: %s" % [id, str(result)])


# ---- shared ---------------------------------------------------------------------------------

func _reader(file: String):
	_reader_mutex.lock()
	if not _readers.has(file):
		var r = Reader.new()
		if r.open(hue_data.plus_file(file)):
			_readers[file] = r
		else:
			error = r.error
			_readers[file] = null
	var reader = _readers[file]
	_reader_mutex.unlock()
	return reader


func _log(msg: String) -> void:
	log_lines.append(msg)
	ModLoaderLog.info(msg, "HuePotato:Content")
