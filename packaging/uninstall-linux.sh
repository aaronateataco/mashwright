#!/bin/sh
# Remove Mashwright's app files, command and menu entry. Your library and install records in
# ~/.local/share/mashwright are kept unless you pass --all (uninstall your mashups first!).
set -eu
DATA=${XDG_DATA_HOME:-$HOME/.local/share}
rm -rf "$DATA/mashwright/app"
rm -f "$HOME/.local/bin/mashwright" "$DATA/applications/io.github.mashwright.Mashwright.desktop" "$DATA/icons/hicolor/scalable/apps/io.github.mashwright.Mashwright.svg"
if [ "${1:-}" = "--all" ]; then
    if [ -n "$(ls -A "$DATA/mashwright/installed" 2>/dev/null)" ]; then
        echo "Some mashups are still installed in your games; run 'mashwright uninstall <id>' first." >&2
        exit 1
    fi
    rm -rf "$DATA/mashwright" "${XDG_CONFIG_HOME:-$HOME/.config}/mashwright"
fi
echo "Mashwright removed."
