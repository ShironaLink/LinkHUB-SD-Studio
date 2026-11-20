# SD Studio セットアップ（Windows PowerShell 5.1 / PowerShell 7）
# setup.bat から呼ばれる。ComfyUI の場所とポートを聞いて config.bat を書き、
# 詠唱補助装置を取ってきて、Anima 系モデルの部品があるかを確かめる。
# もう一度実行すると、前回の設定（場所・ポート・COMFY_ARGS）が既定値になる。
#
# 引数を渡せば質問を飛ばせる:
#   setup.bat -ComfyDir "D:\ComfyUI_windows_portable" -Port 8188 -PromptTool yes
param(
    [string]$ComfyDir,
    [int]$Port = 0,
    [string]$PromptTool = ''   # yes / no; empty means ask
)

# Native commands write warnings to stderr; under 'Stop' Windows PowerShell 5.1
# turns those into terminating errors, so failures are checked by hand instead.
$ErrorActionPreference = 'Continue'
# PS 5.1's progress bar makes Invoke-WebRequest crawl.
$ProgressPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $Root 'config.bat'

function Say([string]$msg, [string]$color = 'Gray') { Write-Host $msg -ForegroundColor $color }

Say '==== SD Studio セットアップ ====' Cyan
Say ''

# ---------------------------------------------------------------- encoding
# cmd decodes .bat files with the console code page: 932 on Japanese Windows,
# 65001 when "Beta: Use Unicode UTF-8" is on. This script runs in the same
# kind of console that will later run config.bat, so ask the console itself.
function Get-BatEncoding {
    $cp = 0
    try { $cp = [Console]::OutputEncoding.CodePage } catch { }
    if (-not $cp) {
        try { $cp = [int](Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Nls\CodePage').OEMCP } catch { }
    }
    if ($cp -eq 65001) { return New-Object System.Text.UTF8Encoding $false }
    if ($cp) {
        try { return [System.Text.Encoding]::GetEncoding($cp) } catch { }
    }
    return [System.Text.Encoding]::Default
}
$enc = Get-BatEncoding

# ---------------------------------------------------------------- previous config
$old = @{}
if (Test-Path -LiteralPath $ConfigPath) {
    foreach ($line in ([System.IO.File]::ReadAllText($ConfigPath, $enc) -split "`r?`n")) {
        if ($line -match '^\s*set\s+"([A-Z_]+)=(.*)"\s*$') { $old[$Matches[1]] = $Matches[2] }
    }
}

# ---------------------------------------------------------------- ComfyUI
function Resolve-Comfy([string]$dir) {
    if (-not $dir) { return $null }
    $dir = $dir.Trim().Trim('"')
    if (-not $dir -or -not (Test-Path -LiteralPath $dir -PathType Container)) { return $null }
    $dir = (Resolve-Path -LiteralPath $dir).ProviderPath.TrimEnd('\')
    if (Test-Path -LiteralPath (Join-Path $dir 'main.py')) { return $dir }
    # The portable build unpacks to ComfyUI_windows_portable\ComfyUI\main.py.
    $inner = Join-Path $dir 'ComfyUI'
    if (Test-Path -LiteralPath (Join-Path $inner 'main.py')) { return $inner }
    return $null
}

$comfy = Resolve-Comfy $ComfyDir
$prev = Resolve-Comfy $old['COMFYUI_DIR']
while (-not $comfy) {
    Say 'ComfyUI のフォルダを入力してください（main.py があるフォルダ、またはポータブル版を展開したフォルダ）。'
    Say '  例: D:\ComfyUI_windows_portable' DarkGray
    Say '  例: D:\StabilityMatrix\Data\Packages\ComfyUI' DarkGray
    if ($prev) { Say "  Enter だけ押すと前回と同じ場所: $prev" DarkGray }
    $in = Read-Host 'ComfyUI のフォルダ'
    if (-not $in -and $prev) { $comfy = $prev } else { $comfy = Resolve-Comfy $in }
    if (-not $comfy) { Say 'main.py が見つかりませんでした。もう一度入力してください。' Yellow }
}
Say "ComfyUI : $comfy" Green

# ---------------------------------------------------------------- Python
$candidates = @(
    (Join-Path (Split-Path -Parent $comfy) 'python_embeded\python.exe'),  # portable build
    (Join-Path $comfy 'venv\Scripts\python.exe'),                          # Stability Matrix
    (Join-Path $comfy '.venv\Scripts\python.exe')                          # manual install
)
if ($old['PYTHON']) { $candidates += $old['PYTHON'] }
$python = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
while (-not $python) {
    Say 'ComfyUI が使っている python.exe が見つかりませんでした。場所を入力してください。' Yellow
    $in = (Read-Host 'python.exe のパス').Trim().Trim('"')
    if ($in -and (Test-Path -LiteralPath $in -PathType Leaf)) {
        $python = (Resolve-Path -LiteralPath $in).ProviderPath
    }
}
Say "Python  : $python" Green

if ("$comfy$python" -match '%') {
    Say 'フォルダ名に % が入っていると、コマンドプロンプトがうまく扱えません。' Red
    Say '% を含まない場所へ移してから、もう一度実行してください。' Red
    exit 1
}
# config.bat is written in this console's code page and read back by cmd in
# whatever code page the *calling* console uses. With an ASCII-only path the
# two can never disagree; otherwise a UTF-8 terminal reads a Shift_JIS path
# as garbage and sdgen.bat reports that Python was not found.
if ("$comfy$python" -match '[^ -~]') {
    Say '  ※ ComfyUI のフォルダ名に日本語などの文字が入っています。ダブルクリックでの起動には問題ありません。' Yellow
    Say '    ただし文字コードの違うターミナル（UTF-8 に切り替えたコンソールなど）から sdgen.bat を呼ぶと、Python を見つけられません。' Yellow
    Say '    コマンドやほかのソフトからも使うなら、英数字だけの場所（例: D:\ComfyUI_windows_portable）が安全です。' Yellow
}

Say 'Python の中身を確認しています（数十秒かかることがあります）...'
$probe = "import sys, torch, aiohttp; print(sys.version.split()[0], torch.__version__, 'gpu' if torch.cuda.is_available() else 'cpu')"
$out = & $python -s -c $probe 2>$null
if ($LASTEXITCODE -ne 0) {
    Say 'この Python では ComfyUI の部品（torch / aiohttp）を読み込めませんでした。' Red
    & $python -s -c $probe 2>&1 | ForEach-Object { Say "  $_" DarkGray }
    Say 'ComfyUI 単体で一度起動できることを確かめてから、もう一度 setup.bat を実行してください。' Red
    exit 1
}
$out = "$($out | Select-Object -Last 1)"
Say "  Python / torch / 演算装置: $out" Green
if ($out -match 'cpu$') {
    Say '  ※ GPU を使えない状態です。生成がとても遅くなります（NVIDIA ドライバと ComfyUI の版を確認してください）。' Yellow
}

# ---------------------------------------------------------------- Port
function Test-PortBusy([int]$p) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $p); return $true } catch { return $false } finally { $client.Close() }
}

if ($Port -le 0) {
    $default = 8188
    if ($old['PORT'] -match '^[0-9]{1,5}$') { $default = [int]$old['PORT'] }
    Say ''
    Say 'SD Studio が使うポート番号を決めます。ふだんの ComfyUI と同時に使いたいときは、別の番号（例: 8189）にしてください。'
    while ($true) {
        if (Test-PortBusy $default) {
            Say "  ※ ポート $default は今ほかのソフトが使っています（ComfyUI を起動したままなら、それかもしれません）。" Yellow
        }
        $in = (Read-Host "ポート番号 [Enter で $default]").Trim()
        if (-not $in) { $Port = $default; break }
        if ($in -match '^[0-9]{1,5}$' -and [int]$in -ge 1024 -and [int]$in -le 65535) { $Port = [int]$in; break }
        Say '1024〜65535 の半角数字で入力してください。' Yellow
    }
}
Say "ポート  : $Port" Green

# ---------------------------------------------------------------- config.bat
$comfyArgs = ''
if ($old.ContainsKey('COMFY_ARGS')) { $comfyArgs = $old['COMFY_ARGS'] }
$config = @(
    '@rem Written by setup.bat. Run setup.bat again (or edit this file) if ComfyUI moves.',
    "set `"COMFYUI_DIR=$comfy`"",
    "set `"PYTHON=$python`"",
    "set `"PORT=$Port`"",
    '@rem Extra ComfyUI options, e.g. --lowvram',
    "set `"COMFY_ARGS=$comfyArgs`""
) -join "`r`n"
if ($enc.GetString($enc.GetBytes($config)) -cne $config) {
    Say 'ComfyUI のフォルダ名に、コマンドプロンプトで扱えない文字が入っています。' Red
    Say '英数字だけの場所（例: D:\ComfyUI_windows_portable）へ移してから、もう一度実行してください。' Red
    exit 1
}
[System.IO.File]::WriteAllText($ConfigPath, $config + "`r`n", $enc)
Say 'config.bat を書きました。' Green
if ($comfyArgs) { Say "  COMFY_ARGS は前回の値を引き継ぎました: $comfyArgs" DarkGray }

foreach ($d in 'outputs', 'runs') {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root $d) | Out-Null
}

# ---------------------------------------------------------------- prompt tool
$pt = Join-Path $Root 'prompt-tool'
$repo = 'https://github.com/ShironaLink/shirona-prompt-tool'
if (Test-Path -LiteralPath (Join-Path $pt 'index.html')) {
    Say '詠唱補助装置: 導入済み' Green
} elseif (Test-Path -LiteralPath $pt) {
    Say "詠唱補助装置: prompt-tool フォルダが不完全です。フォルダを消してから setup.bat を実行し直すか、$repo の中身を置いてください。" Yellow
} else {
    $want = $PromptTool.ToLower()
    if ($want -ne 'yes' -and $want -ne 'no') {
        Say ''
        Say '詠唱補助装置（Danbooru タグを画像付きで選べるツール。R-18 要素を含みます）も入れますか？'
        $want = if ((Read-Host '[Y/n]') -match '^[nN]') { 'no' } else { 'yes' }
    }
    if ($want -eq 'yes') {
        if (Get-Command git -ErrorAction SilentlyContinue) {
            & git clone --depth 1 "$repo.git" $pt
        } else {
            # No git: take the branch zip. Unpack next to the studio, not in
            # %TEMP%, because Move-Item cannot move folders across drives.
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
            $zip = Join-Path $Root 'prompt-tool.zip'
            $tmp = Join-Path $Root 'prompt-tool.tmp'
            try {
                Invoke-WebRequest -UseBasicParsing "$repo/archive/refs/heads/main.zip" -OutFile $zip
                Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
                Move-Item -LiteralPath (Join-Path $tmp 'shirona-prompt-tool-main') -Destination $pt
            } catch {
                Say "  ダウンロードに失敗しました: $_" Yellow
            } finally {
                Remove-Item -LiteralPath $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        if (Test-Path -LiteralPath (Join-Path $pt 'index.html')) {
            Say '詠唱補助装置: 導入しました' Green
        } else {
            Say "詠唱補助装置: 入れられませんでした。あとで $repo から落として prompt-tool フォルダに置けば使えます。" Yellow
        }
    }
}

# ---------------------------------------------------------------- models
# Only the default models folder is checked. Models kept elsewhere through
# ComfyUI's own extra_model_paths.yaml (Stability Matrix does this) still work.
$models = Join-Path $comfy 'models'
$parts = @(
    @{ Path = 'text_encoders\qwen_3_06b_base.safetensors'; Url = 'https://huggingface.co/circlestone-labs/Anima/tree/main/split_files/text_encoders' },
    @{ Path = 'vae\qwen_image_vae.safetensors'; Url = 'https://huggingface.co/circlestone-labs/Anima/tree/main/split_files/vae' }
)
$missing = @($parts | Where-Object { -not (Test-Path -LiteralPath (Join-Path $models $_.Path)) })
Say ''
if ($missing.Count -gt 0) {
    Say 'Anima 系のモデルを使うには、次の部品も必要です（ほかの場所に置いてあるなら無視してかまいません）:' Yellow
    foreach ($m in $missing) {
        Say "  $(Join-Path $models $m.Path)" Yellow
        Say "    入手先: $($m.Url)" DarkGray
    }
} else {
    Say 'Anima 系の部品（テキストエンコーダと VAE）: あり' Green
}

Say ''
Say '==== 完了 ====' Cyan
Say 'SDStudio.bat をダブルクリックすると、エンジンが起動してブラウザで開きます。'
Say "  生成: http://127.0.0.1:$Port/studio"
