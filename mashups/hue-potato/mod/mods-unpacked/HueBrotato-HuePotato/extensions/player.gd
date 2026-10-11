extends "res://entities/units/player/player.gd"

# Hue Potato: when he dies he gets Hue's own crossed-out eyes and Hue's death sound.


func die(args: = Utils.default_die_args) -> void:
	.die(args)
	var hp = Engine.get_meta("hue_potato") if Engine.has_meta("hue_potato") else null
	if hp == null or not hp.is_hue_character(RunData.get_player_character(player_index)):
		return
	hp.audio.play_sound("sfx_death")
	for texture in hp.dead_layer_textures():
		var eyes := Sprite.new()
		eyes.texture = texture
		_animation_node.add_child(eyes)
