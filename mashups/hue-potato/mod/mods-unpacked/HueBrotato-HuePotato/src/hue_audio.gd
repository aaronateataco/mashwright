extends Node

# Plays Hue's own audio inside Brotato: sound effects (sounds sheet), the wheel chimes, region music
# on the Music bus (Brotato's track is paused meanwhile) and Mum's voice letters with subtitles.

signal letter_line(text)     # current subtitle line ("" when the letter ends)

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")
const SFX_VOICES = 6

var content = null
var _sfx := []
var _sfx_stop_at := []
var _music: AudioStreamPlayer
var _music_id := ""
var _music_wanted := ""
var _music_fade := 0.0      # >0 fading in, <0 fading out (dB per real second)
var _vo: AudioStreamPlayer
var _vo_lines := []
var _vo_wanted := {}        # letter waiting for its audio: {asset, text_key, lines}
var _vo_queue := []         # letters waiting for Mum to finish the one she is reading
var _vo_active := false
var _sting_until_ms := 0    # a music sting is playing: the region music stays down until then
var _vo_started_ms := 0
var _vo_line := -1
var _brotato_paused := false
var _last_ms := 0
var _game_paused := false


func _ready() -> void:
	pause_mode = PAUSE_MODE_PROCESS
	for _i in SFX_VOICES:
		var p := AudioStreamPlayer.new()
		p.bus = "Sound"
		add_child(p)
		_sfx.append(p)
		_sfx_stop_at.append(0)
	_music = AudioStreamPlayer.new()
	_music.bus = "Music"
	_music.volume_db = -80
	add_child(_music)
	_vo = AudioStreamPlayer.new()
	_vo.bus = "Sound"
	add_child(_vo)
	_last_ms = OS.get_ticks_msec()
	content.connect("audio_ready", self, "_on_audio_ready")


func _process(_delta: float) -> void:
	# Real time: the colour wheel slows the game clock to Hue's 0.1.
	var now := OS.get_ticks_msec()
	var dt := (now - _last_ms) / 1000.0
	_last_ms = now
	_update_pause(dt)
	_update_sfx(now)
	_update_music(dt)
	_update_sting(now, dt)
	_update_vo(now)


# Brotato's pause menu: Mum waits with her letter (and its subtitle) until the game resumes.
func _update_pause(dt: float) -> void:
	var paused := get_tree().paused
	if paused == _game_paused:
		if paused:
			_vo_started_ms += int(dt * 1000)
		return
	_game_paused = paused
	_vo.stream_paused = paused
	if paused:
		emit_signal("letter_line", "")
	elif _vo_line >= 0 and _vo_line < _vo_lines.size():
		emit_signal("letter_line", _vo_lines[_vo_line][1])


# ---- sound effects --------------------------------------------------------------------------

func play_sound(sound_id: String) -> void:
	var row: Dictionary = D.Sheets.SOUNDS[sound_id]
	var choices := []
	for asset_id in row.assets:
		if content.has_audio(asset_id):
			choices.append(asset_id)
	if choices.empty():
		return
	_play(content.streams[choices[randi() % choices.size()]], row.bus, D.T(row.volume_tuning), D.T(row.max_length_tuning))


func play_chime(colour_id: String) -> void:
	var asset_id: String = D.colour_row(colour_id).chime
	if content.has_audio(asset_id):
		_play(content.streams[asset_id], "Sound", D.T("sfx_volume_db"), D.T("chime_length_s"))


func _play(stream: AudioStream, bus: String, volume_db: float, max_s: float) -> void:
	var best := 0
	for i in _sfx.size():
		if not _sfx[i].playing:
			best = i
			break
		if _sfx_stop_at[i] < _sfx_stop_at[best]:
			best = i
	var p: AudioStreamPlayer = _sfx[best]
	p.stream = stream
	p.bus = bus
	p.volume_db = volume_db
	p.play()
	_sfx_stop_at[best] = OS.get_ticks_msec() + int(max_s * 1000)


func _update_sfx(now: int) -> void:
	for i in _sfx.size():
		var p: AudioStreamPlayer = _sfx[i]
		if not p.playing:
			continue
		var left: int = _sfx_stop_at[i] - now
		if left <= 0:
			p.stop()
		elif left < 400:
			p.volume_db = min(p.volume_db, linear2db(left / 400.0) + D.T("sfx_volume_db"))


# ---- region music ---------------------------------------------------------------------------

func play_music(asset_id: String) -> void:
	_music_wanted = asset_id
	if asset_id == _music_id and _music.playing:
		return
	content.request_audio(asset_id)
	if content.has_audio(asset_id):
		_start_music(asset_id)


func stop_music() -> void:
	_music_wanted = ""
	if _music.playing:
		_music_fade = -40.0 / max(0.1, D.T("music_fade_s"))
	_resume_brotato_music()


func _start_music(asset_id: String) -> void:
	var stream: AudioStreamSample = content.streams[asset_id]
	stream.loop_mode = AudioStreamSample.LOOP_FORWARD
	stream.loop_begin = 0
	stream.loop_end = int(stream.get_length() * stream.mix_rate)
	if _music_id != "" and _music_id != asset_id:
		content.release_audio(_music_id)
	_music_id = asset_id
	_music.stream = stream
	_music.volume_db = -40
	_music.play()
	_music_fade = 40.0 / max(0.1, D.T("music_fade_s"))
	_pause_brotato_music()


func _update_music(dt: float) -> void:
	if _music_fade == 0.0:
		return
	var target := _music_target_db()
	if _music_fade > 0:
		_music.volume_db = min(target, _music.volume_db + _music_fade * dt)
		if _music.volume_db >= target:
			_music_fade = 0.0
	else:
		_music.volume_db += _music_fade * dt
		if _music.volume_db <= -40:
			_music.stop()
			_music_fade = 0.0
			if _music_id != "" and _music_wanted != _music_id:
				content.release_audio(_music_id)
				_music_id = ""


# A one-off music cue (Dr Grey's) over the region music, which dips under it and comes back.
func play_sting(sound_id: String) -> void:
	var row: Dictionary = D.Sheets.SOUNDS[sound_id]
	for asset_id in row.assets:
		content.request_audio(asset_id)
	play_sound(sound_id)
	_sting_until_ms = OS.get_ticks_msec() + int(D.T(row.max_length_tuning) * 1000)


func _update_sting(now: int, dt: float) -> void:
	if _sting_until_ms == 0:
		return
	if now < _sting_until_ms:
		_music.volume_db = move_toward(_music.volume_db, -40.0, 60.0 * dt)
		_music_fade = 0.0
		return
	_sting_until_ms = 0
	if _music.playing:
		_music_fade = 20.0 / max(0.1, D.T("music_fade_s"))


func _music_target_db() -> float:
	var db := D.T("music_volume_db")
	if _vo.playing:
		db += D.T("vo_duck_db")
	return db


func _pause_brotato_music() -> void:
	if not _brotato_paused:
		MusicManager.player.stream_paused = true
		_brotato_paused = true


func _resume_brotato_music() -> void:
	if _brotato_paused:
		MusicManager.player.stream_paused = false
		_brotato_paused = false


# ---- Mum's letters --------------------------------------------------------------------------

# Mum never cuts herself off: a letter that comes while she is reading waits its turn.
func play_letter(asset_id: String, text_key: String, line_count: int) -> void:
	var letter := {"asset": asset_id, "text_key": text_key, "lines": line_count}
	content.request_audio(asset_id)
	if is_letter_playing():
		_vo_queue.append(letter)
	else:
		_want_letter(letter)


func _want_letter(letter: Dictionary) -> void:
	_vo_wanted = letter
	content.request_audio(letter.asset)
	if content.has_audio(letter.asset):
		_start_letter()


func stop_letter() -> void:
	for letter in _vo_queue:
		content.release_audio(letter.asset)
	_vo_queue.clear()
	_vo_active = false
	_vo_wanted = {}
	if _vo.playing:
		_vo.stop()
	_vo_lines = []
	_vo_line = -1
	emit_signal("letter_line", "")


func is_letter_playing() -> bool:
	return _vo_active or not _vo_wanted.empty()


func _start_letter() -> void:
	var asset_id: String = _vo_wanted.asset
	var stream: AudioStreamSample = content.streams[asset_id]
	stream.loop_mode = AudioStreamSample.LOOP_DISABLED
	# Hue doesn't store subtitle timings with the text; spread the lines over the recording by
	# their length, which follows Mum's reading pace closely enough.
	var lines := []
	var total_chars := 0
	for i in _vo_wanted.lines:
		var text: String = content.hue_text("%s%d" % [_vo_wanted.text_key, i])
		if text != "":
			lines.append(text)
			total_chars += text.length() + 12
	var length := stream.get_length()
	var t := 0.0
	_vo_lines = []
	for text in lines:
		_vo_lines.append([t, text])
		t += length * (text.length() + 12) / max(1.0, total_chars)
	_vo_wanted = {}
	_vo_active = true
	_vo.stream = stream
	_vo.volume_db = D.T("vo_volume_db")
	_vo.play()
	_vo_started_ms = OS.get_ticks_msec()
	_vo_line = -1
	play_sound("sfx_letter")
	if _music.playing:
		# Duck the music under Mum's voice; _update_vo raises it again when she finishes.
		_music.volume_db = min(_music.volume_db, _music_target_db())
		_music_fade = 0.0
	content.release_audio(asset_id)


func _update_vo(now: int) -> void:
	if not _vo.playing:
		if _vo_active and not _game_paused:
			_vo_active = false
			_vo_line = -1
			emit_signal("letter_line", "")
			if _music.playing and _sting_until_ms == 0:
				_music_fade = 20.0 / max(0.1, D.T("music_fade_s"))
			if not _vo_queue.empty():
				_want_letter(_vo_queue.pop_front())
		return
	var t := (now - _vo_started_ms) / 1000.0
	var idx := -1
	for i in _vo_lines.size():
		if t >= _vo_lines[i][0]:
			idx = i
	if idx != _vo_line and idx >= 0:
		_vo_line = idx
		emit_signal("letter_line", _vo_lines[idx][1])


func _on_audio_ready(asset_id: String) -> void:
	if asset_id == _music_wanted and asset_id != _music_id:
		_start_music(asset_id)
	if not _vo_wanted.empty() and asset_id == _vo_wanted.asset:
		_start_letter()
