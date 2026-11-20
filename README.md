# SD Studio

ComfyUI に「要素を組み合わせて大量に作り、人が選ぶ」ための画面を足すツールです（Windows 用）。

イラストを要素（魅せカット・構図・カメラ・表情・背景 …）に分け、各要素をランダムに組み合わせて
大量に生成します。人は出来上がりを見て「採用」か「却下」を付けるだけです。採用したものだけを
高解像度で作り直せて、どの要素の当たりが多いかも集計されます。

| 画面 | URL | 役割 |
|---|---|---|
| 生成 | http://127.0.0.1:8188/studio | 単発生成・img2img・レシピからの大量生成 |
| 選別 | http://127.0.0.1:8188/studio/review | キーボードで採用/却下を付ける・採用分の書き出しと本生成 |
| 詠唱補助装置 | http://127.0.0.1:8188/studio/prompt | Danbooru タグを画像付きで選ぶ（任意） |
| 素の ComfyUI | http://127.0.0.1:8188/ | いつものノード画面もそのまま使える |

8188 は既定のポート番号です。セットアップで別の番号にした場合は、URL のその部分が変わります。

ComfyUI 本体には手を加えません。お使いの ComfyUI を「エンジン」として借りるだけです。

---

## 必要なもの

- Windows 10 / 11 と、ComfyUI が動く GPU（NVIDIA 推奨）
- ComfyUI（どれか1つ）
  - **公式ポータブル版**（おすすめ）: [ComfyUI_windows_portable_nvidia.7z](https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z)
  - Stability Matrix で入れた ComfyUI
  - 手動で入れた ComfyUI（`venv` か `.venv` のあるもの）
  - ※ インストーラで入れる **ComfyUI Desktop 版には対応していません**
- 生成モデル（下の「モデル」を参照）

## セットアップ

1. **ComfyUI を用意する。** ポータブル版なら展開して `run_nvidia_gpu.bat` で一度起動し、
   ブラウザに ComfyUI が出ることを確かめてから、黒いウィンドウを閉じます。
2. **このフォルダを好きな場所に置く。** `git clone` でも、GitHub の「Download ZIP」を展開しても構いません。
   - 日本語や空白を含まない場所（例: `D:\sd-studio`）が無難です。
   - OneDrive で同期されるデスクトップやドキュメントは避けてください（生成画像まで同期されます）。
   - ZIP の場合は、**展開する前に** ZIP を右クリック →「プロパティ」→ 下の「許可する」にチェック → OK。
     こうしておくと、展開後の `.bat` を開くたびに警告が出るのを防げます。
3. **`setup.bat` をダブルクリック。** ComfyUI のフォルダとポート番号を聞かれます。
   - ポータブル版: 展開したフォルダ（例: `D:\ComfyUI_windows_portable`）
   - Stability Matrix: `…\Data\Packages\ComfyUI`
     （Stability Matrix の画面で設定した起動オプションは引き継がれません。必要なものは、
     セットアップ後に `config.bat` の `COMFY_ARGS` へ書き足してください）
   - ポート番号はふつう Enter だけで構いません（下の注意を参照）

   ComfyUI の Python を自動で見つけて `config.bat` に記録し、詠唱補助装置を入れるか聞いてきます。
   もう一度実行すると、前回の設定が既定値になります。
4. **モデルを置く**（次の節）。
5. **`SDStudio.bat` をダブルクリック。** エンジンが最小化ウィンドウで起動し、ブラウザで生成画面が開きます。

> ダウンロードした `.bat` を初めて開くと「Windows によって PC が保護されました」と出ることがあります。
> 「詳細情報」→「実行」で進めてください。

ComfyUI をいつも使うときのポート（8188）を SD Studio も使います。**ComfyUI を別に起動したままだと
エンジンが立ち上がりません**（`SDStudio.bat` がそう知らせます）。同時に使いたいときは `setup.bat` で
別のポート番号（例: 8189）を指定してください。同時に動かすと、エンジンの窓に赤字で
「Failed to initialize database」と出ますが、生成には影響しません（ComfyUI の記録用データベースを
1つの ComfyUI につき1プロセスしか開けないためです）。

## モデル

モデルは **ComfyUI 側の `models` フォルダ**に置きます（SD Studio のフォルダではありません）。
置いたら生成画面の「モデル再読込」を押せば一覧に出ます。モデルの種類（Anima / SDXL / Z-Image）は
ファイルの中身から自動で判定し、手順数・CFG・サンプラーもそれぞれに合った値が最初から入ります。

### Anima 系（おすすめ）

アニメ絵向け。モデル本体のほかに、**共通の部品2つ**が要ります。

| 置き場所（ComfyUI\models\ 以下） | ファイル | 入手先 |
|---|---|---|
| `text_encoders\` | `qwen_3_06b_base.safetensors` | [circlestone-labs/Anima](https://huggingface.co/circlestone-labs/Anima/tree/main/split_files/text_encoders) |
| `vae\` | `qwen_image_vae.safetensors` | [circlestone-labs/Anima](https://huggingface.co/circlestone-labs/Anima/tree/main/split_files/vae) |
| `diffusion_models\` | モデル本体（約4GB の `.safetensors`） | 下の表 |

部品はファイル名で探すので、**名前を変えずに**置いてください。

作者が普段使っているモデル（どれも `diffusion_models\` に置く）:

| モデル | 入手先 |
|---|---|
| Hoseki - LustrousMix（Anima v1.0） | https://civitai.com/models/941345?modelVersionId=2982979 |
| Tekito-Mix v3.1 | https://civitai.com/models/2639779?modelVersionId=3147432 |
| JANIMA v1.0 | https://civitai.com/models/2642932?modelVersionId=2967640 |
| MiaoMiao Harem（Anima 版） | https://civitai.com/models/934764 |
| Fn-Moment Anima-Turbo（v3.0-no turbo） | https://civitai.com/models/2733842?modelVersionId=3251959 |
| Anima 公式（base / aesthetic など） | https://huggingface.co/circlestone-labs/Anima/tree/main/split_files/diffusion_models |

ライセンスや利用条件はモデルごとに違います。各ページで確認してください。

### SDXL 系（Illustrious / NoobAI / Pony など）

1ファイルで完結するので `checkpoints\` に置くだけです。

### Z-Image 系

`diffusion_models\` にモデル本体、加えて `text_encoders\qwen_3_4b.safetensors` と `vae\ae.safetensors`
（どちらも [Comfy-Org/Z-Image-Turbo](https://huggingface.co/Comfy-Org/Z-Image-Turbo/tree/main/split_files)）が要ります。

### LoRA

`loras\` に置きます。生成画面で選べます。Anima 用の LoRA は Anima のモデルにしか効きません（SDXL 用も同様）。

---

## 使い方

### 1. レシピを組む（`wildcards\` フォルダ）

1スロット1ファイル。`ラベル | プロンプト` を1行に1つずつ並べます（`|` が無ければ行全体を使います）。
`#` で始まる行と空行は無視されます。

```
# showcut.txt
振り向いた瞬間 | turning around toward the viewer, hair fluttering in the air
本で顔を半分隠す | hiding the lower half of her face behind an open book
```

スロットの並び順と、プロンプトの雛形は `wildcards\_slots.json` にあります。
生成画面の ✎ からその場で編集もできます。

**主役は「魅せカット」スロット**です。書くのは「どんな可愛い一瞬か」で、手足の角度ではありません。
角度を書きたくなったら構図・カメラのスロットに移します。同梱のレシピは見本なので、自由に書き換えてください。

### 2. 大量生成（生成画面の左パネル下部）

枚数とモードを決めて「キューに投入」。1枚ごとに別のプロンプトとして積まれるので、
**投入したらブラウザを閉じても生成は続きます。**

**ラフモード**は解像度と手順数を落として枚数を稼ぎます。当たり外れは構図と魅せカットでほぼ決まるので、
ラフで選別してから、採用したものだけ本解像度に上げるのが効率的です。

プロンプト欄に手書きした内容は、レシピの抽選結果の**前に**付きます（レシピをONにしても消えません）。
実際に送られる文字列は「実際に送られるプロンプト」欄で確認できます。

### 3. 選別（選別画面）

| キー | 動作 |
|---|---|
| `1` / `F` | 採用 |
| `0` / `D` | 却下 |
| `U` / `Backspace` | 取り消し（同じキーをもう一度押しても取り消し） |
| `←` `→` | 1枚戻る / 進む |
| `↑` `↓` | 5枚戻る / 進む |

右側に、その画像がどの要素の組み合わせから出来たかが出ます。

- **採用を書き出し** → `outputs\picked\<run_id>\` にコピー
- **採用を本生成** → 採用分だけ本解像度で作り直す。img2img を選べばラフの構図が保たれる
- **採用率** → スロットの選択肢ごとの採用率。当たる魅せカットと外れる魅せカットが分かる

### 止め方

- **エンジンを止める**: タスクバーの「SD Studio engine」ウィンドウを閉じる（または `sdgen.bat --stop`）
- ※ エンジンの窓の中をクリックすると、文字の選択状態（簡易編集モード）になって**生成が止まる**ことがあります。
  タイトルに「選択」と出ていたら Esc を押すと再開します
- **生成中の1枚を止める**: 生成画面の「中断」
- **積んだキューを消す**: 素の ComfyUI 画面（http://127.0.0.1:8188/ ）のキュー一覧から消去する。
  キューを消しても、生成済みの画像と台帳は残るので選別できます

### コマンドで使う（`sdgen.bat`）

このフォルダでコマンドプロンプトを開いて使います。モデル名は一部だけでも構いません。
エンジンが止まっていれば自動で起動します。

```bat
rem 単発生成（保存先のパスを表示）
sdgen.bat "1girl, silver hair, smile" --model tekito

rem LoRA を付ける（強度は省略すると 0.8）
sdgen.bat "1girl, smile" --model tekito --lora mylora:0.9

rem img2img
sdgen.bat "same prompt" --model tekito --i2i base.png --denoise 0.55

rem レシピから28枚をラフで積む（すぐ戻る。続きは選別画面で）
sdgen.bat --model tekito --run 28 --size 832x1216 --rough 0.65

sdgen.bat --status
sdgen.bat --stop
sdgen.bat --help
```

出力をほかのプログラムで受け取るとき（パイプやリダイレクト）は、UTF-8 で出力します。
フォルダ名やモデル名が英数字だけなら気にする必要はありません。日本語を含む場合、コマンドプロンプトの
`| more` や Windows PowerShell 5.1 の `$o = & .\sdgen.bat ...` では、その部分が文字化けします。

## ファイルの置き場所

| | 場所 |
|---|---|
| レシピ | `wildcards\*.txt` と `wildcards\_slots.json` |
| 生成画像 | `outputs\<run_id>\` （単発生成は `outputs\` 直下） |
| 採用画像の書き出し先 | `outputs\picked\<run_id>\` |
| 台帳（どの選択肢から作ったか） | `runs\<run_id>.json` |
| 設定（ComfyUI の場所・ポート・追加オプション） | `config.bat`（`setup.bat` が作る） |
| 一時ファイル | `temp\`（エンジン起動のたびに空になる） |

## 知っておくと得すること

- **denoise を下げても生成時間は減りません。** ComfyUI は開始ノイズを減らすだけで、手順数は変わらないためです。
  時間を減らしたいときは手順数（steps）を下げます。
- **大量生成は1回につき1モデル**にすると速いです。モデルを混ぜると、切り替えのたびに読み込み直しが走ります。
- **枚数を決める前に1枚だけ作って時間を測る**と、何枚積めば何時間かかるか見積もれます。
- ComfyUI は同じ設定・同じ seed の結果を使い回します。速さを比べるときは seed を変えてください。

## 困ったとき

| 症状 | 確かめること |
|---|---|
| `SDStudio.bat` が「The engine failed to start」と言う | タスクバーの「SD Studio engine」ウィンドウに出ているエラー |
| 「Port 8188 is already used by another program」と出る | ComfyUI を別に起動したままになっていないか。同時に使うなら `setup.bat` で別のポートにする |
| ComfyUI を移動した・入れ直した | `setup.bat` をもう一度実行する（場所が変わったことに気づけば `SDStudio.bat` が自動で実行します） |
| `sdgen.bat` だけが「Python in config.bat was not found」と言う | ComfyUI のフォルダ名に日本語などが入っていないか。入っていると、文字コードを UTF-8 に切り替えたターミナルからは `config.bat` を正しく読めません。ComfyUI を英数字だけの場所へ移して `setup.bat` をやり直す |
| 生成画面のレシピ欄に「読めません」と出る | `wildcards` のファイルを UTF-8 で保存し直す（メモ帳なら「名前を付けて保存」→ 文字コード UTF-8） |
| 生成がとても遅い | `setup.bat` の結果に「GPU を使えない」と出ていないか |
| モデルが一覧に出ない | 置き場所（`checkpoints` か `diffusion_models` か）。置いたあと「モデル再読込」を押したか |
| Anima のモデルでエラーになる | `qwen_3_06b_base.safetensors` と `qwen_image_vae.safetensors` が名前を変えずに置いてあるか |
| VRAM が足りない | `config.bat` の `COMFY_ARGS` に `--lowvram` を入れる |
| 詠唱補助装置が開かない | `prompt-tool\index.html` があるか。無ければ `setup.bat` をもう一度実行する |

## 同梱物と出典

- `custom_nodes\sd_studio_ui\` — 画面とAPI（ComfyUI のカスタムノード。`extra_model_paths.yaml` 経由で読み込む）
- `sdgen.py` / `sdgen.bat` — コマンド
- `wildcards\` — 見本のレシピ
- `setup.bat` / `setup.ps1` / `start.bat` / `SDStudio.bat` — 導入と起動
- 詠唱補助装置は別のリポジトリ [ShironaLink/shirona-prompt-tool](https://github.com/ShironaLink/shirona-prompt-tool) から
  `setup.bat` が取ってきます。同梱はしていません（画像・キャラクター素材は再配布・改変禁止）。
