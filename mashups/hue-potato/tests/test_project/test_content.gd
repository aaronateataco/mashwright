extends Node

# Headless test of the content loader: finds Hue, reads and composes the art, decodes audio with the
# bundled vgmstream. Run as the main scene: godot --no-window --path . res://test_content.tscn
# args after "--": <vgmstream exe> <out dir>

const Content = preload("res://mods-unpacked/HueBrotato-HuePotato/src/hue_content.gd")

var content
var out_dir := ""
var want := ["snd_wheel_1", "snd_fragment", "mus_village", "vo_orange", "vo_intro", "mus_drgrey", "snd_laser_on", "snd_crate_1", "snd_boulder_roll"]
var got := 0
var t0 := 0


func _ready() -> void:
	var args := OS.get_cmdline_args()
	out_dir = args[args.size() - 1]
	content = Content.new()
	add_child(content)
	content.connect("art_ready", self, "_on_art")
	content.connect("audio_ready", self, "_on_audio")
	t0 = OS.get_ticks_msec()
	content.start()
	content._vgmstream = args[args.size() - 2]


func _on_art(ok: bool) -> void:
	print("art ready=", ok, " state=", content.state, " in ", OS.get_ticks_msec() - t0, " ms; hue at ", content.hue_data, " error=", content.error)
	if not ok:
		get_tree().quit(1)
		return
	content.portrait_image.save_png(out_dir.plus_file("portrait.png"))
	content.weapon_icon_image.save_png(out_dir.plus_file("weapon_laser_ring.png"))
	for id in ["tex_laser_beam", "tex_laser_canon", "tex_laser_canon_mask", "spr_crate", "tex_skull_boulder", "spr_dr_grey", "tex_dot_particle"]:
		content.images[id].save_png(out_dir.plus_file(id + ".png"))
	for id in content.layer_images:
		content.layer_images[id].save_png(out_dir.plus_file("layer_" + id + ".png"))
	for id in content.item_icon_images:
		content.item_icon_images[id].save_png(out_dir.plus_file("icon_" + id + ".png"))
	print("VO/Orange0 en: ", content.hue_text("VO/Orange0"))
	TranslationServer.set_locale("fr")
	print("VO/Orange0 fr: ", content.hue_text("VO/Orange0"))
	TranslationServer.set_locale("en")
	for id in want:
		content.request_audio(id)


func _on_audio(id: String) -> void:
	if not want.has(id):
		return
	var s: AudioStreamSample = content.streams[id]
	print("audio ", id, ": ", s.get_length(), " s, ", s.mix_rate, " Hz, stereo=", s.stereo)
	got += 1
	if got == want.size():
		print("all audio decoded in ", OS.get_ticks_msec() - t0, " ms")
		get_tree().quit(0)
