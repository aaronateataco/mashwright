extends "res://main.gd"

# Test-only: acts like another visual mod (tints enemies and the floor) and, during Hue Potato runs,
# drives Hue's colour wheel and checks what Hue Potato did, logging PASS/FAIL lines. Hue Potato is
# NOT made invulnerable: every hit he takes is recorded and checked (a hidden enemy, bullet or
# hazard must never hurt him); the probe heals him when low so long tests keep going.

const PROBE_TINT = Color(0.7, 1.0, 0.7)
var _probe_ms := 0
var _probe_step := 0
var _probe_pass := 0
var _probe_fail := 0
var _ring_hits := 0
var _ring_damage := 0
var _hurt := {"enemy": 0, "bullet": 0, "hazard": 0, "other": 0}
var _hurt_damage := 0
var _hazard_ms := 0
var _hazard_turn := 0
var _showcase_done := false
var _summary_ms := 0
# Burst capture for picking a listing image: a frame every capture_every_s, saved on a thread.
var _cap_count := 0
var _cap_next_ms := 0
var _cap_start_ms := 0
var _cap_jobs := []
var _cap_mutex := Mutex.new()
var _cap_sem := Semaphore.new()
var _cap_thread: Thread = null


func _ready() -> void:
	ModLoaderLog.info("PROBE main _ready", "CompatProbe")
	if _setting("mode", "test") != "showcase":
		_tile_map.modulate = Color(1.0, 0.9, 0.9)
	_entity_spawner.connect("enemy_respawned", self, "_probe_tint")
	for pl in _players:
		pl.connect("took_damage", self, "_probe_hurt")
	_cap_start_ms = OS.get_ticks_msec() + int(float(_setting("capture_start_s", 4.0)) * 1000)
	if float(_setting("capture_every_s", 0.0)) > 0.0:
		var d := Directory.new()
		var _m := d.make_dir_recursive(_cap_dir())
		_cap_thread = Thread.new()
		var _e = _cap_thread.start(self, "_cap_worker")


func _exit_tree() -> void:
	if _cap_thread != null:
		_cap_mutex.lock()
		_cap_jobs.append(null)
		_cap_mutex.unlock()
		var _p = _cap_sem.post()
		_cap_thread.wait_to_finish()
		_cap_thread = null
	ModLoaderLog.info("PROBE wave summary: pass %d / fail %d; hurt %s (%d damage); ring hits %d (%d damage); frames %d" % [_probe_pass, _probe_fail, _hurt, _hurt_damage, _ring_hits, _ring_damage, _cap_count], "CompatProbe")


# Loaded at run time: the probe may be compiled before Hue Potato's zip is mounted.
func _hue_data():
	return load("res://mods-unpacked/HueBrotato-HuePotato/src/hue_data.gd")


func _setting(key: String, default):
	var p = Engine.get_meta("hue_probe") if Engine.has_meta("hue_probe") else null
	return p.setting(key, default) if p != null else default


func _cap_dir() -> String:
	return str(_setting("capture_dir", OS.get_executable_path().get_base_dir().plus_file("mods/probe_shots")))


func _probe_tint(enemy) -> void:
	if _setting("mode", "test") == "showcase":
		return
	enemy.sprite.self_modulate = PROBE_TINT
	if not enemy.is_connected("died", self, "_probe_died"):
		enemy.connect("died", self, "_probe_died")


func _probe_died(enemy, _args) -> void:
	var t := get_tree().create_timer(0.4, false)
	t.connect("timeout", self, "_probe_check_dead", [enemy])


func _probe_check_dead(enemy) -> void:
	if is_instance_valid(enemy):
		_check("dead enemy keeps the other mod's tint", enemy.sprite.self_modulate.is_equal_approx(PROBE_TINT), str(enemy.sprite.self_modulate))


# Every hit Hue Potato takes: what hit him, and was it visible?
func _probe_hurt(_unit, value, _kb, _crit, is_dodge, _prot, _armor, args, _hit_type, _one_shot) -> void:
	var hp = Engine.get_meta("hue_potato") if Engine.has_meta("hue_potato") else null
	if hp == null or hp.run == null or args == null:
		return
	var hb = args.hitbox
	var kind := "other"
	var hidden := false
	var what := ""
	if hb != null and is_instance_valid(hb):
		if hb.has_meta("hue_hazard"):
			kind = "hazard"
			var hz = hb.get_parent()
			what = "%s %s" % [hz.row.id, hz.colour_id]
			hidden = hp.is_hidden_colour(hz.colour_id)
		elif is_instance_valid(hb.from) and hb.from.get_node_or_null("HueTint") != null:
			var tint = hb.from.get_node("HueTint")
			kind = "bullet" if hb.get_parent() != hb.from else "enemy"
			what = tint.colour_id
			hidden = tint.hidden
	_hurt[kind] += 1
	_hurt_damage += int(value)
	ModLoaderLog.info("PROBE hurt by %s %s for %d%s (bg %s)" % [kind, what, value, " (dodged)" if is_dodge else "", hp.run.bg], "CompatProbe")
	if hidden:
		_check("Hue Potato hurt by a HIDDEN %s %s" % [kind, what], false)


func _check(what: String, ok: bool, detail: String = "") -> void:
	if ok:
		_probe_pass += 1
	else:
		_probe_fail += 1
	ModLoaderLog.info("PROBE %s: %s %s (pass %d / fail %d)" % ["PASS" if ok else "FAIL", what, detail, _probe_pass, _probe_fail], "CompatProbe")


func _process(_delta: float) -> void:
	var hp = Engine.get_meta("hue_potato") if Engine.has_meta("hue_potato") else null
	if hp == null or hp.run == null:
		return
	var run = hp.run
	var showcase: bool = _setting("mode", "test") == "showcase"
	if showcase and not _showcase_done:
		# Late-game look: every colour found.
		_showcase_done = true
		run.owned = _hue_data().wheel_order()
	_keep_alive()
	_spawn_hazards(hp)
	_capture()
	var now := OS.get_ticks_msec()
	if now < _probe_ms:
		return
	_probe_ms = now + int(float(_setting("cycle_s", 1.5)) * 1000)
	_probe_step += 1
	if _probe_step % 2 == 1:
		_switch(hp, run)
		return
	if showcase:
		return
	_check_enemies(run)
	_check_ring(run)
	_check_crates(hp, run)
	_check_bullets(run)
	if now >= _summary_ms:
		_summary_ms = now + 5000
		ModLoaderLog.info("PROBE hurt so far: %s, %d damage; ring hits %d; letter playing=%s queue=%d; hazards out=%d" % [_hurt, _hurt_damage, _ring_hits, hp.audio.is_letter_playing(), hp.audio._vo_queue.size(), _hazards_out(run)], "CompatProbe")


func _switch(hp, run) -> void:
	# Switch to the next colour (grey included), as Q/E would, and look for the colour wave.
	var choices: Array = ["grey"] + run.owned
	var next: String = choices[(_probe_step / 2) % choices.size()]
	run.set_bg(next)
	if _setting("mode", "test") == "showcase":
		return
	var waves := 0
	for child in get_children():
		if child.get_script() != null and child.get_script().resource_path.ends_with("hue_switch_wave.gd"):
			waves += 1
	if run.first_live_player() != null and next != "grey":
		_check("switch to %s shows the colour wave" % next, waves > 0 or not hp.opt("switch_wave"))


func _keep_alive() -> void:
	for pl in _players:
		if is_instance_valid(pl) and not pl.dead and pl.current_stats.health < pl.max_stats.health * 0.4:
			pl.heal(pl.max_stats.health)
			ModLoaderLog.info("PROBE healed Hue Potato (test only)", "CompatProbe")


func _spawn_hazards(hp) -> void:
	if not bool(_setting("spawn_hazards", false)) or hp.run.hazards == null:
		return
	var now := OS.get_ticks_msec()
	if now < _hazard_ms:
		return
	_hazard_ms = now + int(float(_setting("hazard_every_s", 6.0)) * 1000)
	var ids: Array = _hue_data().Sheets.HAZARDS_ORDER
	var id: String = ids[_hazard_turn % ids.size()]
	_hazard_turn += 1
	var node = hp.run.hazards.spawn(id)
	_check("probe spawned a %s" % id, node != null)


func _hazards_out(run) -> int:
	var n := 0
	for id in run.hazards._live:
		for node in run.hazards._live[id]:
			if is_instance_valid(node):
				n += 1
	return n


func _check_enemies(run) -> void:
	# Every coloured enemy must be hidden exactly when its colour is the background.
	var checked := 0
	var bad := 0
	for enemy in _entity_spawner.get_all_enemies():
		if not is_instance_valid(enemy) or enemy.dead:
			continue
		var tint = enemy.get_node_or_null("HueTint")
		if tint == null or tint.colour_id == "":
			continue
		checked += 1
		var should_hide: bool = tint.colour_id == run.bg
		var layer_ok: bool = ((enemy.collision_layer & 4) == 0) == should_hide
		var hurt_ok: bool = enemy._hurtbox._collision.disabled == should_hide
		var hit_ok: bool = (not should_hide) or enemy._hitbox._collision.disabled
		var alpha_ok: bool = (enemy.modulate.a < 0.5) == should_hide
		if not (layer_ok and hurt_ok and hit_ok and alpha_ok):
			bad += 1
			_check("enemy %s with bg %s" % [tint.colour_id, run.bg], false, "layer=%s hurtbox=%s hitbox=%s alpha=%s" % [layer_ok, hurt_ok, hit_ok, alpha_ok])
	if checked > 0:
		_check("%d coloured enemies hidden/shown correctly for bg %s" % [checked, run.bg], bad == 0)


func _check_ring(run) -> void:
	for pl in _players:
		if not is_instance_valid(pl) or pl.dead:
			continue
		for w in pl.current_weapons:
			if is_instance_valid(w) and "_beams" in w:
				for beam in w._beams:
					if not beam.hitbox.is_connected("hit_something", self, "_on_ring_hit"):
						beam.hitbox.connect("hit_something", self, "_on_ring_hit")
				var hidden_ok := true
				for beam in w._beams:
					if beam.colour == run.bg and not beam.hitbox._collision.disabled:
						hidden_ok = false
				_check("laser ring: %d beams for %d cannons, background beams harmless" % [w._beams.size(), w._row.emitters], w._beams.size() == w._row.emitters and hidden_ok)


func _check_crates(hp, run) -> void:
	var crates := 0
	var bad := 0
	for tree in _entity_spawner.neutrals:
		if not is_instance_valid(tree) or tree.dead:
			continue
		var crate = tree.get_node_or_null("HueCrate")
		if crate == null or crate.colour_id == "":
			if hp.opt("hue_crates"):
				bad += 1
			continue
		crates += 1
		var should_hide: bool = crate.colour_id == run.bg
		if tree._hurtbox._collision.disabled != should_hide or ((tree.collision_layer & 1) == 0) != should_hide:
			bad += 1
	if crates > 0 or bad > 0:
		_check("%d trees are Hue crates, hidden/shown correctly for bg %s" % [crates, run.bg], bad == 0)


func _check_bullets(run) -> void:
	var bullets := 0
	for p in _enemy_projectiles.get_children():
		if p.has_meta("hue_colour") and p.get_meta("hue_colour") == run.bg and p._hitbox.active:
			bullets += 1
			if not p._hitbox._collision.disabled:
				_check("hidden bullet has no hitbox", false)
	if bullets > 0:
		_check("%d bullets of the background colour are harmless" % bullets, true)


func _on_ring_hit(_thing, dmg) -> void:
	_ring_hits += 1
	_ring_damage += dmg


func _cap_worker(_u) -> void:
	while true:
		var _w = _cap_sem.wait()
		_cap_mutex.lock()
		var job = _cap_jobs.pop_front()
		_cap_mutex.unlock()
		if job == null:
			return
		job[0].save_png(job[1])


func _capture() -> void:
	var every := float(_setting("capture_every_s", 0.0))
	if every <= 0.0 or _cap_thread == null or get_tree().paused:
		return
	var now := OS.get_ticks_msec()
	if now < _cap_start_ms or now < _cap_next_ms or _cap_count >= int(_setting("capture_max", 150)):
		return
	_cap_next_ms = now + int(every * 1000)
	_cap_mutex.lock()
	var backlog := _cap_jobs.size()
	_cap_mutex.unlock()
	if backlog > 12:
		return
	var img := get_viewport().get_texture().get_data()
	img.flip_y()
	_cap_count += 1
	var path := "%s/w%02d_%04d.png" % [_cap_dir(), RunData.current_wave, _cap_count]
	_cap_mutex.lock()
	_cap_jobs.append([img, path])
	_cap_mutex.unlock()
	var _p = _cap_sem.post()
