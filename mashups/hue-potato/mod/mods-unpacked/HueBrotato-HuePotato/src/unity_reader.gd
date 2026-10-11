extends Reference

# Minimal reader for the Unity 5.x serialized files Hue ships (format 15, no type trees,
# little-endian data). It reads the object table and externals, and the few fields the mod needs
# from Texture2D, Sprite, AudioClip and TextAsset objects, using Unity 5.3's field layouts.

const CLASS_TEXTURE2D = 28
const CLASS_TEXT_ASSET = 49
const CLASS_AUDIO_CLIP = 83
const CLASS_SPRITE = 213

var path := ""
var data_dir := ""
var version := 0
var objects := {}    # path_id -> [absolute byte start, byte size, class id]
var externals := []  # file names; a PPtr's fileID n refers to externals[n - 1]
var error := ""


func open(p_path: String) -> bool:
	path = p_path
	data_dir = p_path.get_base_dir()
	var f := File.new()
	if f.open(path, File.READ) != OK:
		error = "cannot open " + path
		return false
	f.endian_swap = true  # the header is big-endian
	var metadata_size := f.get_32()
	var _file_size := f.get_32()
	version = f.get_32()
	var data_offset := f.get_32()
	var big_endian := f.get_8() != 0
	f.get_buffer(3)
	if version < 14 or version > 15:
		error = "unsupported serialized format %d" % version
		f.close()
		return false
	var meta := f.get_buffer(metadata_size)
	f.close()

	var b := StreamPeerBuffer.new()
	b.data_array = meta
	b.big_endian = big_endian
	var _unity_version := _cstr(b)
	var _platform := b.get_32()
	var type_tree := b.get_8() != 0
	if type_tree:
		error = "type trees are not supported"
		return false
	var type_count := b.get_32()
	for _i in type_count:
		var class_id := b.get_32()
		if class_id < 0:
			b.get_data(16)  # script id
		b.get_data(16)  # old type hash

	var object_count := b.get_32()
	for _i in object_count:
		_align(b)
		var path_id := b.get_64()
		var byte_start := b.get_u32()
		var byte_size := b.get_u32()
		var _type_id := b.get_32()
		var class_id := b.get_u16()
		var _script_index := b.get_16()
		if version >= 15:
			b.get_8()  # stripped
		objects[path_id] = [data_offset + byte_start, byte_size, class_id]

	var script_count := b.get_32()
	for _i in script_count:
		b.get_32()
		_align(b)
		b.get_64()

	var external_count := b.get_32()
	for _i in external_count:
		_cstr(b)
		b.get_data(16)
		b.get_32()
		externals.append(_cstr(b).get_file())
	return true


func external_file(file_id: int) -> String:
	if file_id == 0:
		return path.get_file()
	return externals[file_id - 1]


func read_object(path_id: int, expected_class: int) -> StreamPeerBuffer:
	if not objects.has(path_id):
		error = "no object %d in %s" % [path_id, path.get_file()]
		return null
	var o: Array = objects[path_id]
	if o[2] != expected_class:
		error = "object %d is class %d, expected %d" % [path_id, o[2], expected_class]
		return null
	var f := File.new()
	if f.open(path, File.READ) != OK:
		error = "cannot open " + path
		return null
	f.seek(o[0])
	var bytes := f.get_buffer(o[1])
	f.close()
	var b := StreamPeerBuffer.new()
	b.data_array = bytes
	return b


# Texture2D -> {name, width, height, format, data}
func read_texture(path_id: int) -> Dictionary:
	var b := read_object(path_id, CLASS_TEXTURE2D)
	if b == null:
		return {}
	var t := {}
	t.name = _astr(b)
	t.width = b.get_32()
	t.height = b.get_32()
	var _complete_size := b.get_32()
	t.format = b.get_32()
	var _mips := b.get_32()
	b.get_8()  # is readable
	b.get_8()  # read allowed
	_align(b)
	var _image_count := b.get_32()
	var _dimension := b.get_32()
	b.get_data(16)  # filter mode, aniso, mip bias, wrap mode
	var _lightmap_format := b.get_32()
	var _color_space := b.get_32()
	var inline_size := b.get_32()
	if inline_size > 0:
		t.data = b.get_data(inline_size)[1]
		return t
	_align(b)
	var offset := b.get_u32()
	var size := b.get_u32()
	var stream_path := _astr(b)
	t.data = _read_range(data_dir.plus_file(stream_path.get_file()), offset, size)
	if t.data.size() != size:
		error = "short read from " + stream_path
		return {}
	return t


# Sprite -> {name, texture_file_id, texture_path_id, rect (Unity texture coords, y up), rotation}
func read_sprite(path_id: int) -> Dictionary:
	var b := read_object(path_id, CLASS_SPRITE)
	if b == null:
		return {}
	var s := {}
	s.name = _astr(b)
	b.get_data(52)  # rect, offset, border, pixels-to-units, extrude, is-polygon (+align)
	s.texture_file_id = b.get_32()
	s.texture_path_id = b.get_64()
	var size := b.get_size()
	b.seek(size - 44)
	var x := b.get_float()
	var y := b.get_float()
	var w := b.get_float()
	var h := b.get_float()
	s.rect = Rect2(x, y, w, h)
	b.get_float()
	b.get_float()
	var settings := b.get_u32()
	s.rotation = (settings >> 2) & 0xF
	return s


# AudioClip -> {name, channels, frequency, length, source, offset, size, compression}
func read_audio_clip(path_id: int) -> Dictionary:
	var b := read_object(path_id, CLASS_AUDIO_CLIP)
	if b == null:
		return {}
	var a := {}
	a.name = _astr(b)
	var _load_type := b.get_32()
	a.channels = b.get_32()
	a.frequency = b.get_32()
	var _bits := b.get_32()
	a.length = b.get_float()
	b.get_8()  # is tracker format
	_align(b)
	var _subsound := b.get_32()
	b.get_8()
	b.get_8()
	b.get_8()
	_align(b)
	a.source = _astr(b)
	a.offset = b.get_64()
	a.size = b.get_64()
	a.compression = b.get_32()
	return a


func read_audio_bytes(clip: Dictionary) -> PoolByteArray:
	return _read_range(data_dir.plus_file(clip.source.get_file()), clip.offset, clip.size)


# TextAsset -> String (UTF-8)
func read_text_asset(path_id: int) -> String:
	var b := read_object(path_id, CLASS_TEXT_ASSET)
	if b == null:
		return ""
	var _name := _astr(b)
	var n := b.get_32()
	return b.get_data(n)[1].get_string_from_utf8()


static func _read_range(file_path: String, offset: int, size: int) -> PoolByteArray:
	var f := File.new()
	if f.open(file_path, File.READ) != OK:
		return PoolByteArray()
	f.seek(offset)
	var bytes := f.get_buffer(size)
	f.close()
	return bytes


static func _align(b: StreamPeerBuffer) -> void:
	var pos := b.get_position()
	var pad := (4 - pos % 4) % 4
	if pad > 0:
		b.seek(pos + pad)


static func _cstr(b: StreamPeerBuffer) -> String:
	var bytes := PoolByteArray()
	while b.get_position() < b.get_size():
		var c := b.get_u8()
		if c == 0:
			break
		bytes.append(c)
	return bytes.get_string_from_utf8()


static func _astr(b: StreamPeerBuffer) -> String:
	var n := b.get_32()
	var s: String = b.get_data(n)[1].get_string_from_utf8() if n > 0 else ""
	_align(b)
	return s
