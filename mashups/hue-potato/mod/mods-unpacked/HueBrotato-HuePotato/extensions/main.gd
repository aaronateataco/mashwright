extends "res://main.gd"

# Hue Potato: each wave played as Hue Potato gets a Hue run controller (colour wheel, fragments,
# floor colour, region music). Godot 3 runs every level's _ready/_exit_tree itself, so the base
# versions are not called from here.

var _hue_run = null


func _ready() -> void:
	var hp = Engine.get_meta("hue_potato") if Engine.has_meta("hue_potato") else null
	if hp != null and hp.is_hue_run():
		_hue_run = hp.start_wave(self)


func _on_WaveTimer_timeout() -> void:
	if _hue_run != null and is_instance_valid(_hue_run):
		_hue_run.on_wave_ending()
	._on_WaveTimer_timeout()
