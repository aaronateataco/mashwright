extends Node

# Hue Potato boot: a loose script next to Brotato.exe, started by override.cfg.
#
# Brotato's Steam build sets its built-in Godot Mod Loader (6.3) to read only subscribed Steam
# Workshop items, so mods installed in <game>/mods are never looked at. Autoloads added by
# override.cfg are created after the loader has finished, so this hands each zip in <game>/mods
# that the loader skipped to the loader's own setup path, one at a time:
# - zips the loader (or another boot script like this one) already loaded are skipped,
# - a mod already loaded from elsewhere (e.g. its Workshop copy) is not loaded twice,
# - mods the player disabled in the loader's options stay off.
# Builds that already read <game>/mods (no Workshop) are left alone. No game file is changed.

const LOG_NAME = "HuePotato:Boot"
const DONE_META = "mods_folder_boot_done"


func _init() -> void:
	if Engine.has_meta(DONE_META):
		return
	Engine.set_meta(DONE_META, true)
	if not ModLoaderStore.ml_options.enable_mods or not ModLoaderStore.ml_options.steam_workshop_enabled:
		return

	var mods_path: String = OS.get_executable_path().get_base_dir().plus_file("mods")
	var loaded_zips := {}
	for loaded_id in ModLoaderStore.mod_data:
		var loaded: ModData = ModLoaderStore.mod_data[loaded_id]
		if loaded.zip_path != "":
			loaded_zips[loaded.zip_path.get_file().to_lower()] = loaded_id

	var added := []
	for zip_name in _zips_in(mods_path):
		if loaded_zips.has(zip_name.to_lower()):
			ModLoaderLog.info("%s is already loaded as %s" % [zip_name, loaded_zips[zip_name.to_lower()]], LOG_NAME)
			continue
		var mod = _load_zip(mods_path.plus_file(zip_name))
		if mod != null:
			added.append(mod)

	for mod in added:
		# Returns true for a circular dependency; marks the mod not loadable if one is missing.
		var _is_circular: bool = _ModLoaderDependency.check_dependencies(mod)
		if not mod.is_loadable:
			ModLoaderLog.error("Skipping %s: missing dependencies" % mod.dir_name, LOG_NAME)
			continue
		if not mod.is_active:
			continue
		ModLoaderStore.mod_load_order.append(mod)
		ModLoaderLog.info("Initializing -> %s (from %s)" % [mod.manifest.get_mod_id(), mods_path], LOG_NAME)
		ModLoader._init_mod(mod)

	if not added.empty():
		ModLoaderLog.success("DONE: %s mod(s) from %s handed to the mod loader" % [added.size(), mods_path], LOG_NAME)


static func _zips_in(path: String) -> Array:
	var names := []
	var dir := Directory.new()
	if dir.open(path) != OK or dir.list_dir_begin(true) != OK:
		return names
	var name := dir.get_next()
	while name != "":
		if not dir.current_is_dir() and (name.get_extension() == "zip" or name.get_extension() == "pck"):
			names.append(name)
		name = dir.get_next()
	dir.list_dir_end()
	names.sort()
	return names


func _load_zip(zip_path: String):
	var unpacked: String = _ModLoaderPath.get_unpacked_mods_dir_path()
	var before: Array = _mod_dirs(unpacked)
	if not ProjectSettings.load_resource_pack(zip_path, false):
		ModLoaderLog.error("Could not open %s" % zip_path, LOG_NAME)
		return null
	var new_dirs := []
	var after: Array = _mod_dirs(unpacked)
	for dir_path in after:
		if not before.has(dir_path):
			new_dirs.append(dir_path)
	if new_dirs.empty():
		ModLoaderLog.info("%s adds no new mod folder (already loaded from elsewhere?)" % zip_path.get_file(), LOG_NAME)
		return null
	var mod_id: String = new_dirs[0].get_slice("/", 3)
	ModLoaderStore.previous_mod_dirs = after
	if ModLoaderStore.mod_data.has(mod_id) or mod_id in ModLoaderStore.ml_options.disabled_mods:
		return null
	ModLoader._init_mod_data(mod_id, zip_path)
	var mod: ModData = ModLoaderStore.mod_data[mod_id]
	mod.load_manifest()
	if not mod.is_loadable:
		ModLoaderLog.error("Skipping %s: it is not a loadable mod" % mod_id, LOG_NAME)
		return null
	if mod.manifest.get("config_schema") and not mod.manifest.config_schema.empty():
		mod.load_configs()
	return mod


# The loader's own helper logs an error naming mods-unpacked when that folder doesn't exist yet
# (no mod loaded so far), and Brotato's CrashReporter disables every mod after such an error.
static func _mod_dirs(unpacked: String) -> Array:
	if not Directory.new().dir_exists(unpacked):
		return []
	return _ModLoaderPath.get_dir_paths_in_dir(unpacked)
