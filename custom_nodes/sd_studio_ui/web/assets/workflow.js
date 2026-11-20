// Shared workflow builder for SD Studio (used by index.html and review.html).
//
// buildWorkflow() is a pure function: it takes a plain settings object and
// returns a ComfyUI prompt graph. Both the single-shot generate button and the
// batch runner go through it, so a fix here applies to every path.

const API = location.origin;

// per-architecture pipeline settings (from official ComfyUI templates)
const ARCH = {
  sdxl:    { label: "SDXL",    color: "var(--c-sdxl)",    steps: 25, cfg: 6.0, sampler: "euler_ancestral", scheduler: "normal" },
  anima:   { label: "Anima",   color: "var(--c-anima)",   steps: 30, cfg: 4.0, sampler: "euler", scheduler: "simple",
             clip: ["qwen_3_06b_base.safetensors", "stable_diffusion"], vae: "qwen_image_vae.safetensors" },
  z_image: { label: "Z-Image", color: "var(--c-zimage)",  steps: 8, cfg: 1.0, sampler: "res_multistep", scheduler: "simple",
             clip: ["qwen_3_4b.safetensors", "lumina2"], vae: "ae.safetensors", shift: 3.0 },
  unknown: { label: "不明",     color: "var(--c-unknown)", steps: 25, cfg: 6.0, sampler: "euler", scheduler: "normal" },
};
const ARCH_ORDER = ["anima", "z_image", "sdxl", "unknown"];

/**
 * Build a ComfyUI prompt graph.
 *
 * Example — one 832x1216 Anima image with a LoRA:
 *   buildWorkflow({
 *     model: { kind: "dm", arch: "anima", name: "hoseki.safetensors", folder: "diffusion_models" },
 *     loras: [{ name: "mylora.safetensors", strength: 0.8 }],
 *     prompt: "1girl, ...", negative: "worst quality",
 *     width: 832, height: 1216, batch: 1,
 *     steps: 30, cfg: 4, sampler: "euler", scheduler: "simple",
 *     seed: 7777, prefix: "studio",
 *   })
 *
 * Passing `i2iImage` (a filename already in ComfyUI's input dir) switches the
 * graph to img2img and uses `denoise`; width/height/batch are then ignored
 * because the reference image dictates the latent size.
 */
function buildWorkflow(o) {
  const m = o.model;
  const g = {};
  let model, clip, vae;

  if (m.kind === "ckpt") {
    g["1"] = { class_type: "CheckpointLoaderSimple", inputs: { ckpt_name: m.name } };
    model = ["1", 0]; clip = ["1", 1]; vae = ["1", 2];
  } else {
    const a = ARCH[m.arch].clip ? ARCH[m.arch] : ARCH.anima; // unknown: try anima parts
    g["1"] = { class_type: "UNETLoader", inputs: { unet_name: m.name, weight_dtype: "default" } };
    g["8"] = { class_type: "CLIPLoader", inputs: { clip_name: a.clip[0], type: a.clip[1], device: "default" } };
    g["9"] = { class_type: "VAELoader", inputs: { vae_name: a.vae } };
    model = ["1", 0]; clip = ["8", 0]; vae = ["9", 0];
    if (a.shift) {
      g["12"] = { class_type: "ModelSamplingAuraFlow", inputs: { model, shift: a.shift } };
      model = ["12", 0];
    }
  }

  let id = 20;
  for (const lora of o.loras || []) {
    if (!lora.name) continue;
    if (m.kind === "ckpt") {
      g[String(id)] = { class_type: "LoraLoader", inputs: {
        model, clip, lora_name: lora.name,
        strength_model: lora.strength, strength_clip: lora.strength } };
      model = [String(id), 0]; clip = [String(id), 1];
    } else {
      g[String(id)] = { class_type: "LoraLoaderModelOnly", inputs: {
        model, lora_name: lora.name, strength_model: lora.strength } };
      model = [String(id), 0];
    }
    id++;
  }

  g["2"] = { class_type: "CLIPTextEncode", inputs: { text: o.prompt, clip } };
  if (m.arch === "z_image") {
    // turbo runs at cfg 1: feed a zeroed-out conditioning as negative
    g["3"] = { class_type: "ConditioningZeroOut", inputs: { conditioning: ["2", 0] } };
  } else {
    g["3"] = { class_type: "CLIPTextEncode", inputs: { text: o.negative, clip } };
  }

  let denoise = 1;
  if (o.i2iImage) {
    g["40"] = { class_type: "LoadImage", inputs: { image: o.i2iImage } };
    if (o.width && o.height) {
      // promoting a rough render: scale the reference up to the target size first
      g["41"] = { class_type: "ImageScale", inputs: {
        image: ["40", 0], width: o.width, height: o.height,
        upscale_method: "lanczos", crop: "disabled" } };
      g["4"] = { class_type: "VAEEncode", inputs: { pixels: ["41", 0], vae } };
    } else {
      g["4"] = { class_type: "VAEEncode", inputs: { pixels: ["40", 0], vae } };
    }
    denoise = o.denoise;
  } else {
    const latentClass = m.arch === "z_image" ? "EmptySD3LatentImage" : "EmptyLatentImage";
    g["4"] = { class_type: latentClass, inputs: {
      width: o.width, height: o.height, batch_size: o.batch || 1 } };
  }

  g["5"] = { class_type: "KSampler", inputs: {
    model, positive: ["2", 0], negative: ["3", 0], latent_image: ["4", 0],
    seed: o.seed, steps: o.steps, cfg: o.cfg,
    sampler_name: o.sampler, scheduler: o.scheduler, denoise } };
  g["6"] = { class_type: "VAEDecode", inputs: { samples: ["5", 0], vae } };
  g["7"] = { class_type: "SaveImage", inputs: { images: ["6", 0], filename_prefix: o.prefix } };
  return g;
}

async function enqueue(graph, clientId) {
  const r = await fetch(`${API}/prompt`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: graph, client_id: clientId }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.error?.message || `HTTP ${r.status}`);
  }
  return (await r.json()).prompt_id;
}

const outUrl = (filename, subfolder = "") =>
  `${API}/view?filename=${encodeURIComponent(filename)}&subfolder=${encodeURIComponent(subfolder)}&type=output`;

// 64px-aligned scaling, the granularity every one of these models expects
const align64 = n => Math.max(64, Math.round(n / 64) * 64);
