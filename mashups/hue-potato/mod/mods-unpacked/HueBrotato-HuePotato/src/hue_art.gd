extends Reference

# Builds Brotato-shaped images from Hue's own images: potato-canvas layers (150x150), the
# character portrait and item icons (96x96). Pure image work, safe to run on a thread.

const POTATO_CANVAS = 150
const ICON_SIZE = 96
# Brotato's potato body sits at (45,38)-(104,107) on its 150x150 canvas.
const POTATO_BODY = Rect2(45, 38, 59, 69)
# Character portraits draw the potato at (11,6)-(84,90) on 96x96.
const ICON_BODY = Rect2(11, 6, 73, 84)


# Hue image placed on the potato canvas as a sheet layer row describes.
static func layer_image(src: Image, layer: Dictionary) -> Image:
	var img := _scaled(src, float(layer.width) / src.get_width())
	if layer.flip_x:
		img.flip_x()
	if layer.rotation_deg != 0:
		img = _rotated(img, deg2rad(layer.rotation_deg))
	_tint(img, Color8(layer.tint[0], layer.tint[1], layer.tint[2]))
	var canvas := Image.new()
	canvas.create(POTATO_CANVAS, POTATO_CANVAS, false, Image.FORMAT_RGBA8)
	var at := Vector2(layer.center_x - img.get_width() / 2.0, layer.center_y - img.get_height() / 2.0)
	canvas.blend_rect(img, Rect2(Vector2.ZERO, img.get_size()), at.round())
	return canvas


# Character portrait: Brotato's potato tinted dark, Hue's layers on top, a light rim so the dark
# silhouette reads on Brotato's dark panels.
static func portrait(potato: Image, body_tint: Color, layers: Array) -> Image:
	var scale: float = ICON_BODY.size.y / POTATO_BODY.size.y
	var full := Image.new()
	full.create(POTATO_CANVAS, POTATO_CANVAS, false, Image.FORMAT_RGBA8)
	var body: Image = potato.duplicate()
	if body.get_format() != Image.FORMAT_RGBA8:
		body.convert(Image.FORMAT_RGBA8)
	_tint(body, body_tint)
	full.blend_rect(body, Rect2(Vector2.ZERO, body.get_size()), Vector2.ZERO)
	for layer_img in layers:
		full.blend_rect(layer_img, Rect2(Vector2.ZERO, layer_img.get_size()), Vector2.ZERO)
	# Crop around the body (with room for hair above) and scale into the portrait box.
	var crop := Rect2(POTATO_BODY.position.x - 10, POTATO_BODY.position.y - 18, POTATO_BODY.size.x + 20, POTATO_BODY.size.y + 22)
	scale = min(scale, (ICON_SIZE - 2) / crop.size.y)
	var part := full.get_rect(crop)
	part.resize(int(crop.size.x * scale), int(crop.size.y * scale), Image.INTERPOLATE_BILINEAR)
	var icon := Image.new()
	icon.create(ICON_SIZE, ICON_SIZE, false, Image.FORMAT_RGBA8)
	var at := Vector2((ICON_SIZE - part.get_width()) / 2.0, ICON_SIZE - part.get_height() - 2)
	icon.blend_rect(part, Rect2(Vector2.ZERO, part.get_size()), at.round())
	return _outlined(icon, Color(0.92, 0.92, 0.92), 2)


# Item icon: Hue image cropped by region (fractions, y down), fitted into 96x96 with an outline in
# the opposite tone so black and white line art both read on Brotato's item frames.
static func item_icon(main: Image, region: Array, second: Image, tint: Color) -> Image:
	var r := Rect2(region[0] * main.get_width(), region[1] * main.get_height(), region[2] * main.get_width(), region[3] * main.get_height())
	var src := main.get_rect(r)
	src = _trimmed(src)
	var layers := [src]
	if second != null:
		second = second.duplicate()
		_colourize(second, tint)
		layers = [second, src]
	else:
		_tint(src, tint)
	var box := ICON_SIZE - 16
	var fit: float = min(float(box) / src.get_width(), float(box) / src.get_height())
	var icon := Image.new()
	icon.create(ICON_SIZE, ICON_SIZE, false, Image.FORMAT_RGBA8)
	for layer in layers:
		var scaled := _scaled(layer, fit)
		var at := Vector2((ICON_SIZE - scaled.get_width()) / 2.0, (ICON_SIZE - scaled.get_height()) / 2.0)
		icon.blend_rect(scaled, Rect2(Vector2.ZERO, scaled.get_size()), at.round())
	var dark: bool = _mean_luma(src) < 0.5
	return _outlined(icon, Color(0.95, 0.95, 0.95) if dark else Color(0.05, 0.05, 0.08), 3)


# Laser Ring icon: Hue's laser cannons at the corners of a triangle, each firing Hue's laser beam
# in one of Hue's colours at the next.
static func laser_ring_icon(beam: Image, canon: Image, mask: Image, colours: Array) -> Image:
	var icon := Image.new()
	icon.create(ICON_SIZE, ICON_SIZE, false, Image.FORMAT_RGBA8)
	var n := colours.size()
	var centre := Vector2(ICON_SIZE / 2.0, ICON_SIZE / 2.0 + 4.0)
	var corners := []
	for i in n:
		var a: float = -PI / 2.0 + TAU * i / n
		corners.append(centre + Vector2(cos(a), sin(a)) * 32.0)
	var strip := _trimmed(beam)
	for i in n:
		var from: Vector2 = corners[i]
		var to: Vector2 = corners[(i + 1) % n]
		var line := strip.duplicate()
		line.resize(int(from.distance_to(to)), 9, Image.INTERPOLATE_BILINEAR)
		_colourize(line, colours[i])
		line = _rotated(line, (to - from).angle())
		var at: Vector2 = (from + to) / 2.0 - line.get_size() / 2.0
		icon.blend_rect(line, Rect2(Vector2.ZERO, line.get_size()), at.round())
	var fit: float = 24.0 / canon.get_height()
	for i in n:
		var from: Vector2 = corners[i]
		var dir: Vector2 = (corners[(i + 1) % n] - from).normalized()
		var rim := _scaled(mask, fit)
		_colourize(rim, colours[i])
		rim = _rotated(rim, dir.angle() - PI / 2.0)
		var body := _rotated(_scaled(canon, fit), dir.angle() - PI / 2.0)
		icon.blend_rect(rim, Rect2(Vector2.ZERO, rim.get_size()), (from - rim.get_size() / 2.0).round())
		icon.blend_rect(body, Rect2(Vector2.ZERO, body.get_size()), (from - body.get_size() / 2.0).round())
	return _outlined(icon, Color(0.92, 0.92, 0.92), 2)


static func _scaled(src: Image, factor: float) -> Image:
	var img: Image = src.duplicate()
	if img.get_format() != Image.FORMAT_RGBA8:
		img.convert(Image.FORMAT_RGBA8)
	var w := int(max(1, round(img.get_width() * factor)))
	var h := int(max(1, round(img.get_height() * factor)))
	img.resize(w, h, Image.INTERPOLATE_BILINEAR)
	return img


static func _tint(img: Image, c: Color) -> void:
	if c == Color.white:
		return
	img.lock()
	for y in img.get_height():
		for x in img.get_width():
			var p := img.get_pixel(x, y)
			if p.a > 0.0:
				img.set_pixel(x, y, Color(p.r * c.r, p.g * c.g, p.b * c.b, p.a))
	img.unlock()


# Paints every visible pixel in c, keeping its alpha (for Hue's black silhouettes).
static func _colourize(img: Image, c: Color) -> void:
	img.lock()
	for y in img.get_height():
		for x in img.get_width():
			var p := img.get_pixel(x, y)
			if p.a > 0.0:
				img.set_pixel(x, y, Color(c.r, c.g, c.b, p.a))
	img.unlock()


static func _rotated(src: Image, angle: float) -> Image:
	var w := src.get_width()
	var h := src.get_height()
	var size := int(ceil(sqrt(w * w + h * h)))
	var out := Image.new()
	out.create(size, size, false, Image.FORMAT_RGBA8)
	src.lock()
	out.lock()
	var c := Vector2(size, size) / 2.0
	var sc := Vector2(w, h) / 2.0
	var ca := cos(-angle)
	var sa := sin(-angle)
	for y in size:
		for x in size:
			var d := Vector2(x + 0.5, y + 0.5) - c
			var s := Vector2(d.x * ca - d.y * sa, d.x * sa + d.y * ca) + sc
			var sx := int(floor(s.x))
			var sy := int(floor(s.y))
			if sx >= 0 and sy >= 0 and sx < w and sy < h:
				out.set_pixel(x, y, src.get_pixel(sx, sy))
	src.unlock()
	out.unlock()
	return out


# The same image with `px` of clear border, so an outline has room.
static func _padded(src: Image, px: int) -> Image:
	var img: Image = src.duplicate()
	if img.get_format() != Image.FORMAT_RGBA8:
		img.convert(Image.FORMAT_RGBA8)
	var out := Image.new()
	out.create(img.get_width() + px * 2, img.get_height() + px * 2, false, Image.FORMAT_RGBA8)
	out.blit_rect(img, Rect2(Vector2.ZERO, img.get_size()), Vector2(px, px))
	return out


static func _trimmed(src: Image) -> Image:
	var used := src.get_used_rect()
	if used.size.x <= 0 or used.size.y <= 0:
		return src
	return src.get_rect(used)


static func _mean_luma(img: Image) -> float:
	img.lock()
	var total := 0.0
	var n := 0
	for y in range(0, img.get_height(), 2):
		for x in range(0, img.get_width(), 2):
			var p := img.get_pixel(x, y)
			if p.a > 0.5:
				total += p.r * 0.3 + p.g * 0.59 + p.b * 0.11
				n += 1
	img.unlock()
	return total / n if n > 0 else 0.0


# Adds an outline of `colour`, `radius` px wide, around the opaque parts.
static func _outlined(src: Image, colour: Color, radius: int) -> Image:
	var w := src.get_width()
	var h := src.get_height()
	var out := Image.new()
	out.create(w, h, false, Image.FORMAT_RGBA8)
	src.lock()
	out.lock()
	for y in h:
		for x in w:
			var a := 0.0
			for dy in range(-radius, radius + 1):
				var yy: int = y + dy
				if yy < 0 or yy >= h:
					continue
				for dx in range(-radius, radius + 1):
					var xx: int = x + dx
					if xx < 0 or xx >= w or dx * dx + dy * dy > radius * radius:
						continue
					a = max(a, src.get_pixel(xx, yy).a)
			if a > 0.0:
				out.set_pixel(x, y, Color(colour.r, colour.g, colour.b, a))
	src.unlock()
	out.unlock()
	out.blend_rect(src, Rect2(0, 0, w, h), Vector2.ZERO)
	return out
