"""Minimal reader for GameMaker Studio 1.4 data files (data.win / game.unx / game.ios): sprites,
texture page items and texture pages. Reads the player's own copy; nothing is copied elsewhere."""
import struct
import sys


class GMData:
    def __init__(self, path):
        self.b = open(path, "rb").read()
        if self.b[:4] != b"FORM":
            raise ValueError("not a GameMaker data file")
        self.chunks = {}
        pos, end = 8, 8 + struct.unpack_from("<I", self.b, 4)[0]
        while pos < end:
            name = self.b[pos:pos + 4].decode("ascii")
            size = struct.unpack_from("<I", self.b, pos + 4)[0]
            self.chunks[name] = (pos + 8, size)
            pos += 8 + size

    def u32(self, o):
        return struct.unpack_from("<I", self.b, o)[0]

    def i32(self, o):
        return struct.unpack_from("<i", self.b, o)[0]

    def string(self, ptr):
        n = self.u32(ptr - 4)
        return self.b[ptr:ptr + n].decode("utf-8", "replace")

    def list_ptrs(self, chunk):
        start, _ = self.chunks[chunk]
        n = self.u32(start)
        return [self.u32(start + 4 + 4 * i) for i in range(n)]

    def sprites(self):
        out = {}
        for p in self.list_ptrs("SPRT"):
            name = self.string(self.u32(p))
            w, h = self.u32(p + 4), self.u32(p + 8)
            ox, oy = self.i32(p + 48), self.i32(p + 52)
            n = self.u32(p + 56)
            frames = [self.tpag(self.u32(p + 60 + 4 * i)) for i in range(n)]
            out[name] = {"w": w, "h": h, "ox": ox, "oy": oy, "frames": frames}
        return out

    def tpag(self, p):
        v = struct.unpack_from("<10hH", self.b, p)
        return dict(zip(["sx", "sy", "sw", "sh", "tx", "ty", "tw", "th", "bw", "bh", "page"], v))

    def textures(self):
        out = []
        for p in self.list_ptrs("TXTR"):
            off = self.u32(p + 4)
            # PNG length: scan to IEND
            end = self.b.index(b"IEND", off) + 8
            out.append((off, end - off))
        return out


if __name__ == "__main__":
    d = GMData(sys.argv[1])
    print("chunks:", list(d.chunks))
    sp = d.sprites()
    print(len(sp), "sprites;", len(d.textures()), "texture pages")
    pat = sys.argv[2] if len(sys.argv) > 2 else "dog"
    for k, v in sp.items():
        if pat in k.lower():
            print(k, v["w"], v["h"], "frames", len(v["frames"]), "origin", v["ox"], v["oy"])
