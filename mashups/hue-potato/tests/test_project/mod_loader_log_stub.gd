extends Node

# Stand-in for Godot Mod Loader's ModLoaderLog so mod scripts compile in the headless test project.

func info(msg, _name = "") -> void:
	print("[info] ", msg)


func success(msg, _name = "") -> void:
	print("[ok] ", msg)


func warning(msg, _name = "") -> void:
	print("[warn] ", msg)


func error(msg, _name = "") -> void:
	print("[error] ", msg)
