"""Look inside a mashup's components and work out which platforms their binaries are for, then fit
the install to the game actually installed (native Linux, Windows, Proton, macOS...).

Every file in a component archive is classified by its magic bytes: Windows PE (.exe/.dll), Linux ELF,
macOS Mach-O (incl. universal), or platform-neutral (scripts, data, Godot/Unity mods, textures...).
A component is "neutral" (no binaries), single-platform, or a hybrid carrying builds for several.
"""

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Set

PE, ELF, MACHO = "windows", "linux", "macos"
MACHO_MAGIC = {b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"}
# Windows DLLs that games load from their own folder, used by mod loaders (BepInEx, ASI loaders...).
PROXY_DLLS = {"winhttp.dll", "version.dll", "dinput8.dll", "winmm.dll", "d3d9.dll", "d3d11.dll", "dxgi.dll",
              "dsound.dll", "xinput1_3.dll", "xinput1_4.dll", "msvcp140.dll"}
OS_DIR_HINTS = {
    "windows": re.compile(r"(^|/)(win(dows)?|win32|win64|x64|x86)(/|$)", re.I),
    "linux": re.compile(r"(^|/)(linux(64|32)?|lin)(/|$)", re.I),
    "macos": re.compile(r"(^|/)(mac(os)?|osx|darwin)(/|$)", re.I),
}


def classify(head: bytes) -> Optional[str]:
    """Platform of a binary from its first bytes, or None for non-binaries."""
    if head[:4] == b"\x7fELF":
        return ELF
    if head[:4] in MACHO_MAGIC:
        # 0xCAFEBABE is also a Java class file; universal binaries have a small arch count next.
        if head[:4] == b"\xca\xfe\xba\xbe" and len(head) >= 8 and int.from_bytes(head[4:8], "big") > 30:
            return None
        return MACHO
    if head[:2] == b"MZ":
        return PE
    return None


@dataclass
class ComponentReport:
    id: str
    platforms: Set[str] = field(default_factory=set)      # platforms with binaries
    by_platform: Dict[str, List[str]] = field(default_factory=dict)
    os_folders: Dict[str, str] = field(default_factory=dict)  # platform -> folder holding only that platform's binaries
    proxy_dlls: List[str] = field(default_factory=list)
    nested: List[str] = field(default_factory=list)       # archives inside the archive (scanned too)

    @property
    def kind(self) -> str:
        if not self.platforms:
            return "neutral"
        return "hybrid" if len(self.platforms) > 1 else "single"

    def to_json(self) -> dict:
        return {"id": self.id, "kind": self.kind, "platforms": sorted(self.platforms),
                "binaries": {k: v[:20] for k, v in self.by_platform.items()},
                "os_folders": self.os_folders, "proxy_dlls": self.proxy_dlls, "nested": self.nested}


def _scan_zip(z: zipfile.ZipFile, rep: ComponentReport, prefix: str = "", depth: int = 0) -> None:
    for info in z.infolist():
        if info.is_dir():
            continue
        name = prefix + info.filename.replace("\\", "/")
        with z.open(info) as f:
            head = f.read(16)
        plat = classify(head)
        if plat:
            rep.platforms.add(plat)
            rep.by_platform.setdefault(plat, []).append(name)
            if plat == PE and PurePosixPath(name).name.lower() in PROXY_DLLS and PurePosixPath(name).parent.name in ("", "."):
                rep.proxy_dlls.append(name)
        elif head[:4] == b"PK\x03\x04" and depth < 2 and info.file_size < (512 << 20):
            rep.nested.append(name)
            import io
            with z.open(info) as f:
                try:
                    with zipfile.ZipFile(io.BytesIO(f.read())) as inner:
                        _scan_zip(inner, rep, name + "!/", depth + 1)
                except zipfile.BadZipFile:
                    pass


def analyze_component(path: Path, comp_id: str, extract: bool = True) -> ComponentReport:
    rep = ComponentReport(comp_id)
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                _scan_zip(z, rep)
        else:
            with open(path, "rb") as f:
                plat = classify(f.read(16))
            if plat:
                rep.platforms.add(plat)
                rep.by_platform[plat] = [path.name]
    except OSError:
        pass
    # Hybrids often keep each platform's build in its own folder (win64/, linux/, macos/...).
    for plat, files in rep.by_platform.items():
        dirs = {str(PurePosixPath(f.split("!/")[-1]).parent) for f in files}
        hint = OS_DIR_HINTS[plat]
        if dirs and all(hint.search(d + "/") for d in dirs):
            common = _common_dir(sorted(dirs))
            if common:
                rep.os_folders[plat] = common
    return rep


def _common_dir(dirs: List[str]) -> str:
    parts = [d.split("/") for d in dirs]
    out = []
    for segs in zip(*parts):
        if len(set(segs)) != 1:
            break
        out.append(segs[0])
    return "/".join(out)


def analyze(recipe: dict, mashup_dir) -> Dict[str, ComponentReport]:
    d = Path(mashup_dir)
    return {c["id"]: analyze_component(d / c["file"], c["id"], c.get("extract", True))
            for c in recipe.get("components", []) if (d / c["file"]).is_file()}


def game_binary_platform(game) -> str:
    """What the installed game's own executables are built for."""
    if game.runner in ("proton", "wine"):
        return PE
    return game.platform


def fit(recipe: dict, reports: Dict[str, ComponentReport], primary, host_os: str) -> dict:
    """How the components fit the chosen game, and what Mashwright adjusts automatically.

    Returns {"status": "ok"|"adjusted"|"warning"|"blocked", "notes": [...], "skip": [paths inside
    components not to install], "advice": [...]}.
    """
    want = game_binary_platform(primary) if primary else host_os
    notes, advice, skip = [], [], []
    status = "ok"
    for cid, rep in reports.items():
        if rep.kind == "neutral":
            continue
        if want in rep.platforms:
            if rep.kind == "hybrid":
                # Only the build for this game is needed; others are left out where they sit in their own folders.
                for plat, folder in rep.os_folders.items():
                    if plat != want and folder:
                        skip.append(f"{cid}:{folder}")
                notes.append(f"{cid}: carries {', '.join(sorted(rep.platforms))} builds; using the {want} one")
                status = "adjusted" if status == "ok" else status
            continue
        # The component has binaries, but none for this game's platform.
        have = ", ".join(sorted(rep.platforms))
        if want == ELF and rep.platforms == {PE}:
            if primary is not None and primary.runner == "native":
                notes.append(f"{cid}: has only Windows binaries ({', '.join(rep.by_platform[PE][:3])}) but "
                             f"{primary.title} is the native Linux build")
                advice.append(f"Run {primary.title} through Proton (Steam: Properties → Compatibility → force Proton), "
                              "then rescan; Windows-only parts that the game itself loads need the Windows build.")
                status = "warning"
            continue
        notes.append(f"{cid}: has {have} binaries, none for {want}")
        status = "warning"
    if primary is not None and primary.runner in ("proton", "wine"):
        for rep in reports.values():
            for dll in rep.proxy_dlls:
                base = PurePosixPath(dll).stem.lower()
                advice.append(f'{dll} is a DLL loader: add WINEDLLOVERRIDES="{base}=n,b" %command% to the '
                              "game's launch options so Proton loads it")
                status = "warning" if status in ("ok", "adjusted") else status
    if primary is not None and primary.runner == "native" and primary.platform == MACHO:
        for cid, rep in reports.items():
            if rep.platforms and MACHO not in rep.platforms:
                advice.append(f"{cid}: no macOS build inside; it may not work on Mac")
    return {"status": status, "target": want, "notes": notes, "advice": list(dict.fromkeys(advice)),
            "skip": skip, "components": {k: v.to_json() for k, v in reports.items()}}
