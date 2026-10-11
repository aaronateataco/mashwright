extends Reference

# Finds the player's own Hue install (its Hue_Data folder). Hue isn't in Melty's catalog, so the
# mod looks for it itself: an explicit path in user://huepotato.cfg, then Steam's library list
# (reached from Brotato's own Steam library, no registry, plus Steam's usual folders on Windows,
# Linux (native, Flatpak, Snap) and macOS), then common GOG/Epic/Heroic folders. Hue's Windows,
# Linux and macOS builds hold the same data.

const HUE_STEAM_APP_ID = "383270"
const CONFIG_PATH = "user://huepotato.cfg"

var tried := []


func find_hue_data() -> String:
	tried.clear()
	var cfg := ConfigFile.new()
	if cfg.load(CONFIG_PATH) == OK:
		var forced: String = cfg.get_value("hue", "data_dir", "")
		if forced != "":
			return forced if _is_hue_data(forced) else ""

	for lib in _steam_libraries():
		var dir := _steam_install_dir(lib)
		if dir != "" and _is_hue_data(dir):
			return dir

	var home := OS.get_environment("HOME")
	for dir in [
		home.plus_file("Games/Heroic/Hue/Hue_Data"),
		home.plus_file("GOG Games/Hue/Hue_Data"),
		"/Applications/Hue.app/Contents/Resources/Data",
		"C:/GOG Games/Hue/Hue_Data",
		"C:/Program Files (x86)/GOG Galaxy/Games/Hue/Hue_Data",
		"C:/Program Files/Epic Games/Hue/Hue_Data",
		"D:/GOG Games/Hue/Hue_Data",
		"D:/Epic Games/Hue/Hue_Data",
	]:
		if _is_hue_data(dir):
			return dir
	return ""


func _is_hue_data(dir: String) -> bool:
	tried.append(dir)
	var f := File.new()
	if not (f.file_exists(dir.plus_file("resources.assets")) and f.file_exists(dir.plus_file("sharedassets0.assets"))):
		return false
	var game_dir := dir.get_base_dir()
	for exe in ["Hue.exe", "Hue.x86_64", "Hue.x86"]:
		if f.file_exists(game_dir.plus_file(exe)):
			return true
	# macOS: Hue.app/Contents/Resources/Data
	return dir.ends_with("Contents/Resources/Data")


func _steam_install_dir(lib: String) -> String:
	var acf := lib.plus_file("steamapps/appmanifest_%s.acf" % HUE_STEAM_APP_ID)
	var installdir := "Hue"
	var text := _read_text(acf)
	if text != "":
		var v := _vdf_value(text, "installdir")
		if v != "":
			installdir = v
	var game := lib.plus_file("steamapps/common").plus_file(installdir)
	if OS.get_name() == "OSX":
		return game.plus_file("Hue.app/Contents/Resources/Data")
	return game.plus_file("Hue_Data")


func _steam_libraries() -> Array:
	var libs := []
	# Brotato.exe lives in <library>/steamapps/common/Brotato.
	var exe_dir := OS.get_executable_path().get_base_dir()
	var brotato_lib := exe_dir.get_base_dir().get_base_dir().get_base_dir()
	_add_unique(libs, brotato_lib)

	var steam_dirs := []
	var launcher := _vdf_value(_read_text(brotato_lib.plus_file("libraryfolder.vdf")), "launcher")
	if launcher != "":
		_add_unique(steam_dirs, launcher.replace("\\", "/").get_base_dir())
	_add_unique(steam_dirs, brotato_lib)
	var pf86 := OS.get_environment("ProgramFiles(x86)").replace("\\", "/")
	if pf86 != "":
		_add_unique(steam_dirs, pf86.plus_file("Steam"))
	_add_unique(steam_dirs, "C:/Program Files (x86)/Steam")
	_add_unique(steam_dirs, "C:/Program Files/Steam")
	var home := OS.get_environment("HOME")
	if home != "":
		for rel in [".steam/steam", ".steam/root", ".local/share/Steam",
				".var/app/com.valvesoftware.Steam/.local/share/Steam",
				".var/app/com.valvesoftware.Steam/data/Steam",
				"snap/steam/common/.local/share/Steam", "Library/Application Support/Steam"]:
			_add_unique(steam_dirs, home.plus_file(rel))

	for steam_dir in steam_dirs:
		var text := _read_text(steam_dir.plus_file("steamapps/libraryfolders.vdf"))
		if text == "":
			continue
		_add_unique(libs, steam_dir)
		for path in _vdf_values(text, "path"):
			_add_unique(libs, path.replace("\\\\", "/").replace("\\", "/"))
	return libs


static func _add_unique(arr: Array, v: String) -> void:
	if v != "" and not arr.has(v):
		arr.append(v)


static func _read_text(path: String) -> String:
	var f := File.new()
	if not f.file_exists(path) or f.open(path, File.READ) != OK:
		return ""
	var t := f.get_as_text()
	f.close()
	return t


static func _vdf_value(text: String, key: String) -> String:
	var values := _vdf_values(text, key)
	return values[0] if values.size() > 0 else ""


static func _vdf_values(text: String, key: String) -> Array:
	var out := []
	var re := RegEx.new()
	re.compile("\"" + key + "\"\\s+\"([^\"]*)\"")
	for m in re.search_all(text):
		out.append(m.get_string(1))
	return out
