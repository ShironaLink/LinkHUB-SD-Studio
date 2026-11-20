#!/bin/bash
# sdgen for macOS: runs sdgen.py with ComfyUI's own Python from config.sh.
#   ./sdgen.sh --help
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$ROOT/config.sh" ]; then
    echo "SD Studio is not set up yet. Run setup.command first." >&2
    exit 1
fi
. "$ROOT/config.sh"
if [ ! -x "$PYTHON" ]; then
    echo "Python in config.sh was not found. Run setup.command again." >&2
    exit 1
fi
export SD_STUDIO_PORT="$PORT"
exec "$PYTHON" -s "$ROOT/sdgen.py" "$@"
