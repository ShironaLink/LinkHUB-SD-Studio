#!/bin/bash
# SD Studio engine (macOS): runs the ComfyUI named in config.sh headless, with
# the SD Studio UI node loaded from this folder. Nothing is copied into ComfyUI.
# SDStudio.command runs this in its Terminal window; sdgen.sh runs it in the
# background with the output in engine.log.
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || exit 1

if [ ! -f "$ROOT/config.sh" ]; then
    echo "[SD Studio] config.sh is missing. Run setup.command first."
    echo 1 > "$ROOT/engine.failed"
    [ -t 0 ] && read -r -p "Press Enter to close." _
    exit 1
fi
. "$ROOT/config.sh"
# Optional per-machine additions that setup.command must not overwrite.
[ -f "$ROOT/config.local.sh" ] && . "$ROOT/config.local.sh"

export SD_STUDIO_ROOT="$ROOT"
mkdir -p "$ROOT/outputs"

# COMFY_ARGS is split into words on purpose; keep the shell from globbing them.
set -f
"$PYTHON" -s "$COMFYUI_DIR/main.py" --listen 127.0.0.1 --port "$PORT" \
    --output-directory "$ROOT/outputs" --temp-directory "$ROOT" \
    --extra-model-paths-config "$ROOT/extra_model_paths.yaml" \
    --preview-method auto $COMFY_ARGS
RC=$?
set +f
[ "$RC" = 0 ] && exit 0

# Leave a marker so SDStudio.command / sdgen stop waiting, and keep the window
# open so the error can be read.
echo "$RC" > "$ROOT/engine.failed"
echo
echo "[SD Studio] The engine stopped with an error (code $RC). The lines above say why."
[ -t 0 ] && read -r -p "Press Enter to close." _
exit "$RC"
