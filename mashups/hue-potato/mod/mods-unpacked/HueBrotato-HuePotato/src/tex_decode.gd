extends Reference

# Decodes Unity texture data (as stored in Hue's files) into Godot Images. Only the region a
# sprite needs is decoded. Unity stores rows bottom-up, so regions are given in Unity's
# coordinates (y up) and the result is flipped to Godot's top-down rows.

const FMT_ALPHA8 = 1
const FMT_RGB24 = 3
const FMT_RGBA32 = 4
const FMT_ARGB32 = 5
const FMT_DXT1 = 10
const FMT_DXT5 = 12


static func supported(fmt: int) -> bool:
	return fmt in [FMT_ALPHA8, FMT_RGB24, FMT_RGBA32, FMT_ARGB32, FMT_DXT1, FMT_DXT5]


# Returns an RGBA8 Image of `rect` (Unity coords) from a texture dict {width, height, format, data}.
# step > 1 samples every step-th pixel (cheap downscale for big soft textures).
static func decode_region(tex: Dictionary, rect: Rect2, step: int = 1) -> Image:
	var w: int = tex.width
	var h: int = tex.height
	var x0 := int(clamp(floor(rect.position.x), 0, w))
	var y0 := int(clamp(floor(rect.position.y), 0, h))
	var x1 := int(clamp(ceil(rect.end.x), 0, w))
	var y1 := int(clamp(ceil(rect.end.y), 0, h))
	var ow := int(ceil(float(x1 - x0) / step))
	var oh := int(ceil(float(y1 - y0) / step))
	if ow <= 0 or oh <= 0:
		return null
	var out := PoolByteArray()
	out.resize(ow * oh * 4)
	var fmt: int = tex.format
	if fmt == FMT_DXT1 or fmt == FMT_DXT5:
		out = _decode_blocks(tex.data, w, fmt, x0, y0, x1, y1, step, out, ow)
	else:
		out = _decode_linear(tex.data, w, fmt, x0, y0, x1, y1, step, out, ow)
	var img := Image.new()
	img.create_from_data(ow, oh, false, Image.FORMAT_RGBA8, out)
	img.flip_y()
	return img


static func decode_full(tex: Dictionary, step: int = 1) -> Image:
	return decode_region(tex, Rect2(0, 0, tex.width, tex.height), step)


static func _decode_linear(data: PoolByteArray, w: int, fmt: int, x0: int, y0: int, x1: int, y1: int, step: int, out: PoolByteArray, ow: int) -> PoolByteArray:
	var bpp: int = 4
	if fmt == FMT_ALPHA8:
		bpp = 1
	elif fmt == FMT_RGB24:
		bpp = 3
	var oy: int = 0
	var y: int = y0
	while y < y1:
		var ox: int = 0
		var x: int = x0
		var row: int = y * w
		while x < x1:
			var s: int = (row + x) * bpp
			var d: int = (oy * ow + ox) * 4
			if fmt == FMT_ARGB32:
				out[d] = data[s + 1]
				out[d + 1] = data[s + 2]
				out[d + 2] = data[s + 3]
				out[d + 3] = data[s]
			elif fmt == FMT_RGBA32:
				out[d] = data[s]
				out[d + 1] = data[s + 1]
				out[d + 2] = data[s + 2]
				out[d + 3] = data[s + 3]
			elif fmt == FMT_RGB24:
				out[d] = data[s]
				out[d + 1] = data[s + 1]
				out[d + 2] = data[s + 2]
				out[d + 3] = 255
			else:
				out[d] = 255
				out[d + 1] = 255
				out[d + 2] = 255
				out[d + 3] = data[s]
			ox += 1
			x += step
		oy += 1
		y += step
	return out


static func _decode_blocks(data: PoolByteArray, w: int, fmt: int, x0: int, y0: int, x1: int, y1: int, step: int, out: PoolByteArray, ow: int) -> PoolByteArray:
	var block_bytes: int = 16 if fmt == FMT_DXT5 else 8
	var blocks_wide: int = int((w + 3) / 4)
	var colours := PoolIntArray()
	colours.resize(16)
	var alphas := PoolIntArray()
	alphas.resize(16)
	for by in range(int(y0 / 4), int((y1 + 3) / 4)):
		for bx in range(int(x0 / 4), int((x1 + 3) / 4)):
			var o: int = (by * blocks_wide + bx) * block_bytes
			if o + block_bytes > data.size():
				continue
			var c: int = o
			if fmt == FMT_DXT5:
				alphas = _dxt5_alpha(data, o, alphas)
				c = o + 8
			colours = _dxt_colours(data, c, fmt == FMT_DXT1, colours)
			for py in 4:
				var y: int = by * 4 + py
				if y < y0 or y >= y1 or (y - y0) % step != 0:
					continue
				for px in 4:
					var x: int = bx * 4 + px
					if x < x0 or x >= x1 or (x - x0) % step != 0:
						continue
					var i: int = py * 4 + px
					var rgba: int = colours[i]
					var d: int = (int((y - y0) / step) * ow + int((x - x0) / step)) * 4
					out[d] = (rgba >> 24) & 0xFF
					out[d + 1] = (rgba >> 16) & 0xFF
					out[d + 2] = (rgba >> 8) & 0xFF
					out[d + 3] = alphas[i] if fmt == FMT_DXT5 else (rgba & 0xFF)
	return out


# 16 colours as 0xRRGGBBAA for one DXT colour block.
static func _dxt_colours(data: PoolByteArray, o: int, dxt1: bool, out: PoolIntArray) -> PoolIntArray:
	var c0: int = data[o] | (data[o + 1] << 8)
	var c1: int = data[o + 2] | (data[o + 3] << 8)
	var p := []
	p.resize(4)
	var r0: int = ((c0 >> 11) & 31) * 255 / 31
	var g0: int = ((c0 >> 5) & 63) * 255 / 63
	var b0: int = (c0 & 31) * 255 / 31
	var r1: int = ((c1 >> 11) & 31) * 255 / 31
	var g1: int = ((c1 >> 5) & 63) * 255 / 63
	var b1: int = (c1 & 31) * 255 / 31
	p[0] = (r0 << 24) | (g0 << 16) | (b0 << 8) | 255
	p[1] = (r1 << 24) | (g1 << 16) | (b1 << 8) | 255
	if c0 > c1 or not dxt1:
		p[2] = (((2 * r0 + r1) / 3) << 24) | (((2 * g0 + g1) / 3) << 16) | (((2 * b0 + b1) / 3) << 8) | 255
		p[3] = (((r0 + 2 * r1) / 3) << 24) | (((g0 + 2 * g1) / 3) << 16) | (((b0 + 2 * b1) / 3) << 8) | 255
	else:
		p[2] = (((r0 + r1) / 2) << 24) | (((g0 + g1) / 2) << 16) | (((b0 + b1) / 2) << 8) | 255
		p[3] = 0
	var bits: int = data[o + 4] | (data[o + 5] << 8) | (data[o + 6] << 16) | (data[o + 7] << 24)
	for i in 16:
		out[i] = p[(bits >> (2 * i)) & 3]
	return out


static func _dxt5_alpha(data: PoolByteArray, o: int, out: PoolIntArray) -> PoolIntArray:
	var a0: int = data[o]
	var a1: int = data[o + 1]
	var t := []
	t.resize(8)
	t[0] = a0
	t[1] = a1
	if a0 > a1:
		for i in range(1, 7):
			t[i + 1] = ((7 - i) * a0 + i * a1) / 7
	else:
		for i in range(1, 5):
			t[i + 1] = ((5 - i) * a0 + i * a1) / 5
		t[6] = 0
		t[7] = 255
	var bits: int = 0
	for i in 6:
		bits |= data[o + 2 + i] << (8 * i)
	for i in 16:
		out[i] = t[(bits >> (3 * i)) & 7]
	return out
