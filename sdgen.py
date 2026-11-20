#!/usr/bin/env python3
"""sdgen - SD Studio CLI for agents and humans.

On Windows run it through sdgen.bat, which picks ComfyUI's own Python.

Examples:
  sdgen "1girl, silver hair, smile" --model hoseki --lora mylora:0.8
  sdgen "same prompt" --model tekito --i2i base.png --denoise 0.55   # img2img
  sdgen --model tekito --run 28 --size 832x1216 --rough 0.65         # recipe batch
  sdgen "1girl, transparent background" -m tekito --vae anima_rgba --lora anima_rgba:1.0   # RGBA PNG
  sdgen --status
  sdgen --stop

Prints progress lines ("step 12/30") to stdout while generating and the
absolute path of each saved image at the end.
"""
import argparse
import asyncio
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.abspath(__file__))

# Piped or redirected output on Japanese Windows defaults to cp932, which cannot
# encode every model name. The portable build's Python runs isolated, so
# PYTHONUTF8 cannot fix it from outside; do it here.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and not _stream.isatty():
        _stream.reconfigure(encoding="utf-8")


def _config_port():
    """PORT from config.bat, so running sdgen.py directly hits the same engine."""
    try:
        with open(os.path.join(ROOT, "config.bat"), "rb") as fh:
            text = fh.read().decode("ascii", "ignore")
    except OSError:
        return None
    m = re.search(r'^\s*set\s+"PORT=(\d+)"', text, re.I | re.M)
    return int(m.group(1)) if m else None


PORT = int(os.environ.get("SD_STUDIO_PORT") or _config_port() or 8188)
API = f"http://127.0.0.1:{PORT}"
PORT_BUSY = (f"port {PORT} is used by another program (a ComfyUI left running?). "
             "Close it, or run setup.bat and choose another port.")
# The engine is always local. Windows system proxy settings would otherwise
# apply to 127.0.0.1 too when the bypass list is incomplete.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OUTPUTS = os.path.join(ROOT, "outputs")
CLIENT_ID = f"sdgen-{uuid.uuid4().hex[:8]}"

ARCH = {
    "sdxl":    {"steps": 25, "cfg": 6.0, "sampler": "euler_ancestral", "scheduler": "normal"},
    "anima":   {"steps": 30, "cfg": 4.0, "sampler": "euler", "scheduler": "simple",
                "clip": ("qwen_3_06b_base.safetensors", "stable_diffusion"), "vae": "qwen_image_vae.safetensors"},
    "z_image": {"steps": 8, "cfg": 1.0, "sampler": "res_multistep", "scheduler": "simple",
                "clip": ("qwen_3_4b.safetensors", "lumina2"), "vae": "ae.safetensors", "shift": 3.0},
    "unknown": {"steps": 25, "cfg": 6.0, "sampler": "euler", "scheduler": "normal"},
}

NEG_DEFAULT = "worst quality, low quality, bad hands"


def api_get(path, timeout=5):
    with _OPENER.open(API + path, timeout=timeout) as r:
        return json.load(r)


def api_post(path, payload):
    req = urllib.request.Request(
        API + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with _OPENER.open(req) as r:
        return json.load(r)


def upload_image(path, name):
    """Hand an image to the engine's input folder over HTTP.

    ComfyUI may live anywhere (portable build, Stability Matrix, ...), so the
    input folder is not something this script can find on disk.
    """
    boundary = uuid.uuid4().hex
    name = name.replace('"', "_")
    with open(path, "rb") as fh:
        data = fh.read()
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n", data, b"\r\n",
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n',
        f"--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        API + "/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with _OPENER.open(req) as r:
        info = json.load(r)
    return f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]


def engine_state():
    """'studio' when SD Studio answers, 'other' when a different server holds
    the port (typically a ComfyUI started on its own), 'down' when nothing does.
    """
    for path in ("/studio/api/ping", "/"):
        try:
            with _OPENER.open(API + path, timeout=3):
                pass
            return "studio" if path == "/studio/api/ping" else "other"
        except urllib.error.HTTPError:
            return "other"  # something speaks HTTP there, but not SD Studio
        except Exception:
            continue
    return "down"


def ensure_engine():
    state = engine_state()
    if state == "studio":
        return
    if state == "other":
        sys.exit("engine: " + PORT_BUSY)
    if os.name != "nt":
        sys.exit("engine: not running (start it with start.bat)")
    print("engine: starting...", flush=True)
    failed = os.path.join(ROOT, "engine.failed")
    if os.path.exists(failed):
        os.remove(failed)
    # A .bat needs a console to run in, so it cannot be spawned detached.
    # `start` gives it its own (minimised) window that outlives this CLI;
    # closing that window is also a way to stop the engine. The command line is
    # built by hand so the path is always quoted, whatever characters it has.
    #
    # The three DEVNULLs matter when sdgen's own output is captured (PowerShell
    # `$o = & .\sdgen.bat ...`, Python subprocess.run(capture_output=True)).
    # Without them Windows hands our stdout pipe on to `cmd /c start`, the
    # engine inherits it from there, and the caller then waits for a pipe that
    # stays open until the engine exits - it "hangs" after the image is done.
    # With explicit handles, Python limits inheritance to exactly those three.
    # The engine window is unaffected: `start` gives it a console of its own.
    comspec = os.environ.get("ComSpec", "cmd.exe")
    bat = os.path.join(ROOT, "start.bat")
    subprocess.Popen(f'"{comspec}" /c start "SD Studio engine" /min "{bat}"', cwd=ROOT,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    for _ in range(300):
        time.sleep(1)
        if engine_state() == "studio":
            print("engine: ready", flush=True)
            return
        if os.path.exists(failed):
            sys.exit("engine: failed to start; see the 'SD Studio engine' window")
    sys.exit("engine: did not answer within 5 minutes; see the 'SD Studio engine' window")


def stop_engine():
    state = engine_state()
    if state == "down":
        print("engine: already down")
        return
    if state == "other":
        sys.exit("engine: not stopping it - " + PORT_BUSY)
    try:
        api_post("/studio/api/engine/stop", {})
    except Exception:
        pass  # the server may drop the connection while exiting
    for _ in range(30):
        time.sleep(1)
        if engine_state() != "studio":
            print("engine: stopped")
            return
    sys.exit("engine: still running after 30s")


def resolve(query, entries, label):
    """Fuzzy-match query against model names; exact > prefix > substring."""
    names = [e["name"] for e in entries]
    q = query.lower()
    exact = [n for n in names if n.lower() in (q, q + ".safetensors")]
    prefix = [n for n in names if n.lower().startswith(q)]
    sub = [n for n in names if q in n.lower()]
    for pool in (exact, prefix, sub):
        if len(pool) == 1:
            n = pool[0]
            return next(e for e in entries if e["name"] == n)
        if len(pool) > 1:
            sys.exit(f"{label} '{query}' is ambiguous: {pool}")
    sys.exit(f"{label} '{query}' not found. available: {names}")


def build_graph(a, model, loras, models_info):
    arch = ARCH[model["arch"]]
    g = {}
    if model["kind"] == "ckpt":
        g["1"] = {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": model["name"]}}
        m, clip, vae = ["1", 0], ["1", 1], ["1", 2]
    else:
        comp = arch if "clip" in arch else ARCH["anima"]
        g["1"] = {"class_type": "UNETLoader", "inputs": {"unet_name": model["name"], "weight_dtype": "default"}}
        g["8"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": comp["clip"][0], "type": comp["clip"][1], "device": "default"}}
        g["9"] = {"class_type": "VAELoader", "inputs": {"vae_name": getattr(a, "vae", None) or comp["vae"]}}
        m, clip, vae = ["1", 0], ["8", 0], ["9", 0]
        if "shift" in comp:
            g["12"] = {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": m, "shift": comp["shift"]}}
            m = ["12", 0]

    nid = 20
    for lora_name, strength in loras:
        if model["kind"] == "ckpt":
            g[str(nid)] = {"class_type": "LoraLoader", "inputs": {
                "model": m, "clip": clip, "lora_name": lora_name,
                "strength_model": strength, "strength_clip": strength}}
            m, clip = [str(nid), 0], [str(nid), 1]
        else:
            g[str(nid)] = {"class_type": "LoraLoaderModelOnly", "inputs": {
                "model": m, "lora_name": lora_name, "strength_model": strength}}
            m = [str(nid), 0]
        nid += 1

    g["2"] = {"class_type": "CLIPTextEncode", "inputs": {"text": a.prompt, "clip": clip}}
    if model["arch"] == "z_image":
        g["3"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}}
    else:
        g["3"] = {"class_type": "CLIPTextEncode", "inputs": {"text": a.negative, "clip": clip}}

    denoise = 1.0
    if a.i2i:
        src = os.path.abspath(a.i2i)
        if not os.path.isfile(src):
            sys.exit(f"i2i image not found: {src}")
        dst_name = upload_image(src, f"sdgen_{uuid.uuid4().hex[:8]}_{os.path.basename(src)}")
        g["40"] = {"class_type": "LoadImage", "inputs": {"image": dst_name}}
        g["4"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["40", 0], "vae": vae}}
        denoise = a.denoise
    else:
        w, h = map(int, a.size.lower().split("x"))
        latent = "EmptySD3LatentImage" if model["arch"] == "z_image" else "EmptyLatentImage"
        g["4"] = {"class_type": latent, "inputs": {"width": w, "height": h, "batch_size": a.batch}}

    seed = a.seed if a.seed is not None else random.randrange(2 ** 48)
    g["5"] = {"class_type": "KSampler", "inputs": {
        "model": m, "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
        "seed": seed, "steps": a.steps or arch["steps"], "cfg": a.cfg or arch["cfg"],
        "sampler_name": a.sampler or arch["sampler"],
        "scheduler": a.scheduler or arch["scheduler"], "denoise": denoise}}
    g["6"] = {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": vae}}
    g["7"] = {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": a.prefix}}
    if not getattr(a, "quiet", False):
        print(f"seed: {seed}", flush=True)
    return g


async def watch_progress(prompt_id):
    """Stream step progress over websocket until the prompt finishes."""
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(f"{API}/ws?clientId={CLIENT_ID}") as ws:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                d = json.loads(msg.data)
                if d["type"] == "progress":
                    v, mx = d["data"]["value"], d["data"]["max"]
                    print(f"step {v}/{mx} ({v * 100 // mx}%)", flush=True)
                elif d["type"] in ("execution_success", "execution_error", "execution_interrupted"):
                    if d["data"].get("prompt_id") == prompt_id:
                        return d["type"]


def generate(a):
    ensure_engine()
    info = api_get("/studio/api/models", timeout=120)
    all_models = (
        [{**m, "kind": "ckpt"} for m in info["checkpoints"]] +
        [{**m, "kind": "dm"} for m in info["diffusion_models"]])
    model = resolve(a.model, all_models, "model")
    loras = []
    for spec in a.lora or []:
        name, _, strength = spec.partition(":")
        entry = resolve(name, info["loras"], "lora")
        loras.append((entry["name"], float(strength) if strength else 0.8))
    if a.vae:
        if model["kind"] == "ckpt":
            sys.exit("--vae is not supported for checkpoint models (their VAE is built in)")
        a.vae = resolve(a.vae, [{"name": n} for n in api_get("/models/vae")], "vae")["name"]

    print(f"model: {model['name']} [{model['arch']}]", flush=True)
    for n, s in loras:
        print(f"lora: {n} @{s}", flush=True)
    if a.vae:
        print(f"vae: {a.vae}", flush=True)

    g = build_graph(a, model, loras, info)
    pid = api_post("/prompt", {"prompt": g, "client_id": CLIENT_ID})["prompt_id"]
    print(f"queued: {pid}", flush=True)

    try:
        outcome = asyncio.run(asyncio.wait_for(watch_progress(pid), timeout=3600))
    except Exception:
        outcome = None  # websocket died; fall through to history polling

    for _ in range(360):
        h = api_get(f"/history/{pid}")
        if pid in h:
            st = h[pid]["status"]
            if st.get("completed"):
                for out in h[pid]["outputs"].values():
                    for im in out.get("images", []):
                        print(os.path.join(OUTPUTS, im["subfolder"], im["filename"]))
                return
            if st.get("status_str") == "error":
                for mtype, mdata in st.get("messages", []):
                    if mtype == "execution_error":
                        sys.exit("error: " + mdata.get("exception_message", "unknown"))
                sys.exit("error: generation failed")
        if outcome == "execution_interrupted":
            sys.exit("interrupted")
        time.sleep(5)
    sys.exit("timeout")


def align64(n):
    """Every one of these models expects 64px-aligned latents."""
    return max(64, round(n / 64) * 64)


def compose_prompt(recipe, picks):
    """Fill the template's __key__ placeholders, then tidy the leftover commas."""
    out = recipe["template"]
    for slot in recipe["slots"]:
        opt = picks.get(slot["key"])
        out = out.replace(f"__{slot['key']}__", opt["text"] if opt else "")
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r"(,\s*)+", ", ", out)
    return out.strip(" ,")


def run_batch(a):
    """Queue N images drawn from the recipe as one run, then return immediately.

    The engine keeps generating after this exits - that is the point. Progress
    and selection happen in the review UI, not here.
    """
    ensure_engine()
    info = api_get("/studio/api/models", timeout=120)
    all_models = (
        [{**m, "kind": "ckpt"} for m in info["checkpoints"]] +
        [{**m, "kind": "dm"} for m in info["diffusion_models"]])
    model = resolve(a.model, all_models, "model")
    loras = []
    for spec in a.lora or []:
        name, _, strength = spec.partition(":")
        entry = resolve(name, info["loras"], "lora")
        loras.append((entry["name"], float(strength) if strength else 0.8))

    recipe = api_get("/studio/api/recipe")
    if not recipe.get("slots"):
        sys.exit("no recipe: check wildcards/_slots.json")

    arch = ARCH[model["arch"]]
    width, height = map(int, a.size.lower().split("x"))
    final_steps = a.steps or arch["steps"]
    if a.rough < 1.0:
        render = {"width": align64(width * a.rough), "height": align64(height * a.rough),
                  "steps": a.rough_steps or max(4, round(final_steps * 0.47))}
        mode = "rough"
    else:
        render = {"width": width, "height": height, "steps": final_steps}
        mode = "final"

    run_id = api_post("/studio/api/runs/new", {"mode": mode, "meta": {
        "model": model["name"], "arch": model["arch"], "kind": model["kind"],
        "folder": "checkpoints" if model["kind"] == "ckpt" else "diffusion_models",
        "loras": [{"name": n, "strength": s} for n, s in loras],
        "negative": a.negative,
        "cfg": a.cfg or arch["cfg"],
        "sampler": a.sampler or arch["sampler"],
        "scheduler": a.scheduler or arch["scheduler"],
        "final": {"width": width, "height": height, "steps": final_steps},
        "render": render,
        "template": recipe["template"],
    }})["run_id"]

    items = []
    for i in range(a.run):
        picks = {s["key"]: random.choice(s["options"])
                 for s in recipe["slots"] if s["options"]}
        items.append({"index": i, "seed": random.randrange(2 ** 48),
                      "prompt": compose_prompt(recipe, picks),
                      "picks": {k: v["label"] for k, v in picks.items()}})
    api_post(f"/studio/api/runs/{run_id}/items", {"items": items})

    for it in items:
        shim = argparse.Namespace(**vars(a))
        shim.quiet, shim.i2i, shim.batch = True, None, 1
        shim.prompt, shim.seed = it["prompt"], it["seed"]
        shim.size = f"{render['width']}x{render['height']}"
        shim.steps = render["steps"]
        shim.prefix = f"{run_id}/{it['index']:05d}"
        api_post("/prompt", {"prompt": build_graph(shim, model, loras, info),
                             "client_id": CLIENT_ID})

    print(f"run: {run_id}  model: {model['name']} [{model['arch']}]  "
          f"{a.run} images  {render['width']}x{render['height']}/{render['steps']}steps  [{mode}]",
          flush=True)
    return run_id


def status():
    state = engine_state()
    if state == "down":
        print("engine: down")
        return
    if state == "other":
        print("engine: " + PORT_BUSY)
        return
    q = api_get("/queue")
    running = len(q["queue_running"])
    pending = len(q["queue_pending"])
    print(f"engine: up / running: {running} / pending: {pending}")


def main():
    p = argparse.ArgumentParser(prog="sdgen", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("prompt", nargs="?", help="positive prompt")
    p.add_argument("--model", "-m", help="model name (partial match ok: hoseki, tekito, rin...)")
    p.add_argument("--lora", "-l", action="append", metavar="NAME[:STRENGTH]",
                   help="add a lora, repeatable (default strength 0.8)")
    p.add_argument("--vae", help="override the arch's VAE, partial match ok (single t2i only: --run/--i2i "
                                 "would lose the alpha when promoting or re-encoding)")
    p.add_argument("--negative", "-n", default=NEG_DEFAULT)
    p.add_argument("--i2i", metavar="IMAGE", help="reference image for img2img")
    p.add_argument("--denoise", type=float, default=0.6, help="i2i denoise (default 0.6)")
    p.add_argument("--size", default="1024x1024", help="WxH for t2i (default 1024x1024)")
    p.add_argument("--steps", type=int, help="override arch default")
    p.add_argument("--cfg", type=float, help="override arch default")
    p.add_argument("--sampler", help="override arch default")
    p.add_argument("--scheduler", help="override arch default")
    p.add_argument("--seed", type=int, help="fixed seed (default: random)")
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--prefix", default="sdgen", help="output filename prefix")
    p.add_argument("--run", type=int, metavar="N",
                   help="queue N images drawn from the recipe (wildcards/) as one run")
    p.add_argument("--rough", type=float, default=1.0, metavar="SCALE",
                   help="render at SCALE of --size to sift more images (e.g. 0.65)")
    p.add_argument("--rough-steps", type=int, help="steps for the rough pass (default: 47%% of full)")
    p.add_argument("--status", action="store_true", help="show engine/queue state")
    p.add_argument("--stop", action="store_true", help="stop the engine")
    a = p.parse_args()

    if a.vae and (a.run or a.i2i):
        p.error("--vae works only with single t2i generation (not --run or --i2i)")
    if a.stop:
        stop_engine()
    elif a.status:
        status()
    elif a.run and a.model:
        run_batch(a)
    elif a.prompt and a.model:
        generate(a)
    else:
        p.error("need PROMPT and --model, or --run N and --model (or --status / --stop)")


if __name__ == "__main__":
    main()
