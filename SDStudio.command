#!/bin/bash
# SD Studio launcher (macOS): double-click in Finder.
# Opens the studio in the browser, starting the engine first when it is down.
# This Terminal window then becomes the engine; closing it stops the engine.
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || exit 1
CONFIG="$ROOT/config.sh"

# No config yet, or ComfyUI was moved since setup: run setup (again).
config_ok() {
    [ -f "$CONFIG" ] && ( . "$CONFIG" >/dev/null 2>&1; [ -x "$PYTHON" ] && [ -f "$COMFYUI_DIR/main.py" ] )
}
if ! config_ok; then
    echo "[SD Studio] Running setup first."
    SD_STUDIO_FROM_LAUNCHER=1 /bin/bash "$ROOT/setup.command" || exit 1
    config_ok || exit 1
    echo
fi
. "$CONFIG"
URL="http://127.0.0.1:$PORT"

studio_up() { /usr/bin/curl -sf -m 3 --noproxy '*' -o /dev/null "$URL/studio/api/ping"; }

if studio_up; then
    open "$URL/studio"
    exit 0
fi
# Something else answers HTTP on the port: most likely ComfyUI started on its own.
if /usr/bin/curl -s -m 3 --noproxy '*' -o /dev/null "$URL/"; then
    echo "[SD Studio] Port $PORT is already used by another program (a ComfyUI left running?)."
    echo "            Quit it, or run setup.command again and choose another port."
    exit 1
fi

rm -f "$ROOT/engine.failed"
echo "[SD Studio] Starting the engine on port $PORT. The browser opens when it is ready."
echo "[SD Studio] Closing this window stops the engine."
echo
# After the exec below, $$ is the engine's start.sh; stop waiting once it is gone
# (Ctrl+C does not reach this background job).
(
    for _ in $(seq 150); do
        sleep 2
        kill -0 $$ 2>/dev/null || exit 0
        if studio_up; then open "$URL/studio"; exit 0; fi
        [ -f "$ROOT/engine.failed" ] && exit 1
    done
    echo "[SD Studio] The engine did not answer within 5 minutes. Read the lines above."
) &
exec /bin/bash "$ROOT/start.sh"
