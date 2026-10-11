#!/bin/sh
# Double-click to start Mashwright on macOS (needs python3: Xcode command line tools or python.org).
cd "$(dirname "$0")/.." && exec python3 mashwright.py "$@"
