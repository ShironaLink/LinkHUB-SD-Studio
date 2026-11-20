#!/bin/bash
# SD Studio セットアップ（macOS）
# ComfyUI の場所とポートを聞いて config.sh を書き、詠唱補助装置を取ってきて、
# Anima 系モデルの部品があるかを確かめる。もう一度実行すると、前回の設定
# （場所・ポート・COMFY_ARGS）が既定値になる。
#
# 初回は、ターミナルで `bash ` と打ってからこのファイルをドラッグして Enter。
# ダウンロード印（quarantine）を外すので、以後は .command をダブルクリックで開ける。
#
# 引数を渡せば質問を飛ばせる:
#   bash setup.command --comfy-dir ~/ComfyUI --port 8188 --prompt-tool yes

ROOT="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$ROOT/config.sh"

say()  { printf '%s\n' "$*"; }
ok()   { printf '\033[32m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
err()  { printf '\033[31m%s\033[0m\n' "$*"; }
dim()  { printf '\033[90m%s\033[0m\n' "$*"; }

# No `read -e`: bash 3.2's readline silently drops Japanese and other non-ASCII
# bytes unless the locale is an existing UTF-8 one (it is not on, e.g., an
# English-UI Mac set to the Japan region).
ARG_COMFY=''; ARG_PORT=''; ARG_PT=''
while [ $# -gt 0 ]; do
    case "$1" in
        --comfy-dir|--port|--prompt-tool)
            [ $# -ge 2 ] || { err "$1 には値が要ります。"; exit 1; } ;;
    esac
    case "$1" in
        --comfy-dir)   ARG_COMFY="$2"; shift 2 ;;
        --port)        ARG_PORT="$2"; shift 2 ;;
        --prompt-tool) ARG_PT="$2"; shift 2 ;;
        *) err "知らない引数です: $1"; exit 1 ;;
    esac
done

printf '\033[36m%s\033[0m\n\n' '==== SD Studio セットアップ ===='

# ---------------------------------------------------------------- download mark
# Files unpacked from a browser download carry com.apple.quarantine, and
# Gatekeeper refuses to open an unsigned .command that has it. Running this
# script through `bash` is not affected; afterwards the launchers open normally.
for f in "$ROOT"/*.command "$ROOT"/*.sh; do
    [ -f "$f" ] || continue
    /usr/bin/xattr -d com.apple.quarantine "$f" 2>/dev/null
    chmod +x "$f" 2>/dev/null
done

# ---------------------------------------------------------------- previous config
old() { [ -f "$CONFIG" ] && ( . "$CONFIG" >/dev/null 2>&1; eval "printf '%s' \"\$$1\"" ); }
OLD_COMFY="$(old COMFYUI_DIR)"
OLD_PYTHON="$(old PYTHON)"
OLD_PORT="$(old PORT)"
OLD_ARGS="$(old COMFY_ARGS)"

# ---------------------------------------------------------------- ComfyUI
# Accept what Terminal pastes for a dragged folder: a trailing space and
# backslash-escaped spaces, sometimes quotes, and a leading ~.
clean_path() {
    local p="$1"
    p="$(printf '%s' "$p" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    case "$p" in \"*\") p="${p#\"}"; p="${p%\"}" ;; \'*\') p="${p#\'}"; p="${p%\'}" ;; esac
    case "$p" in *\\*) p="$(printf '%s' "$p" | sed -e 's/\\\(.\)/\1/g')" ;; esac
    case "$p" in "~") p="$HOME" ;; "~/"*) p="$HOME/${p#\~/}" ;; esac
    printf '%s' "$p"
}

resolve_comfy() {
    local d
    d="$(clean_path "$1")"
    [ -n "$d" ] && [ -d "$d" ] || return 1
    d="$(cd "$d" && pwd)" || return 1
    if [ -f "$d/main.py" ]; then printf '%s' "$d"; return 0; fi
    # A folder that holds ComfyUI/ (and maybe the venv next to it).
    if [ -f "$d/ComfyUI/main.py" ]; then printf '%s' "$d/ComfyUI"; return 0; fi
    return 1
}

COMFY=''
[ -n "$ARG_COMFY" ] && COMFY="$(resolve_comfy "$ARG_COMFY")"
PREV="$(resolve_comfy "$OLD_COMFY")"
while [ -z "$COMFY" ]; do
    say 'ComfyUI のフォルダを入力してください（main.py があるフォルダ）。Finder からこの窓へドラッグしても入ります。'
    dim '  例: ~/ComfyUI'
    dim '  例: ~/Library/Application Support/StabilityMatrix/Packages/ComfyUI'
    [ -n "$PREV" ] && dim "  Enter だけ押すと前回と同じ場所: $PREV"
    read -r -p 'ComfyUI のフォルダ: ' IN || exit 1
    if [ -z "$IN" ] && [ -n "$PREV" ]; then COMFY="$PREV"; else COMFY="$(resolve_comfy "$IN")"; fi
    [ -z "$COMFY" ] && warn 'main.py が見つかりませんでした。もう一度入力してください。'
done
ok "ComfyUI : $COMFY"

# ---------------------------------------------------------------- Python
PARENT="$(dirname "$COMFY")"
PYTHON=''
for c in "$COMFY/venv/bin/python" "$COMFY/.venv/bin/python" \
         "$PARENT/.venv/bin/python" "$PARENT/venv/bin/python" "$OLD_PYTHON"; do
    if [ -n "$c" ] && [ -f "$c" ] && [ -x "$c" ]; then PYTHON="$c"; break; fi
done
while [ -z "$PYTHON" ]; do
    warn 'ComfyUI が使っている Python が見つかりませんでした。場所を入力してください（例: ~/ComfyUI/venv/bin/python）。'
    read -r -p 'python のパス: ' IN || exit 1
    IN="$(clean_path "$IN")"
    if [ -n "$IN" ] && [ -f "$IN" ] && [ -x "$IN" ]; then PYTHON="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"; fi
done
ok "Python  : $PYTHON"

say 'Python の中身を確認しています（数十秒かかることがあります）...'
PROBE="import sys, torch, aiohttp; print(sys.version.split()[0], torch.__version__, 'mps' if torch.backends.mps.is_available() else ('gpu' if torch.cuda.is_available() else 'cpu'))"
if ! OUT="$("$PYTHON" -s -c "$PROBE" 2>/dev/null)"; then
    err 'この Python では ComfyUI の部品（torch / aiohttp）を読み込めませんでした。'
    "$PYTHON" -s -c "$PROBE" 2>&1 | tail -n 5 | while IFS= read -r l; do dim "  $l"; done
    err 'ComfyUI 単体で一度起動できることを確かめてから、もう一度 setup.command を実行してください。'
    exit 1
fi
OUT="$(printf '%s\n' "$OUT" | tail -n 1)"
ok "  Python / torch / 演算装置: $OUT"
case "$OUT" in
    *cpu) warn '  ※ GPU（Apple シリコンの MPS）を使えない状態です。生成がとても遅くなります（Intel Mac は非対応です）。' ;;
esac

# ---------------------------------------------------------------- Port
port_busy() { /usr/bin/nc -z -G 1 127.0.0.1 "$1" >/dev/null 2>&1; }
valid_port() { case "$1" in ''|*[!0-9]*) return 1 ;; esac; [ "${#1}" -le 5 ] && [ "$1" -ge 1024 ] && [ "$1" -le 65535 ]; }

PORT=''
valid_port "$ARG_PORT" && PORT="$ARG_PORT"
if [ -z "$PORT" ]; then
    DEFAULT=8188
    valid_port "$OLD_PORT" && DEFAULT="$OLD_PORT"
    say ''
    say 'SD Studio が使うポート番号を決めます。ふだんの ComfyUI と同時に使いたいときは、別の番号（例: 8189）にしてください。'
    while :; do
        port_busy "$DEFAULT" && warn "  ※ ポート $DEFAULT は今ほかのソフトが使っています（ComfyUI を起動したままなら、それかもしれません）。"
        read -r -p "ポート番号 [Enter で $DEFAULT]: " IN || exit 1
        IN="$(printf '%s' "$IN" | tr -d '[:space:]')"
        if [ -z "$IN" ]; then PORT="$DEFAULT"; break; fi
        if valid_port "$IN"; then PORT="$IN"; break; fi
        warn '1024〜65535 の半角数字で入力してください。'
    done
fi
ok "ポート  : $PORT"

# ---------------------------------------------------------------- config.sh
# Single-quote every value so spaces, Japanese and $ in paths survive.
q() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
{
    say '# Written by setup.command, which rewrites it: keep your own additions'
    say '# (e.g. export PYTORCH_ENABLE_MPS_FALLBACK=1) in config.local.sh instead.'
    say "COMFYUI_DIR=$(q "$COMFY")"
    say "PYTHON=$(q "$PYTHON")"
    say "PORT=$(q "$PORT")"
    say '# Extra ComfyUI options, e.g. --force-fp16'
    say "COMFY_ARGS=$(q "$OLD_ARGS")"
} > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG" || { err 'config.sh を書けませんでした。'; exit 1; }
ok 'config.sh を書きました。'
[ -n "$OLD_ARGS" ] && dim "  COMFY_ARGS は前回の値を引き継ぎました: $OLD_ARGS"

mkdir -p "$ROOT/outputs" "$ROOT/runs"

# ---------------------------------------------------------------- prompt tool
PT="$ROOT/prompt-tool"
REPO='https://github.com/ShironaLink/shirona-prompt-tool'
# /usr/bin/git is only a stub until the Command Line Tools are installed; calling
# it then pops up an installer, so only use git when it is real.
have_git() {
    local g
    g="$(command -v git)" || return 1
    [ "$g" != /usr/bin/git ] || /usr/bin/xcode-select -p >/dev/null 2>&1
}
if [ -f "$PT/index.html" ]; then
    ok '詠唱補助装置: 導入済み'
elif [ -e "$PT" ]; then
    warn "詠唱補助装置: prompt-tool フォルダが不完全です。フォルダを消してから setup.command を実行し直すか、$REPO の中身を置いてください。"
else
    WANT="$(printf '%s' "$ARG_PT" | tr '[:upper:]' '[:lower:]')"
    if [ "$WANT" != yes ] && [ "$WANT" != no ]; then
        say ''
        say '詠唱補助装置（Danbooru タグを画像付きで選べるツール。R-18 要素を含みます）も入れますか？'
        read -r -p '[Y/n]: ' IN || exit 1
        case "$IN" in [nN]*) WANT=no ;; *) WANT=yes ;; esac
    fi
    if [ "$WANT" = yes ]; then
        if have_git; then
            git clone --depth 1 "$REPO.git" "$PT"
        else
            ZIP="$ROOT/prompt-tool.zip"; TMP="$ROOT/prompt-tool.tmp"
            rm -rf "$ZIP" "$TMP"
            if /usr/bin/curl -fsSL -o "$ZIP" "$REPO/archive/refs/heads/main.zip" \
               && /usr/bin/ditto -x -k "$ZIP" "$TMP"; then
                mv "$TMP/shirona-prompt-tool-main" "$PT"
            else
                warn '  ダウンロードに失敗しました。'
            fi
            rm -rf "$ZIP" "$TMP"
        fi
        if [ -f "$PT/index.html" ]; then
            ok '詠唱補助装置: 導入しました'
        else
            warn "詠唱補助装置: 入れられませんでした。あとで $REPO から落として prompt-tool フォルダに置けば使えます。"
        fi
    fi
fi

# ---------------------------------------------------------------- models
# Only the default models folder is checked. Models kept elsewhere through
# ComfyUI's own extra_model_paths.yaml (Stability Matrix does this) still work.
MODELS="$COMFY/models"
say ''
MISSING=0
for part in 'text_encoders/qwen_3_06b_base.safetensors|https://huggingface.co/circlestone-labs/Anima/tree/main/split_files/text_encoders' \
            'vae/qwen_image_vae.safetensors|https://huggingface.co/circlestone-labs/Anima/tree/main/split_files/vae'; do
    rel="${part%%|*}"; url="${part#*|}"
    if [ ! -f "$MODELS/$rel" ]; then
        [ "$MISSING" = 0 ] && warn 'Anima 系のモデルを使うには、次の部品も必要です（ほかの場所に置いてあるなら無視してかまいません）:'
        MISSING=1
        warn "  $MODELS/$rel"
        dim "    入手先: $url"
    fi
done
[ "$MISSING" = 0 ] && ok 'Anima 系の部品（テキストエンコーダと VAE）: あり'

say ''
printf '\033[36m%s\033[0m\n' '==== 完了 ===='
if [ -n "$SD_STUDIO_FROM_LAUNCHER" ]; then
    say 'このままエンジンを起動して、ブラウザで開きます。'
else
    say 'SDStudio.command をダブルクリックすると、エンジンが起動してブラウザで開きます。'
fi
say "  生成: http://127.0.0.1:$PORT/studio"
exit 0
