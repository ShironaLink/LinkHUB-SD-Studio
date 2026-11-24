"""SD Studio UI: serves the custom frontend at /studio on the ComfyUI server.

Also exposes:
  /studio/api/models     — models with their architecture (sdxl / anima / z_image)
  /studio/api/recipe     — element slots and their wildcard options
  /studio/api/runs/*     — batch run ledgers (which slot options produced which image)
  /studio/api/stats      — pick rate per slot option
"""
import json
import os
import re
import struct
import time

from aiohttp import web

import folder_paths
from server import PromptServer

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
# custom_nodes/sd_studio_ui -> custom_nodes -> sd-studio
# ComfyUI itself lives elsewhere (portable build, Stability Matrix, ...) and
# loads this node through extra_model_paths.yaml, so the studio root is two
# levels up from here. start.bat / start.sh also set SD_STUDIO_ROOT explicitly.
STUDIO_ROOT = os.environ.get("SD_STUDIO_ROOT") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", ".."))
WILDCARD_DIR = os.path.join(STUDIO_ROOT, "wildcards")
RUNS_DIR = os.path.join(STUDIO_ROOT, "runs")

# 零式Danbooru型詠唱補助装置（github.com/ShironaLink/shirona-prompt-tool）。
# 単体HTMLなので web/ へコピーせず、setup.bat / setup.command が prompt-tool/ に clone したまま
# 配信する。そうしておけば git pull がそのまま更新になる。無くても他の画面は動く。
PROMPT_TOOL_DIR = os.environ.get("SD_STUDIO_PROMPT_TOOL") or os.path.join(
    STUDIO_ROOT, "prompt-tool")

routes = PromptServer.instance.routes

_arch_cache = {}  # path -> (mtime, size, arch)

# component files each non-checkpoint architecture needs
ARCH_COMPONENTS = {
    "anima": {"clip": "qwen_3_06b_base.safetensors", "vae": "qwen_image_vae.safetensors"},
    "z_image": {"clip": "qwen_3_4b.safetensors", "vae": "ae.safetensors"},
}

# Transparent output for Anima (huggingface.co/localai0301/Anima-RGBA).
# Same file names as ALPHA in web/assets/workflow.js.
ALPHA_KIT = {"vae": "anima_rgba_vae.safetensors", "lora": "anima_rgba_lora.safetensors"}


def _read_header_keys(path, max_header=100_000_000):
    with open(path, "rb") as fh:
        (n,) = struct.unpack("<Q", fh.read(8))
        if n > max_header:
            return []
        return list(json.loads(fh.read(n)).keys())


def _detect_arch(path):
    try:
        st = os.stat(path)
        cached = _arch_cache.get(path)
        if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
            return cached[2]
        keys = _read_header_keys(path)
        joined = "\n".join(keys)
        if "cap_embedder" in joined:
            arch = "z_image"
        elif "adaln_modulation_cross_attn" in joined:
            arch = "anima"
        elif "diffusion_model.blocks." in joined and "cross_attn" in joined:
            arch = "anima"  # anima LoRAs carry only the attention layers
        elif "lora_unet_blocks_" in joined and "cross_attn" in joined:
            arch = "anima"  # kohya-style anima LoRA (SDXL uses input_/output_blocks)
        elif "lora_unet" in joined or "lora_te" in joined:
            arch = "sdxl"
        elif "conditioner.embedders" in joined:
            arch = "sdxl"
        else:
            arch = "unknown"
        _arch_cache[path] = (st.st_mtime, st.st_size, arch)
        return arch
    except Exception:
        return "unknown"


def _list_with_arch(folder_key):
    out = []
    for name in folder_paths.get_filename_list(folder_key):
        if not name.endswith((".safetensors", ".ckpt")):
            continue
        path = folder_paths.get_full_path(folder_key, name)
        out.append({"name": name, "arch": _detect_arch(path) if path else "unknown"})
    return out


# The UI is edited in place and viewed through a WKWebView that otherwise serves
# a stale copy from its own cache, so every page and asset must be revalidated.
NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


@routes.get("/studio")
async def studio_index(request):
    return web.FileResponse(os.path.join(WEB_DIR, "index.html"), headers=NO_CACHE)


@routes.get("/studio/prompt")
async def studio_prompt_page(request):
    """SD Studio の一員としての「詠唱補助装置」ページ（戻るナビ付き）。

    中身は別リポジトリの単体HTMLなので、コピーも改変もせず iframe で載せている。
    そうしておけば `git pull` がそのまま更新経路になる。
    """
    return web.FileResponse(os.path.join(WEB_DIR, "prompt.html"), headers=NO_CACHE)


@routes.get("/studio/prompt/app")
async def studio_prompt_app_redirect(request):
    # The tool references its images relatively ("images/x.webp"), so it has to be
    # served from a directory URL. Without the trailing slash those would resolve
    # against /studio/prompt/ and every thumbnail would 404.
    raise web.HTTPFound("/studio/prompt/app/")


@routes.get("/studio/prompt/app/")
async def studio_prompt_index(request):
    path = os.path.join(PROMPT_TOOL_DIR, "index.html")
    if not os.path.isfile(path):
        raise web.HTTPNotFound(reason=f"prompt tool not found at {PROMPT_TOOL_DIR}")
    return web.FileResponse(path, headers=NO_CACHE)


@routes.get("/studio/prompt/app/{path:.*}")
async def studio_prompt_asset(request):
    rel = request.match_info["path"]
    root = os.path.realpath(PROMPT_TOOL_DIR)
    target = os.path.realpath(os.path.join(root, rel))
    # Resolve first, then confirm the result is still inside the tool directory —
    # "../" and symlinks are both handled by comparing the resolved paths.
    if target != root and not target.startswith(root + os.sep):
        raise web.HTTPForbidden()
    if not os.path.isfile(target):
        raise web.HTTPNotFound()
    return web.FileResponse(target)


@routes.get("/studio/assets/{name}")
async def studio_asset(request):
    name = os.path.basename(request.match_info["name"])
    path = os.path.join(WEB_DIR, "assets", name)
    if not os.path.isfile(path):
        raise web.HTTPNotFound()
    return web.FileResponse(path, headers=NO_CACHE)


PREVIEW_EXTS = [
    ".preview.png", ".preview.jpg", ".preview.jpeg", ".preview.webp",
    ".png", ".jpg", ".jpeg", ".webp",
]

CIVITAI_BY_HASH = "https://civitai.com/api/v1/model-versions/by-hash/{}"


def _sha256_of(path):
    """SHA256 of a model file, cached in a .sha256 sidecar to avoid rehashing."""
    import hashlib
    cache = os.path.splitext(path)[0] + ".sha256"
    st = os.stat(path)
    if os.path.isfile(cache):
        try:
            size, digest = open(cache).read().split()
            if int(size) == st.st_size:
                return digest
        except ValueError:
            pass
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(8 * 1024 * 1024):
            h.update(chunk)
    digest = h.hexdigest()
    with open(cache, "w") as fh:
        fh.write(f"{st.st_size} {digest}")
    return digest


def _preview_ext(body):
    """Extension from the bytes themselves, or None if this is not an image.

    Civitai preview URLs carry no extension (.../width=450/<uuid>), so guessing
    from the URL writes a lying suffix and the file will not open.
    """
    if body[:8] == b"\x89PNG\r\n\x1a\n":
        return ".preview.png"
    if body[:3] == b"\xff\xd8\xff":
        return ".preview.jpeg"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return ".preview.webp"
    return None


async def _fetch_civitai_preview(session, path):
    """Look up a model on Civitai by hash and save its first preview image."""
    import asyncio
    digest = await asyncio.to_thread(_sha256_of, path)
    async with session.get(CIVITAI_BY_HASH.format(digest)) as resp:
        if resp.status != 200:
            return "not_found"
        data = await resp.json()
    # A version mixes stills and clips. Without the type check the first entry
    # can be a video, which then lands on disk as an unreadable image.
    images = [im for im in data.get("images", [])
              if im.get("url") and im.get("type", "image") == "image"]
    if not images:
        return "no_image"
    for candidate in images:
        async with session.get(candidate["url"]) as resp:
            if resp.status != 200:
                continue
            body = await resp.read()
        ext = _preview_ext(body)
        if ext:
            break
    else:
        return "no_image"
    stem = os.path.splitext(path)[0]
    for old in PREVIEW_EXTS:  # official image replaces any existing sidecar
        if os.path.isfile(stem + old):
            os.remove(stem + old)
    with open(stem + ext, "wb") as fh:
        fh.write(body)
    return "fetched"


@routes.post("/studio/api/fetch_previews")
async def studio_fetch_previews(request):
    import aiohttp
    # {"only": ["a.safetensors", ...]} re-fetches just those, so one bad grab
    # does not mean re-downloading every preview.
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    only = set(payload.get("only") or ())
    result = {}
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=60),
        headers={"User-Agent": "sd-studio/1.0"},
    ) as session:
        for kind in ("checkpoints", "diffusion_models", "loras"):
            for name in folder_paths.get_filename_list(kind):
                if not name.endswith((".safetensors", ".ckpt")):
                    continue
                if only and name not in only:
                    continue
                path = folder_paths.get_full_path(kind, name)
                try:
                    result[name] = await _fetch_civitai_preview(session, path)
                except Exception as exc:
                    result[name] = f"error: {exc.__class__.__name__}"
    return web.json_response(result)


@routes.get("/studio/api/model_image")
async def studio_model_image(request):
    kind = request.query.get("kind", "")
    name = request.query.get("name", "")
    if kind not in ("checkpoints", "diffusion_models", "loras"):
        raise web.HTTPBadRequest()
    if name not in folder_paths.get_filename_list(kind):
        raise web.HTTPNotFound()
    path = folder_paths.get_full_path(kind, name)
    stem = os.path.splitext(path)[0]
    for ext in PREVIEW_EXTS:
        candidate = stem + ext
        if os.path.isfile(candidate):
            # The URL does not change when a sidecar is replaced, so without
            # this the browser keeps showing the old thumbnail. "no-cache" means
            # revalidate, not refetch — Last-Modified still yields a 304.
            return web.FileResponse(candidate, headers=NO_CACHE)
    raise web.HTTPNotFound()


@routes.get("/studio/api/models")
async def studio_models(request):
    clips = set(folder_paths.get_filename_list("text_encoders"))
    vaes = set(folder_paths.get_filename_list("vae"))
    components = {
        arch: {
            "clip": req["clip"] in clips,
            "vae": req["vae"] in vaes,
        }
        for arch, req in ARCH_COMPONENTS.items()
    }
    return web.json_response({
        "checkpoints": [
            {"name": m, "arch": "sdxl"}
            for m in folder_paths.get_filename_list("checkpoints")
        ],
        "diffusion_models": _list_with_arch("diffusion_models"),
        "loras": _list_with_arch("loras"),
        "components": components,
        "alpha": {
            "vae": ALPHA_KIT["vae"] in vaes,
            "lora": ALPHA_KIT["lora"] in set(folder_paths.get_filename_list("loras")),
        },
    })


# ---------------------------------------------------------------------------
# Recipe: element slots + wildcard options
#
# One .txt per slot in wildcards/, one option per line, in the form
#   ラベル | prompt text        (a line without "|" is used as both)
#   ラベル | prompt text | タグ  (optional third column: comma-separated tags)
# "#" comments and blank lines are ignored. _slots.json holds the slot order
# and the prompt template whose __key__ placeholders the options fill in.
# Tags change how an option is drawn, never the prompt: "場所" marks an option
# that makes the model paint a place, so transparent runs skip it.
# ---------------------------------------------------------------------------

SLOTS_FILE = os.path.join(WILDCARD_DIR, "_slots.json")
SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def _parse_options(text):
    options = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        label, sep, rest = line.partition("|")
        prompt, _, tags = rest.partition("|")
        label = label.strip()
        options.append({"label": label, "text": prompt.strip() if sep else label,
                        "tags": [t.strip() for t in re.split(r"[,、]", tags) if t.strip()]})
    return options


# Recipe files are edited by hand. utf-8-sig accepts UTF-8 with or without the
# BOM that some Windows editors add (a BOM otherwise breaks json.load and turns
# the first "# comment" line of a .txt into an option).
def _read_slots_file():
    with open(SLOTS_FILE, encoding="utf-8-sig") as fh:
        return json.load(fh)


@routes.get("/studio/api/recipe")
async def studio_recipe(request):
    if not os.path.isfile(SLOTS_FILE):
        return web.json_response({"template": "", "slots": [], "error": "wildcards/_slots.json がありません"})
    try:
        conf = _read_slots_file()
    except (ValueError, UnicodeDecodeError) as e:
        return web.json_response({"template": "", "slots": [],
                                  "error": f"wildcards/_slots.json を読めません（UTF-8で保存してください）: {e}"})
    slots = []
    for slot in conf.get("slots", []):
        path = os.path.join(WILDCARD_DIR, slot["key"] + ".txt")
        raw = ""
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8-sig") as fh:
                    raw = fh.read()
            except UnicodeDecodeError as e:
                return web.json_response({"template": "", "slots": [],
                                          "error": f"wildcards/{slot['key']}.txt を読めません（UTF-8で保存してください）: {e}"})
        slots.append({**slot, "options": _parse_options(raw), "raw": raw})
    return web.json_response({"template": conf.get("template", ""), "slots": slots})


@routes.post("/studio/api/recipe/template")
async def studio_recipe_template(request):
    body = await request.json()
    conf = _read_slots_file()
    conf["template"] = body.get("template", "")
    with open(SLOTS_FILE, "w", encoding="utf-8") as fh:
        json.dump(conf, fh, ensure_ascii=False, indent=2)
    return web.json_response({"ok": True})


@routes.post("/studio/api/recipe/slot/{key}")
async def studio_recipe_slot(request):
    key = request.match_info["key"]
    if not SAFE_KEY.match(key):
        raise web.HTTPBadRequest(reason="bad slot key")
    body = await request.json()
    path = os.path.join(WILDCARD_DIR, key + ".txt")
    if not os.path.isfile(path):
        raise web.HTTPNotFound()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body.get("raw", ""))
    return web.json_response({"ok": True, "options": _parse_options(body.get("raw", ""))})


# ---------------------------------------------------------------------------
# Run ledger: what each generated image was made of, and whether it was picked
#
# runs/<run_id>.json holds every item's slot draw, seed and prompt. Images are
# saved with filename_prefix "<run_id>/<index>", so the file on disk carries its
# own ledger index and no ComfyUI history lookup is needed to reconnect them.
# ---------------------------------------------------------------------------

SAFE_RUN = re.compile(r"^[0-9]{8}-[0-9]{6}(-[0-9]+)?$")


def _run_path(run_id):
    if not SAFE_RUN.match(run_id):
        raise web.HTTPBadRequest(reason="bad run id")
    return os.path.join(RUNS_DIR, run_id + ".json")


def _load_run(run_id):
    path = _run_path(run_id)
    if not os.path.isfile(path):
        raise web.HTTPNotFound()
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _save_run(run):
    with open(_run_path(run["run_id"]), "w", encoding="utf-8") as fh:
        json.dump(run, fh, ensure_ascii=False)


def _run_files(run_id):
    """index -> filename, read straight off disk from the "<index>_00001_.png" names."""
    folder = os.path.join(folder_paths.get_output_directory(), run_id)
    found = {}
    if not os.path.isdir(folder):
        return found
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(IMAGE_EXTS):
            continue
        head = name.split("_", 1)[0]
        if head.isdigit():
            found.setdefault(int(head), name)
    return found


@routes.post("/studio/api/runs/new")
async def studio_run_new(request):
    body = await request.json()
    os.makedirs(RUNS_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_id, n = stamp, 1
    while os.path.exists(os.path.join(RUNS_DIR, run_id + ".json")):
        n += 1
        run_id = f"{stamp}-{n}"
    run = {
        "run_id": run_id,
        "created": stamp,
        "mode": body.get("mode", "final"),
        "meta": body.get("meta", {}),
        "items": [],
    }
    _save_run(run)
    return web.json_response({"run_id": run_id})


@routes.post("/studio/api/runs/{run_id}/items")
async def studio_run_items(request):
    run = _load_run(request.match_info["run_id"])
    body = await request.json()
    for item in body.get("items", []):
        item.setdefault("rating", None)
        run["items"].append(item)
    _save_run(run)
    return web.json_response({"ok": True, "count": len(run["items"])})


@routes.get("/studio/api/runs")
async def studio_runs(request):
    os.makedirs(RUNS_DIR, exist_ok=True)
    out = []
    for name in sorted(os.listdir(RUNS_DIR), reverse=True):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(RUNS_DIR, name), encoding="utf-8") as fh:
                run = json.load(fh)
        except Exception:
            continue
        ratings = [i.get("rating") for i in run["items"]]
        out.append({
            "run_id": run["run_id"],
            "created": run["created"],
            "mode": run.get("mode", "final"),
            "model": run.get("meta", {}).get("model", ""),
            "count": len(run["items"]),
            "picked": ratings.count("pick"),
            "rated": len([r for r in ratings if r]),
            "done": len(_run_files(run["run_id"])),
        })
    return web.json_response(out)


@routes.get("/studio/api/runs/{run_id}")
async def studio_run_detail(request):
    run = _load_run(request.match_info["run_id"])
    files = _run_files(run["run_id"])
    for item in run["items"]:
        item["file"] = files.get(item["index"])
    return web.json_response(run)


@routes.post("/studio/api/runs/{run_id}/rate")
async def studio_run_rate(request):
    run = _load_run(request.match_info["run_id"])
    body = await request.json()
    rating = body.get("rating")
    if rating not in (None, "pick", "drop"):
        raise web.HTTPBadRequest(reason="bad rating")
    by_index = {i["index"]: i for i in run["items"]}
    for index in body.get("indexes", [body.get("index")]):
        if index in by_index:
            by_index[index]["rating"] = rating
    _save_run(run)
    return web.json_response({"ok": True})


@routes.post("/studio/api/runs/{run_id}/export")
async def studio_run_export(request):
    """Copy the picked images of a run into outputs/picked/<run_id>/."""
    import shutil
    run = _load_run(request.match_info["run_id"])
    files = _run_files(run["run_id"])
    src_dir = os.path.join(folder_paths.get_output_directory(), run["run_id"])
    dst_dir = os.path.join(folder_paths.get_output_directory(), "picked", run["run_id"])
    os.makedirs(dst_dir, exist_ok=True)
    copied = 0
    for item in run["items"]:
        name = files.get(item["index"])
        if item.get("rating") != "pick" or not name:
            continue
        dst = os.path.join(dst_dir, name)
        if not os.path.exists(dst):
            shutil.copy2(os.path.join(src_dir, name), dst)
        copied += 1
    return web.json_response({"copied": copied, "dir": dst_dir})


@routes.post("/studio/api/runs/{run_id}/stage")
async def studio_run_stage(request):
    """Copy one run image into ComfyUI's input dir so LoadImage can pick it up.

    This is what makes the rough -> final promotion possible: the rough render
    becomes the img2img reference for the full-resolution pass.
    """
    import shutil
    run = _load_run(request.match_info["run_id"])
    body = await request.json()
    name = _run_files(run["run_id"]).get(body.get("index"))
    if not name:
        raise web.HTTPNotFound(reason="no image for that index")
    src = os.path.join(folder_paths.get_output_directory(), run["run_id"], name)
    staged = f"{run['run_id']}_{name}"
    shutil.copy2(src, os.path.join(folder_paths.get_input_directory(), staged))
    return web.json_response({"name": staged})


@routes.get("/studio/api/stats")
async def studio_stats(request):
    """Pick rate per slot option — which 魅せカット actually land."""
    want = request.query.get("run", "all")
    os.makedirs(RUNS_DIR, exist_ok=True)
    tally = {}  # slot key -> option label -> [generated, picked]
    for name in os.listdir(RUNS_DIR):
        if not name.endswith(".json"):
            continue
        if want != "all" and name != want + ".json":
            continue
        try:
            with open(os.path.join(RUNS_DIR, name), encoding="utf-8") as fh:
                run = json.load(fh)
        except Exception:
            continue
        for item in run["items"]:
            if not item.get("rating"):  # unrated images say nothing about hit rate
                continue
            for key, label in (item.get("picks") or {}).items():
                row = tally.setdefault(key, {}).setdefault(label, [0, 0])
                row[0] += 1
                if item["rating"] == "pick":
                    row[1] += 1
    stats = {
        key: sorted(
            ({"label": label, "rated": g, "picked": p, "rate": (p / g if g else 0)}
             for label, (g, p) in options.items()),
            key=lambda r: (-r["rate"], -r["rated"]),
        )
        for key, options in tally.items()
    }
    return web.json_response(stats)


@routes.get("/studio/review")
async def studio_review(request):
    return web.FileResponse(os.path.join(WEB_DIR, "review.html"), headers=NO_CACHE)


def _exit_soon(delay=0.4):
    """Give aiohttp time to flush the response before the process disappears."""
    import threading

    def bye():
        time.sleep(delay)
        os._exit(0)

    threading.Thread(target=bye, daemon=True).start()


@routes.get("/studio/api/ping")
async def studio_ping(request):
    """Liveness check that proves this is an SD Studio engine, not some other
    ComfyUI on the same port. Depends on no user-editable file."""
    return web.json_response({"app": "sd-studio"})


@routes.post("/studio/api/engine/stop")
async def studio_engine_stop(request):
    """Shut the engine down. `sdgen --stop` uses this so no OS-specific process
    killing is needed; start.bat / start.sh then end on their own."""
    _exit_soon()
    return web.json_response({"status": "stopping"})


class SDStudioAlphaPrep:
    """RGBA image -> the 4-channel input the Anima RGBA VAE's encoder expects.

    That encoder was trained on RGB composited over white, plus alpha as a 4th
    channel. LoadImage hands over straight RGB (undefined where alpha is 0) and
    an inverted alpha as MASK, so encoding it as-is would bake whatever colour
    sits under the transparent area into the latent. Optionally resizes with
    lanczos, for promoting a rough render to the final size.
    """
    CATEGORY = "SD Studio"
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "prep"

    @classmethod
    def INPUT_TYPES(cls):
        size = {"default": 0, "min": 0, "max": 16384, "step": 8}
        return {"required": {
            "image": ("IMAGE",),
            "mask": ("MASK",),
            "width": ("INT", size),   # 0 = keep the source size
            "height": ("INT", size),
        }}

    def prep(self, image, mask, width, height):
        import numpy as np
        import torch
        from PIL import Image

        def to_pil(t):
            return Image.fromarray((t.clamp(0, 1).cpu().numpy() * 255).round().astype(np.uint8))

        def to_tensor(im):
            return torch.from_numpy(np.asarray(im).astype(np.float32) / 255.0)

        out = []
        for i in range(image.shape[0]):
            rgb = image[i, ..., :3].float().cpu()
            h, w = rgb.shape[:2]
            m = mask[min(i, mask.shape[0] - 1)] if mask.dim() == 3 else mask
            # LoadImage gives a 64x64 zero mask for images without alpha: opaque.
            alpha = (1.0 - m.float().cpu()) if tuple(m.shape) == (h, w) else torch.ones((h, w))
            comp = rgb * alpha[..., None] + (1.0 - alpha[..., None])
            if width and height and (width, height) != (w, h):
                comp = to_tensor(to_pil(comp).resize((width, height), Image.LANCZOS))
                alpha = to_tensor(to_pil(alpha).resize((width, height), Image.LANCZOS))
            out.append(torch.cat([comp, alpha[..., None]], dim=-1))
        return (torch.stack(out),)


NODE_CLASS_MAPPINGS = {"SDStudioAlphaPrep": SDStudioAlphaPrep}
NODE_DISPLAY_NAME_MAPPINGS = {"SDStudioAlphaPrep": "SD Studio: RGBA → VAE input (white composite)"}
