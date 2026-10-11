extends Node

# One wave of a Hue Potato run. Owns Hue's colour wheel (input, slow-motion, HUD), the background
# colour (arena floor tint), the colour fragment for this wave, the region banner and music, and
# the item synergies. Enemies and bullets read `bg` to know whether they are hidden.

const D = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")
const WheelUI = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_wheel_ui.gd")
const Fragment = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_fragment.gd")
const Tint = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_tint.gd")
const SwitchWave = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_switch_wave.gd")
const Hazards = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_hazards.gd")
const Crate = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_crate.gd")

var hp = null      # the mod's main node
var main = null    # Brotato's main (wave) scene
var hazards = null # Hue's laser gates and skull boulders
var wave := 1
var owned := []    # colour ids found so far, in wheel order
var bg: String = D.GREY
var wheel_open := false
var wheel_hover: String = D.GREY

var _region := {}
var _hud: CanvasLayer = null
var _wheel_ui = null
var _fragment_colour := ""
var _fragment = null
var _fragment_done := false
var _floor_from := Color.white
var _floor_to := Color.white
var _floor_t := 1.0
var _last_ms := 0
var _time_easing := false
var _switch_ready_ms := 0
var _syn_ready_ms := {}
var _mouse_start := Vector2.ZERO
var _mouse_moved := false
var _death_handled := false
var _won_handled := false
# What other mods (or Brotato) had set before this wave touched it; Hue's effects scale these.
var _floor_base := Color.white
var _background_base := Color.white
var _floor_applied := Color(-1, -1, -1, -1)
var _background_applied := Color(-1, -1, -1, -1)
var _time_base := 1.0
var _time_owned := false


func setup(p_hp, p_main) -> void:
	hp = p_hp
	main = p_main


func _ready() -> void:
	pause_mode = PAUSE_MODE_PROCESS
	wave = RunData.current_wave
	owned = D.colours_owned_at_wave_start(wave)
	bg = hp.last_bg if owned.has(hp.last_bg) else D.GREY
	_fragment_colour = D.fragment_for_wave(wave)
	_region = D.region_for_wave(wave)
	_last_ms = OS.get_ticks_msec()

	_hud = CanvasLayer.new()
	_hud.layer = 100
	add_child(_hud)
	_wheel_ui = WheelUI.new()
	_wheel_ui.run = self
	_wheel_ui.symbols = hp.symbol_textures
	if wave <= 2:
		_wheel_ui.hint = tr("HUE_WHEEL_HINT")
	_hud.add_child(_wheel_ui)

	_floor_to = _floor_colour(bg)
	_apply_floor(_floor_to)

	# Every regular enemy (new or reused from Brotato's pool) passes through enemy_respawned.
	main._entity_spawner.connect("enemy_respawned", self, "_on_enemy_respawned")
	# Trees become Hue's crates the same way.
	if hp.opt("hue_crates"):
		main._entity_spawner.connect("neutral_respawned", self, "_on_neutral_respawned")
		for tree in main._entity_spawner.neutrals:
			_on_neutral_respawned(tree)

	if wave == 1:
		hp.hazard_hinted.clear()
	hazards = Hazards.new()
	hazards.hp = hp
	hazards.run = self
	# The wheel keeps working in Brotato's pause menu checks; hazards stop with the game.
	hazards.pause_mode = PAUSE_MODE_STOP
	add_child(hazards)
	if hp.opt("hue_dust"):
		_add_dust()

	if hp.opt("hue_music"):
		hp.audio.play_music(_region.music)
	if wave == 1 or wave == _region.wave_from:
		hp.overlay.show_banner(hp.textures.get(_region.icon), tr(_region.name_key), tr("HUE_BANNER_WAVES").format([_region.wave_from, _region.wave_to]))
		hp.audio.play_sound("sfx_region")

	# Mum's story letters for this wave, then the letters for the colours Hue starts with. Mum
	# reads them one after another.
	hp.play_story_letters(wave)
	var starting := _starting_colours()
	if wave <= starting.size():
		hp.play_letter(starting[wave - 1])
	if _fragment_colour != "":
		hp.content.request_audio(D.colour_row(_fragment_colour).letter_vo)
	var next_region := D.region_for_wave(_region.wave_to + 1)
	hp.content.request_audio(next_region.music)

	# The last wave: Dr Grey appears, with his music from Hue.
	if wave == RunData.nb_of_waves:
		hp.overlay.show_banner(hp.textures.get("spr_dr_grey"), tr("HUE_DRGREY"), tr("HUE_DRGREY_SUB"))
		if hp.opt("hue_music"):
			hp.audio.play_sting("sfx_drgrey")


func _exit_tree() -> void:
	_restore_time()
	hp.end_wave(self)


func _process(_delta: float) -> void:
	var now := OS.get_ticks_msec()
	var dt := (now - _last_ms) / 1000.0
	_last_ms = now
	if get_tree().paused:
		if wheel_open:
			_close_wheel(false)
		_restore_time()
		return
	if not _death_handled and _player_dead():
		# Run lost: put the wheel away and let Mum stop reading over Brotato's end screen.
		_death_handled = true
		if wheel_open:
			_close_wheel(false)
		_restore_time()
		_wheel_ui.hide()
		hp.audio.stop_letter()
	if not _won_handled and main._is_run_won:
		# Run won: Mum's last letter and her PS, read over Brotato's end screen.
		_won_handled = true
		if wheel_open:
			_close_wheel(false)
		_restore_time()
		hp.play_story_letters(0)
	_update_wheel()
	_update_time_scale(dt)
	_update_floor(dt)
	_update_fragment()


func _physics_process(_delta: float) -> void:
	_update_projectiles()


# ---- enemies and their bullets ----------------------------------------------------------------

func _on_enemy_respawned(enemy) -> void:
	var tint = Tint.on(enemy)
	if tint != null:
		tint.clear()
	if not hp.enemy_takes_colour(enemy) or owned.empty():
		return
	if tint == null:
		tint = Tint.new()
		tint.name = Tint.NAME
		enemy.add_child(tint)
	tint.assign(hp, owned[randi() % owned.size()])


func _on_neutral_respawned(tree) -> void:
	if not is_instance_valid(tree) or owned.empty() or hp.registry.crate_texture == null:
		return
	var crate = Crate.on(tree)
	if crate == null:
		crate = Crate.new()
		crate.name = Crate.NAME
		tree.add_child(crate)
	crate.assign(hp, owned[randi() % owned.size()], hp.registry.crate_texture)


# Hue's dust motes drifting over the arena floor, under the potatoes and enemies.
func _add_dust() -> void:
	var tex: Texture = hp.textures.get("tex_dot_particle")
	if tex == null:
		return
	var lo: Vector2 = ZoneService.current_zone_min_position
	var hi: Vector2 = ZoneService.current_zone_max_position
	var dust := CPUParticles2D.new()
	dust.name = "HueDust"
	dust.texture = tex
	dust.amount = int(D.T("dust_amount"))
	dust.lifetime = D.T("dust_lifetime_s")
	dust.preprocess = dust.lifetime
	dust.local_coords = false
	dust.emission_shape = CPUParticles2D.EMISSION_SHAPE_RECTANGLE
	dust.emission_rect_extents = (hi - lo) / 2.0
	dust.position = (lo + hi) / 2.0
	dust.direction = Vector2(0, -1)
	dust.spread = 180.0
	dust.gravity = Vector2.ZERO
	dust.initial_velocity = D.T("dust_speed_px_s")
	dust.initial_velocity_random = 0.6
	dust.scale_amount = D.T("dust_size_px") / tex.get_width()
	dust.scale_amount_random = 0.6
	var ramp := Gradient.new()
	ramp.set_color(0, Color(1, 1, 1, 0))
	ramp.set_color(1, Color(1, 1, 1, 0))
	ramp.add_point(0.5, Color(1, 1, 1, D.T("dust_alpha")))
	dust.color_ramp = ramp
	main.add_child_below_node(main._tile_map, dust)


func first_live_player():
	for player in main._players:
		if is_instance_valid(player) and not player.dead:
			return player
	return null


func wave_lost() -> bool:
	return _death_handled or _won_handled


func colour_of_enemy(enemy) -> String:
	if not is_instance_valid(enemy):
		return ""
	var tint = Tint.on(enemy)
	return tint.colour_id if tint != null else ""


# Enemy bullets take their shooter's colour and vanish with it. Brotato pools bullets, so the
# shooter is re-checked whenever it changes. Only bullets coloured here are touched, and their
# original tint and opacity (which another mod may have set) are put back.
func _update_projectiles() -> void:
	var container = main._enemy_projectiles
	if not is_instance_valid(container):
		return
	var hidden_alpha := D.T("hidden_projectile_alpha")
	for p in container.get_children():
		if not ("_hitbox" in p) or not ("_sprite" in p) or p._hitbox == null:
			continue
		var from = p._hitbox.from
		var from_id: int = from.get_instance_id() if is_instance_valid(from) else 0
		if p.get_meta("hue_from", -1) != from_id:
			p.set_meta("hue_from", from_id)
			_uncolour_projectile(p)
			var c := colour_of_enemy(from)
			if c != "":
				p.set_meta("hue_colour", c)
				p.set_meta("hue_base_tint", p._sprite.self_modulate)
				p.set_meta("hue_base_alpha", p.modulate.a)
				p._sprite.self_modulate = p._sprite.self_modulate * Color.white.linear_interpolate(D.colour_of(c), D.T("projectile_tint_mix"))
		if not p.has_meta("hue_colour"):
			continue
		var hide: bool = p.get_meta("hue_colour") == bg
		if hide != p.get_meta("hue_hidden", false):
			p.set_meta("hue_hidden", hide)
			var base_alpha: float = p.get_meta("hue_base_alpha")
			p.modulate.a = base_alpha * hidden_alpha if hide else base_alpha
			if hide:
				p._hitbox.disable()
			elif p._hitbox.active:
				p._hitbox.enable()


static func _uncolour_projectile(p) -> void:
	if not p.has_meta("hue_colour"):
		return
	p._sprite.self_modulate = p.get_meta("hue_base_tint")
	p.modulate.a = p.get_meta("hue_base_alpha")
	if p.get_meta("hue_hidden", false) and p._hitbox.active:
		p._hitbox.enable()
	for key in ["hue_colour", "hue_base_tint", "hue_base_alpha", "hue_hidden"]:
		if p.has_meta(key):
			p.remove_meta(key)


func _input(event: InputEvent) -> void:
	if wheel_open or get_tree().paused or _player_dead():
		return
	if OS.get_ticks_msec() < _switch_ready_ms:
		return
	if event.is_action_pressed("hue_next"):
		_cycle(1)
	elif event.is_action_pressed("hue_prev"):
		_cycle(-1)
	elif event.is_action_pressed("hue_grey"):
		set_bg(D.GREY)


# Called by Brotato's main when the wave timer runs out.
func on_wave_ending() -> void:
	if wheel_open:
		_close_wheel(false)
	_restore_time()
	if _fragment_colour != "" and not _fragment_done:
		_collect_fragment()


# ---- the wheel ------------------------------------------------------------------------------

func _update_wheel() -> void:
	var hold := Input.is_action_pressed("hue_wheel_hold") and not _player_dead()
	if hold and not wheel_open:
		_open_wheel()
	elif not hold and wheel_open:
		_close_wheel(true)
	if not wheel_open:
		return
	var candidate := ""
	var mouse := get_viewport().get_mouse_position()
	if not _mouse_moved and mouse.distance_to(_mouse_start) > 6.0:
		_mouse_moved = true
	if _mouse_moved:
		candidate = _wheel_ui.slice_at(mouse)
	var dz := D.T("wheel_stick_deadzone")
	var stick := Vector2(Input.get_joy_axis(0, JOY_AXIS_2), Input.get_joy_axis(0, JOY_AXIS_3))
	if stick.length() < dz:
		stick = Vector2(Input.get_joy_axis(0, JOY_AXIS_0), Input.get_joy_axis(0, JOY_AXIS_1))
	if stick.length() >= dz:
		candidate = WheelUI.slice_for_direction(stick)
	if candidate != "" and candidate != wheel_hover and (candidate == D.GREY or owned.has(candidate)):
		wheel_hover = candidate
		if candidate != D.GREY:
			hp.audio.play_chime(candidate)


func _open_wheel() -> void:
	wheel_open = true
	wheel_hover = bg
	_mouse_start = get_viewport().get_mouse_position()
	_mouse_moved = false
	_time_easing = false
	if not _time_owned:
		_time_base = Engine.time_scale
		_time_owned = true
	Engine.time_scale = _time_base * D.T("wheel_time_scale")
	hp.audio.play_sound("sfx_wheel_open")


func _close_wheel(apply: bool) -> void:
	wheel_open = false
	_time_easing = true
	hp.audio.play_sound("sfx_wheel_close")
	if apply and wheel_hover != bg:
		set_bg(wheel_hover)


func _update_time_scale(dt: float) -> void:
	if not _time_easing:
		return
	var rate: float = _time_base * (1.0 - D.T("wheel_time_scale")) / max(0.01, D.T("wheel_ease_out_s"))
	Engine.time_scale = min(_time_base, Engine.time_scale + rate * dt)
	if Engine.time_scale >= _time_base:
		_restore_time()


# Puts back the game speed found when the wheel opened (another mod may run the game faster or
# slower than 1x).
func _restore_time() -> void:
	_time_easing = false
	if _time_owned:
		Engine.time_scale = _time_base
		_time_owned = false


func _cycle(direction: int) -> void:
	var choices := [D.GREY] + owned
	var i := choices.find(bg)
	var next: String = choices[(i + direction + choices.size()) % choices.size()]
	set_bg(next)
	if next != D.GREY:
		hp.audio.play_chime(next)


func set_bg(colour_id: String) -> void:
	if colour_id == bg:
		return
	var old := bg
	bg = colour_id
	hp.last_bg = colour_id
	_switch_ready_ms = OS.get_ticks_msec() + int(D.T("wheel_switch_cooldown_s") * 1000)
	_floor_from = _current_floor()
	_floor_to = _floor_colour(colour_id)
	_floor_t = 0.0
	hp.audio.play_sound("sfx_colour_goo")
	_spawn_switch_wave(colour_id)
	_on_colour_switched(old)


# ---- floor ----------------------------------------------------------------------------------

func _floor_colour(colour_id: String) -> Color:
	var mix: float = _region.get("floor_mix", D.T("floor_mix_default"))
	return Color.white.linear_interpolate(D.colour_of(colour_id), mix)


func _current_floor() -> Color:
	return _floor_from.linear_interpolate(_floor_to, _floor_t)


func _update_floor(dt: float) -> void:
	if _floor_t >= 1.0:
		return
	_floor_t = min(1.0, _floor_t + dt * 4.0)
	_apply_floor(_current_floor())


func _apply_floor(c: Color) -> void:
	# If another mod changed the floor colour since our last change, build on its colour instead.
	if is_instance_valid(main._tile_map):
		if main._tile_map.modulate != _floor_applied:
			_floor_base = main._tile_map.modulate
		_floor_applied = _floor_base * c
		main._tile_map.modulate = _floor_applied
	if is_instance_valid(main._background):
		if main._background.modulate != _background_applied:
			_background_base = main._background.modulate
		_background_applied = _background_base * Color.white.linear_interpolate(c, 0.6)
		main._background.modulate = _background_applied


# Hue's colour change sweeps out from the player as a ring of the new colour.
func _spawn_switch_wave(colour_id: String) -> void:
	if not hp.opt("switch_wave"):
		return
	for player in main._players:
		if is_instance_valid(player) and not player.dead:
			var wave_fx = SwitchWave.new()
			wave_fx.colour = D.colour_of(colour_id)
			main.add_child_below_node(main._tile_map, wave_fx)
			wave_fx.global_position = player.global_position
			return


# ---- fragments ------------------------------------------------------------------------------

func _update_fragment() -> void:
	if _fragment_colour == "" or _fragment_done:
		return
	if _fragment == null:
		var timer: Timer = main._wave_timer
		if timer.wait_time - timer.time_left >= timer.wait_time * D.T("fragment_spawn_fraction"):
			_spawn_fragment()
		return
	var radius := D.T("fragment_pickup_radius")
	for player in main._players:
		if is_instance_valid(player) and not player.dead and player.global_position.distance_to(_fragment.global_position) < radius:
			_collect_fragment()
			return


func _spawn_fragment() -> void:
	var lo: Vector2 = ZoneService.current_zone_min_position
	var hi: Vector2 = ZoneService.current_zone_max_position
	var anchor: Vector2 = (lo + hi) / 2.0
	for player in main._players:
		if is_instance_valid(player):
			anchor = player.global_position
			break
	var pos := anchor
	for _attempt in 12:
		pos = Vector2(rand_range(lo.x + 80, hi.x - 80), rand_range(lo.y + 80, hi.y - 80))
		if pos.distance_to(anchor) > 260 and pos.distance_to(anchor) < 700:
			break
	_fragment = Fragment.new()
	_fragment.colour_id = _fragment_colour
	_fragment.symbol = hp.symbol_textures.get(_fragment_colour)
	_fragment.disc = hp.textures.get("spr_sym_bg")
	_fragment.glow = hp.textures.get("tex_glow")
	main._entities_container.add_child(_fragment)
	_fragment.global_position = pos
	hp.overlay.show_banner(hp.symbol_textures.get(_fragment_colour), tr("HUE_FRAGMENT_HINT"), tr(D.colour_row(_fragment_colour).name_key))


func _collect_fragment() -> void:
	_fragment_done = true
	if _fragment != null and is_instance_valid(_fragment):
		_fragment.queue_free()
	_fragment = null
	var found := []
	for id in D.wheel_order():
		if owned.has(id) or id == _fragment_colour:
			found.append(id)
	owned = found
	hp.audio.play_sound("sfx_fragment")
	_spawn_switch_wave(_fragment_colour)
	var colour_name: String = tr(D.colour_row(_fragment_colour).name_key)
	hp.overlay.show_banner(hp.symbol_textures.get(_fragment_colour), tr("HUE_FRAGMENT_FOUND").format([colour_name]), "")
	hp.play_letter(_fragment_colour)
	_run_synergies("fragment_collected", [])


func _starting_colours() -> Array:
	var start := []
	for order in range(1, D.Sheets.COLOURS_ORDER.size() + 1):
		for id in D.Sheets.COLOURS_ORDER:
			var row: Dictionary = D.Sheets.COLOURS[id]
			if row.unlock_wave == 0 and row.unlock_order == order:
				start.append(id)
	return start


# ---- synergies ------------------------------------------------------------------------------

func _on_colour_switched(old: String) -> void:
	var revealed := []
	if old != D.GREY:
		for enemy in main._entity_spawner.get_all_enemies():
			if is_instance_valid(enemy) and not enemy.dead and colour_of_enemy(enemy) == old:
				revealed.append(enemy)
	_run_synergies("colour_switched", revealed)


func _run_synergies(trigger: String, revealed: Array) -> void:
	var now := OS.get_ticks_msec()
	for player_index in RunData.get_player_count():
		if player_index >= main._players.size():
			continue
		var player = main._players[player_index]
		if not is_instance_valid(player) or player.dead:
			continue
		var counts := {}
		for item in RunData.get_player_items(player_index):
			var row_id: String = hp.registry.item_row_for(item.my_id)
			if row_id != "":
				counts[row_id] = counts.get(row_id, 0) + 1
		for row_id in counts:
			var syn: Dictionary = D.synergy_for_item(row_id)
			if syn.empty() or syn.trigger != trigger:
				continue
			var key := "%s_%d" % [syn.id, player_index]
			if now < _syn_ready_ms.get(key, 0):
				continue
			var n: int = counts[row_id]
			match syn.action:
				"heal_percent_max_hp":
					player.heal(int(player.max_stats.health * syn.amount * n / 100.0))
				"heal_flat":
					player.heal(int(syn.amount * n))
				"materials_per_revealed":
					var gold := int(min(revealed.size(), syn.cap) * syn.amount * n)
					if gold <= 0:
						continue
					RunData.add_gold(gold, player_index)
				"slow_revealed_percent":
					if revealed.empty():
						continue
					for i in int(min(revealed.size(), syn.cap)):
						var e = revealed[i]
						e.add_decaying_speed(-int(e.current_stats.speed * syn.amount / 100.0))
			_syn_ready_ms[key] = now + int(syn.cooldown_s * 1000)


func _player_dead() -> bool:
	for player in main._players:
		if is_instance_valid(player) and not player.dead:
			return false
	return main._players.size() > 0
