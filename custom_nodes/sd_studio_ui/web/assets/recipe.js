// Recipe panel: element slots, wildcard drawing, and the batch runner.
//
// The idea it implements: an illustration is a set of independent elements
// (魅せカット / 構図 / カメラ / ...). Each slot is either fixed or drawn at
// random, so hundreds of images can be queued from one template and every
// image remembers which options produced it (see runs/<id>.json).

const Recipe = (() => {
  const RANDOM = "__random__";
  const OFF = "__off__";

  let recipe = null;      // {template, slots:[{key,label,hero,options,raw}]}
  let state = {};         // slot key -> RANDOM | OFF | option label
  let draw = null;        // {picks: {key: {label, text}}, prompt}
  let ctx = null;         // supplied by index.html
  let editing = null;     // slot key currently open in the editor
  let alpha = false;      // transparent output: ALPHA.skipSlots and options tagged
                          // ALPHA.skipTag are left out of every draw

  const skipped = key => alpha && ALPHA.skipSlots.includes(key);
  /** The options a draw may use: all of them, minus the place-drawing ones when transparent. */
  const poolOf = s => (alpha ? s.options.filter(o => !alphaSkips(o)) : s.options);

  const $ = id => document.getElementById(id);
  const slotOf = key => recipe.slots.find(s => s.key === key);

  const post = (path, body) =>
    fetch(API + path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });

  // ---------- load & render ----------
  async function load() {
    recipe = await fetch(API + "/studio/api/recipe").then(r => r.json());
    if (recipe.error) {
      $("slots").innerHTML = `<div class="dim-note">${recipe.error}</div>`;
      return;
    }
    for (const s of recipe.slots) {
      if (!(s.key in state)) state[s.key] = RANDOM;
    }
    renderSlots();
    reroll();
  }

  function renderSlots() {
    const host = $("slots");
    host.innerHTML = "";
    for (const s of recipe.slots) {
      const row = document.createElement("div");
      row.className = "slot-row" + (s.hero ? " hero" : "");

      const name = document.createElement("div");
      name.className = "slot-name";
      name.textContent = s.label;
      name.title = `__${s.key}__`;

      const sel = document.createElement("select");
      sel.className = "slot-sel";
      const add = (value, text, disabled = false) => {
        const o = document.createElement("option");
        o.value = value; o.textContent = text; o.disabled = disabled;
        sel.appendChild(o);
      };
      const pool = poolOf(s);
      const out = s.options.length - pool.length;  // tagged 場所 while transparent
      add(RANDOM, out ? `🎲 ランダム (${pool.length}/${s.options.length})` : `🎲 ランダム (${s.options.length})`);
      add(OFF, "— 使わない");
      for (const o of s.options) {
        const off = alpha && alphaSkips(o);
        add(o.label, off ? `${o.label}（透過では使わない）` : o.label, off);
      }
      // A fixed pick that transparency rules out draws from the pool instead;
      // the choice itself is kept and comes back when transparency is turned off.
      const fixed = s.options.find(o => o.label === state[s.key]);
      sel.value = fixed && alpha && alphaSkips(fixed) ? RANDOM : state[s.key];
      if (out && !skipped(s.key)) {
        sel.title = `透過PNGのあいだは「${ALPHA.skipTag}」印の${out}件を抽選から外す（背景を描かせて透過と衝突するため）`;
      }
      sel.onchange = () => { state[s.key] = sel.value; reroll(); };
      if (skipped(s.key)) {
        sel.disabled = true;
        row.style.opacity = 0.45;
        row.title = "透過PNGのあいだは使わない（場所の指定が透過と衝突するため）";
      }

      const edit = document.createElement("button");
      edit.className = "slot-edit";
      edit.textContent = "✎";
      edit.title = "選択肢を編集";
      edit.onclick = () => openEditor(s.key);

      row.append(name, sel, edit);
      host.appendChild(row);
    }
  }

  // ---------- drawing ----------
  const pick = arr => arr[Math.floor(Math.random() * arr.length)];

  /** One independent draw across every slot. Fixed slots always yield the same option. */
  function drawPicks() {
    const picks = {};
    for (const s of recipe.slots) {
      const mode = state[s.key];
      const pool = poolOf(s);
      if (mode === OFF || !pool.length || skipped(s.key)) continue;
      picks[s.key] = (mode !== RANDOM && pool.find(o => o.label === mode)) || pick(pool);
    }
    return picks;
  }

  /** Fill the template's __key__ placeholders, then tidy the leftover commas. */
  function compose(picks) {
    let out = recipe.template;
    for (const s of recipe.slots) {
      out = out.split(`__${s.key}__`).join(picks[s.key] ? picks[s.key].text : "");
    }
    return out
      .replace(/\s+/g, " ")
      .replace(/(,\s*)+/g, ", ")
      .replace(/^[,\s]+|[,\s]+$/g, "");
  }

  function reroll() {
    if (!recipe || recipe.error) return;
    const picks = drawPicks();
    draw = { picks, prompt: compose(picks) };
    ctx.refreshComposed();  // never touch the prompt box; the user owns it
    const hero = recipe.slots.find(s => s.hero);
    $("drawNote").textContent = hero && picks[hero.key]
      ? `${hero.label}: ${picks[hero.key].label}` : "";
  }

  // ---------- slot editor ----------
  function openEditor(key) {
    editing = key;
    const s = slotOf(key);
    $("editTitle").textContent = `${s.label}（__${s.key}__）の選択肢`;
    $("editArea").value = s.raw;
    $("editOverlay").classList.add("open");
  }

  async function saveEditor() {
    const raw = $("editArea").value;
    try {
      const res = await post(`/studio/api/recipe/slot/${editing}`, { raw });
      const s = slotOf(editing);
      s.raw = raw;
      s.options = res.options;
      if (state[editing] !== RANDOM && state[editing] !== OFF &&
          !s.options.some(o => o.label === state[editing])) {
        state[editing] = RANDOM;  // the fixed option was edited away
      }
      renderSlots();
      reroll();
      $("editOverlay").classList.remove("open");
      ctx.setStatus(`${s.label}: ${res.options.length}件を保存しました`);
    } catch (e) {
      ctx.setStatus("保存に失敗: " + e.message);
    }
  }

  async function saveTemplate() {
    const template = $("editArea").value;
    try {
      await post("/studio/api/recipe/template", { template });
      recipe.template = template;
      reroll();
      $("editOverlay").classList.remove("open");
      ctx.setStatus("テンプレートを保存しました");
    } catch (e) {
      ctx.setStatus("保存に失敗: " + e.message);
    }
  }

  function openTemplateEditor() {
    editing = null;
    $("editTitle").textContent = "プロンプトテンプレート（__スロット名__ が抽選結果に置き換わる）";
    $("editArea").value = recipe.template;
    $("editOverlay").classList.add("open");
  }

  // ---------- batch runner ----------
  function batchSize() {
    const s = ctx.getSettings();
    const rough = $("batchMode").value === "rough";
    if (!rough) return { width: s.width, height: s.height, steps: s.steps, rough };
    const scale = parseFloat($("roughScale").value) || 0.65;
    return {
      width: align64(s.width * scale),
      height: align64(s.height * scale),
      steps: parseInt($("roughSteps").value) || 14,
      rough,
    };
  }

  /** Rough passes are cheaper than the measured full-size rate; scale by pixels x steps. */
  function updateEstimate() {
    const per = parseFloat(localStorage.getItem("sdstudio.secPerImage") || "0");
    const n = parseInt($("batchCount").value) || 0;
    const el = $("batchEstimate");
    if (!per) {
      el.textContent = `${n}枚 — 所要時間は1枚生成すると実測から出ます`;
      return;
    }
    const s = ctx.getSettings();
    const b = batchSize();
    const ref = parseFloat(localStorage.getItem("sdstudio.refCost") || "0");
    const cost = b.width * b.height * b.steps;
    const secs = per * (ref ? cost / ref : 1) * n;
    const h = Math.floor(secs / 3600), m = Math.round((secs % 3600) / 60);
    el.textContent = `${n}枚 ${b.width}x${b.height}/${b.steps}steps — 推定 約${h > 0 ? h + "時間" : ""}${m}分`
      + (b.rough ? `（本番は ${s.width}x${s.height}）` : "");
  }

  async function runBatch() {
    const btn = $("batchRun");
    const s = ctx.getSettings();
    if (!s.model) { ctx.setStatus("モデルが選択されていません"); return; }
    const n = parseInt($("batchCount").value) || 0;
    if (n < 1) return;
    const b = batchSize();

    btn.disabled = true;
    try {
      const { run_id } = await post("/studio/api/runs/new", {
        mode: b.rough ? "rough" : "final",
        meta: {
          model: s.model.name, arch: s.model.arch, kind: s.model.kind, folder: s.model.folder,
          loras: s.loras, negative: s.negative,
          cfg: s.cfg, sampler: s.sampler, scheduler: s.scheduler,
          final: { width: s.width, height: s.height, steps: s.steps },
          render: { width: b.width, height: b.height, steps: b.steps },
          template: recipe.template,
          base_prompt: ctx.userPrompt(),
          ...(s.alpha ? { alpha: true } : {}),  // promotion reads this back
        },
      });

      const items = [];
      for (let i = 0; i < n; i++) {
        const picks = drawPicks();
        const labels = {};
        for (const [k, v] of Object.entries(picks)) labels[k] = v.label;
        // same join as the single shot: hand-written prompt first, draw after
        const prompt = ctx.composePrompt(compose(picks));
        items.push({
          index: i,
          seed: Math.floor(Math.random() * 2 ** 48),
          // the ledger keeps what was actually sent, trigger included
          prompt: s.alpha ? alphaPrompt(prompt) : prompt,
          picks: labels,
        });
      }
      await post(`/studio/api/runs/${run_id}/items`, { items });

      for (const it of items) {
        const graph = buildWorkflow({
          model: s.model, loras: s.loras, prompt: it.prompt, negative: s.negative,
          width: b.width, height: b.height, batch: 1,
          steps: b.steps, cfg: s.cfg, sampler: s.sampler, scheduler: s.scheduler,
          alpha: s.alpha,
          seed: it.seed, prefix: `${run_id}/${String(it.index).padStart(5, "0")}`,
        });
        await enqueue(graph, ctx.clientId);
        if (it.index % 10 === 0 || it.index === n - 1) {
          ctx.setStatus(`キュー投入 ${it.index + 1}/${n}`);
        }
      }
      ctx.setStatus(`${n}枚をキューに投入しました（run ${run_id}）。\n`
        + "このタブを閉じてもエンジン側で生成は続きます。終わったら選別ビューへ。");
      $("toReview").href = `/studio/review?run=${run_id}`;
      $("toReview").style.display = "block";
    } catch (e) {
      ctx.setStatus("バッチ投入に失敗: " + e.message);
    }
    btn.disabled = false;
  }

  // ---------- wiring ----------
  function init(context) {
    ctx = context;
    $("reroll").onclick = reroll;
    $("editTemplate").onclick = openTemplateEditor;
    $("editSave").onclick = () => (editing ? saveEditor() : saveTemplate());
    $("editCancel").onclick = () => $("editOverlay").classList.remove("open");
    $("useRecipe").onchange = () => {
      $("recipeBody").style.display = $("useRecipe").checked ? "block" : "none";
      if ($("useRecipe").checked) reroll();
      ctx.refreshComposed();  // turning the recipe off hides the preview
    };
    $("batchMode").onchange = () => {
      $("roughOpts").style.display = $("batchMode").value === "rough" ? "flex" : "none";
      updateEstimate();
    };
    for (const id of ["batchCount", "roughScale", "roughSteps"]) {
      $(id).oninput = updateEstimate;
    }
    $("batchRun").onclick = runBatch;
    load().then(updateEstimate);
  }

  /** Turn transparent output on/off: greys out the skipped slots and 場所 options, then redraws. */
  function setAlpha(on) {
    if (on === alpha) return;
    alpha = on;
    if (recipe && !recipe.error) { renderSlots(); reroll(); }
  }

  return {
    init,
    reroll,
    setAlpha,
    updateEstimate,
    enabled: () => $("useRecipe").checked && recipe && !recipe.error,
    currentDraw: () => draw,
  };
})();
