#!/bin/sh
# Install Mashwright for the current user (no sudo): app in ~/.local/share/mashwright/app,
# a `mashwright` command in ~/.local/bin, and a menu entry with its icon. Safe to run again.
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
DATA=${XDG_DATA_HOME:-$HOME/.local/share}
APP="$DATA/mashwright/app"
BIN="$HOME/.local/bin"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Mashwright needs python3 (Fedora: sudo dnf install python3)." >&2
    exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
    echo "Mashwright needs Python 3.9 or newer." >&2
    exit 1
fi

mkdir -p "$APP" "$BIN" "$DATA/applications" "$DATA/icons/hicolor/scalable/apps"
rm -rf "$APP/mashwright"
cp -R "$HERE/mashwright" "$APP/"
cp "$HERE/mashwright.py" "$HERE/LICENSE" "$HERE/NOTICE.md" "$HERE/README.md" "$APP/"
[ -d "$HERE/examples" ] && rm -rf "$APP/examples" && cp -R "$HERE/examples" "$APP/"

cat > "$BIN/mashwright" <<LAUNCH
#!/bin/sh
exec python3 "$APP/mashwright.py" "\$@"
LAUNCH
chmod 755 "$BIN/mashwright"

ID=io.github.mashwright.Mashwright
cp "$HERE/packaging/mashwright.svg" "$DATA/icons/hicolor/scalable/apps/$ID.svg"
sed "s|@BIN@|$BIN|g" "$HERE/packaging/mashwright.desktop" > "$DATA/applications/$ID.desktop"
chmod 644 "$DATA/applications/$ID.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA/applications" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q "$DATA/icons/hicolor" >/dev/null 2>&1 || true

echo "Mashwright installed. Open it from your app menu, or run: mashwright"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "(Add $BIN to your PATH to use the mashwright command.)";; esac
echo
echo "Optional extras:"
echo "  Android games:  sudo dnf install android-tools          (adb)"
echo "  iOS games:      sudo dnf install libimobiledevice-utils ifuse"
