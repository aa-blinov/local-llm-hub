// Targeted DOM writes: touch an element only when its value changes.
function setDis(id, v) { const el = document.getElementById(id); if (el && el.disabled !== !!v) el.disabled = !!v; }
function setCls(id, cls) { const el = document.getElementById(id); if (el && el.className !== cls) el.className = cls; }
function setPrimary(id, on) { const el = document.getElementById(id); if (el && el.classList.contains("primary") !== !!on) el.classList.toggle("primary", !!on); }

// Skip writes when the content has not changed, so periodic refreshes do not flicker.
(function () {
  const dHTML = Object.getOwnPropertyDescriptor(Element.prototype, "innerHTML");
  Object.defineProperty(Element.prototype, "innerHTML", {
    get() { return dHTML.get.call(this); },
    set(v) {
      const h = String(v);
      if (this.__lastHTML === h) return;
      this.__lastHTML = h; this.__lastText = null;
      dHTML.set.call(this, h);
    },
  });
  const dText = Object.getOwnPropertyDescriptor(Node.prototype, "textContent");
  Object.defineProperty(Node.prototype, "textContent", {
    get() { return dText.get.call(this); },
    set(v) {
      const t = String(v);
      if (this.__lastText === t) return;
      this.__lastText = t; this.__lastHTML = null;
      dText.set.call(this, t);
    },
  });
})();

// Local LLM Hub: web interface. No build step, no external libraries.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const gib = (v) => (v == null ? "—" : v.toFixed(2) + " GiB");
const fmt = (v, u = "") => (v == null ? "—" : v + u);

let catalog = null;
let status = null;
let comps = [];
let simpleRisk = false, settingsRisk = false;  // last memory verdict is "risk": Start asks first
let preflightTimer = null;
let dlTimer = null;
let jobWatch = null;

// Labels for the simple view. Keys come from config/registry.json.
const SIMPLE_PRESETS = {
  chat: "Chat — for conversations and questions (quick start)",
  coding: "Coding — for code (remembers more text)",
};

// Turn backend errors into plain instructions. The original text stays in the log.
const FRIENDLY = [
  [/another operation on this component/, () => "This operation is already running. Wait for it to finish."],
  [/port (\d+) is already in use/, (m) => `Port ${m[1]} is used by another program. Close it or restart your Mac.`],
  [/engine binary not found/, () => "The model engine is not installed. Install it in step 1."],
  [/model files not found/, () => "The model is not downloaded. Download it in step 2."],
  [/the engine is already running/, () => "The assistant is already running."],
  [/the model is still loading/, () => "The model is still loading. Wait about a minute and try again."],
  [/the engine is not running/, () => "Start the assistant first (step 3)."],
  [/the engine is running: stop it first/, () => "Stop the assistant first, then remove the program."],
  [/the model is running: stop/, () => "Stop the assistant first, then remove the model."],
  [/the download is already running/, () => "The download is already in progress."],
  [/no such preset/, () => "This mode does not exist. Choose one from the list."],
];
function friendly(msg) {
  if (!msg) return "Something went wrong. Check the program log.";
  for (const [re, fn] of FRIENDLY) {
    const m = String(msg).match(re);
    if (m) return fn(m);
  }
  return msg;
}

async function api(path, body) {
  const opts = body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opts);
  return r.json();
}

// ---- catalog ----
function fillCatalog(c) {
  catalog = c;
  // advanced view
  const pre = $("preset");
  pre.add(new Option("— manual —", ""));
  for (const [k, p] of Object.entries(c.presets)) pre.add(new Option(p.label, k));
  const eng = $("engine");
  for (const [k, e] of Object.entries(c.engines)) eng.add(new Option(e.label + (e.binary_ok ? "" : " (not installed)"), k));
  eng.onchange = () => { fillModels(); fillCtx(); refreshPreflight(); };
  $("model").onchange = () => { ctxTouched = false; fillCtx(); refreshPreflight(); updateDownload(); };
  $("ctx").onchange = () => { ctxTouched = true; refreshPreflight(); };
  $("prefill").onchange = refreshPreflight;
  pre.onchange = applyPreset;
  $("start").onclick = startAdvanced;
  $("stop").onclick = stopEngine;
  $("send").onclick = () => sendChat($("prompt").value, +$("maxtok").value, $("answer"), $("chatstat"));
  $("reflog").onclick = refreshLog;
  $("download").onclick = () => startModelDownload($("model").value);
  $("cacheclear").onclick = clearCache;
  $("ocsync").onclick = syncOpencode;
  const d = c.default || {};
  eng.value = (c.models[d.model] || {}).engine || Object.keys(c.engines)[0];
  fillModels(d.model);
  fillCtx(d.ctx);
  fillPrefill(d.prefill);
  $("apc").checked = d.apc !== false;
  $("apcmem").value = d.apc_mem_gb || 6;

  // simple view
  rebuildSimpleModels(d.model);
  const sm = $("s-model");
  const sp = $("s-preset");
  for (const [k, label] of Object.entries(SIMPLE_PRESETS)) if (c.presets[k]) sp.add(new Option(label, k));
  sp.value = "chat";
  sm.onchange = () => { fillModes(true); renderSimple(); refreshPreflight(); };
  $("s-purpose").onchange = refreshRecommend;
  $("s-recommend-btn").onclick = () => {
    if (!recommendedKey) return;
    sm.value = recommendedKey;
    sm.onchange();
  };
  refreshRecommend();
  sp.onchange = () => { renderSimple(); refreshPreflight(); };
  $("s-engine-btn").onclick = installEngineForSimple;
  $("s-model-btn").onclick = () => startModelDownload($("s-model").value);
  $("s-start").onclick = startSimple;
  $("s-stop").onclick = stopEngine;
  $("s-send").onclick = () => sendChat($("s-prompt").value, 600, $("s-answer"), $("s-chatstat"), $("s-mode").value);
  $("s-copy").onclick = async () => {
    try { await navigator.clipboard.writeText(lastAnswer); $("s-chatstat").textContent = "Answer copied. Paste it into Word or Pages."; }
    catch (e) { $("s-chatstat").textContent = "Could not copy. Select the answer with the mouse and press Command+C."; }
  };

  fillModels(d.model);
  refreshPreflight();
}

// Sampling modes of the selected model; the row is hidden when the model has none.
function fillModes(resetToDefault) {
  const sel = $("s-mode");
  const info = catalog && catalog.models[$("s-model").value];
  const modes = (info && info.modes) || [];
  const keep = sel.value;
  while (sel.options.length) sel.remove(0);  // innerHTML is guarded against no-op writes, so clear explicitly
  for (const m of modes) sel.add(new Option(m.label, m.key));
  const keepable = !resetToDefault && modes.some((m) => m.key === keep);
  sel.value = keepable && keep ? keep : ((info && info.default_mode) || (modes[0] ? modes[0].key : ""));
  $("s-mode-row").hidden = modes.length < 2;  // one optimal mode per model: nothing to choose
}

function rebuildSimpleModels(selected) {
  const sm = $("s-model");
  const keep = selected || sm.value;
  sm.innerHTML = "";
  for (const [k, info] of Object.entries(catalog.models)) {
    if (!info.simple && !info.exists) continue;
    sm.add(new Option(info.label, k));
  }
  sm.value = [...sm.options].some((o) => o.value === keep) ? keep : (sm.options[0] ? sm.options[0].value : "");
  fillModes();
}

function fillModels(selected) {
  const key = $("engine").value;
  const m = $("model");
  m.innerHTML = "";
  for (const [k, info] of Object.entries(catalog.models)) {
    if (info.engine !== key) continue;
    m.add(new Option(info.label + (info.exists ? "" : " (not downloaded)"), k));
  }
  if (selected && [...m.options].some((o) => o.value === selected)) m.value = selected;
  updateDownload();
}

// Context advice from this Mac's total memory. Until the user picks a context, the field follows the advice.
let ctxTouched = false;
async function refreshCtxAdvice() {
  const key = $("model").value;
  const box = $("ctx-advice");
  if (!key || $("engine").value !== "mlx") { box.textContent = ""; return; }
  const a = await api(`/api/context-advice?model=${encodeURIComponent(key)}`);
  if (!a || !a.ok) { box.textContent = (a && a.message) || ""; return; }
  box.textContent = `${a.message} Reading step ${a.prefill}, prefix cache ${a.apc_mem_gb} GB.`;
  if (!ctxTouched && a.ctx) { $("ctx").value = String(a.ctx); refreshPreflight(); }
}

function fillCtx(selected) {
  const e = catalog.engines[$("engine").value];
  const cs = $("ctx");
  cs.innerHTML = "";
  for (const c of e.ctx_choices) cs.add(new Option(c.toLocaleString("en-US") + " tokens", c));
  if (selected) cs.value = selected;
  $("mlxopts").style.display = $("engine").value === "mlx" ? "" : "none";
  fillPrefill();
  refreshCtxAdvice();
}

function fillPrefill(selected) {
  const e = catalog.engines[$("engine").value];
  const ps = $("prefill");
  ps.innerHTML = "";
  for (const p of e.prefill_choices) ps.add(new Option(p, p));
  if (selected) ps.value = selected;
}

function applyPreset() {
  const p = catalog.presets[$("preset").value];
  if (!p) return;
  $("engine").value = p.engine;
  fillModels(p.model);
  fillCtx(p.ctx);
  fillPrefill(p.prefill);
  $("apc").checked = p.apc !== false;
  if (p.apc_mem_gb) $("apcmem").value = p.apc_mem_gb;
  refreshPreflight();
}

function updateDownload() {
  const info = catalog.models[$("model").value];
  const btn = $("download");
  if (!info) { btn.disabled = true; return; }
  btn.disabled = info.exists || !info.can_download;
  btn.textContent = info.exists ? "Model on disk" : "Download model";
  $("dlstate").textContent = info.can_download ? "" : "This model must be placed on disk by hand";
}

// ---- memory check ----
function refreshPreflight() {
  clearTimeout(preflightTimer);
  preflightTimer = setTimeout(async () => {
    const model = $("model").value;
    const ctx = $("ctx").value;
    if (model && ctx) {
      const v = await api(`/api/preflight?model=${encodeURIComponent(model)}&ctx=${ctx}`);
      const el = $("verdict");
      el.className = "verdict " + ({ ok: "good", tight: "warn", risk: "bad" }[v.verdict] || "");
      el.textContent = v.verdict === "unknown" ? (v.message || "Memory check is not available") : v.message;
      settingsRisk = v.verdict === "risk";
    }
    const sm = $("s-model").value;
    const sp = $("s-preset").value;
    const ctxSimple = catalog.presets[sp] ? catalog.presets[sp].ctx : 32768;
    if (sm) {
      const v = await api(`/api/preflight?model=${encodeURIComponent(sm)}&ctx=${ctxSimple}`);
      const text = {
        ok: ["good", "There is enough memory."],
        tight: ["warn", "Memory is tight. Close large apps such as browsers with many tabs or video editors."],
        risk: ["bad", "There may not be enough memory. Choose the Chat mode or close other apps."],
      }[v.verdict] || ["", "Memory check is not available."];
      $("s-memory").className = "verdict " + text[0];
      $("s-memory").textContent = text[1];
      simpleRisk = v.verdict === "risk";
    }
  }, 200);
}

// ---- status ----
function runningLabel(s) {
  // Which mode is running: find the preset with the same model and context length.
  if (!s.running || !catalog) return "";
  const names = { chat: "Chat", coding: "Coding", long: "Long context" };
  const hit = Object.entries(catalog.presets).find(([, p]) => p.model === s.model && s.opts && p.ctx === s.opts.ctx);
  const mode = hit ? (names[hit[0]] || hit[1].label) : "Custom settings";
  return `${mode}, ${s.model_label || s.model}`;
}

let lastSyncedRun = null;
function render(s) {
  status = s;
  $("runinfo").textContent = runningLabel(s);
  // The mode field in Settings shows the running mode whenever it changes.
  const runKey = s.running && catalog ? (Object.entries(catalog.presets).find(([, p]) => p.model === s.model && s.opts && p.ctx === s.opts.ctx) || [""])[0] : "";
  if (runKey !== lastSyncedRun) {
    lastSyncedRun = runKey;
    if (runKey) {
      $("preset").value = runKey;
      // Step 3 shows the same mode as the header, so a beginner never sees "Chat" while Coding runs.
      if (SIMPLE_PRESETS[runKey]) $("s-preset").value = runKey;
    }
  }
  setCls("dot", "dot " + (s.ready ? "ok-bg" : s.running ? "wait-bg" : "off-bg"));
  $("state").textContent = s.ready ? "assistant ready" : s.running ? "loading…" : "stopped";
  $("status").innerHTML = [
    ["Program", s.running ? catalog.engines[s.engine].label : "—"],
    ["Model", s.model_label || "—"],
    ["Process ID", fmt(s.pid)],
    ["Used by the program", fmt(s.rss_gib, " GiB")],
    ["Conversation length", s.opts ? Number(s.opts.ctx).toLocaleString("en-US") : "—"],
    ["Automatic restarts (10 min)", fmt(s.restarts_recent)],
    ["Port", catalog.port],
  ].map(([a, b]) => `<div class="row"><span>${esc(a)}</span><span>${esc(b)}</span></div>`).join("");
  $("loaderr").textContent = s.load_error ? "Loading error: " + friendly(s.load_error) : "";
  const m = s.memory;
  $("mem").innerHTML = [
    ["Free now", gib(m.free_gib)],
    ["Available including cache (free + inactive)", gib(m.free_gib + m.inactive_gib)],
    ["Active", gib(m.active_gib)],
    ["Inactive (system cache)", gib(m.inactive_gib)],
    ["Wired (system)", gib(m.wired_gib)],
    ["Compressed", gib(m.compressor_gib)],
    ["Swap (disk used as memory)", m.swap_used_gib == null ? "—" : `${m.swap_used_gib} of ${m.swap_total_gib} GiB`],
  ].map(([a, b]) => `<div class="row"><span>${esc(a)}</span><span>${esc(b)}</span></div>`).join("");
  $("memwarn").textContent = m.swap_used_gib > ((appSettings && appSettings.swap_warn_gb) || 12)
    ? "The disk is being used as memory, so work will be slower. Close other programs." : "";
  $("cache").innerHTML = `<div class="row"><span>Saved conversation starts</span><span>${gib(s.apc_disk_gib)}</span></div>`;
  setDis("start", s.running);
  setDis("stop", !s.running);
  setDis("send", !s.ready);
  setDis("cacheclear", s.running);
  renderSimple();
}

async function refresh() {
  try {
    const s = await api("/api/status");
    if (!catalog) fillCatalog(await api("/api/catalog"));
    render(s);
  } catch (e) {
    $("state").textContent = "panel unavailable";
  }
}

async function refreshLog() {
  const el = $("log");
  const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
  el.textContent = (await api("/api/log")).log;
  if (atEnd) el.scrollTop = el.scrollHeight;
}

async function refreshHistory() {
  const { events } = await api("/api/history");
  const names = {
    start: "Start", stop: "Stop", crash: "Crash", restart: "Automatic restart",
    gave_up: "Restarts exhausted", chat: "Question", cache_cleared: "Cache cleared", watchdog_error: "Watchdog error",
  };
  $("history").innerHTML = events.slice(0, 40).map((e) => {
    const extra = e.event === "chat" ? `, ${e.tok_s ?? "—"} tok/s` : (e.exit_code != null ? `, exit code ${e.exit_code}` : "");
    return `<div class="hist-row"><span class="t">${esc(e.ts.slice(5, 16).replace("T", " "))}</span> ${esc(names[e.event] || e.event)}${e.model ? " — " + esc(e.model) : ""}${esc(extra)}</div>`;
  }).join("") || '<p class="hint">No events yet.</p>';
}

// ---- actions: advanced view ----
async function startAdvanced() {
  if (settingsRisk && !confirm("This model may not fit in memory. Starting it can slow the Mac down a lot or fail. Start anyway?")) return;
  $("actmsg").textContent = "Starting…";
  const body = { model: $("model").value, ctx: +$("ctx").value };
  if ($("engine").value === "mlx") {
    body.prefill = +$("prefill").value;
    body.apc = $("apc").checked;
    body.apc_mem_gb = +$("apcmem").value;
  }
  const r = await api("/api/start", body);
  $("actmsg").textContent = r.ok ? "The assistant is starting. The model loads in 1–2 minutes." : friendly(r.error);
  refresh();
}

async function stopEngine() {
  const r = await api("/api/stop", {});
  $("actmsg").textContent = r.ok ? "Stopped." : "Could not stop. Check the log.";
  $("s-run-text").textContent = r.ok ? "The assistant is stopped." : "Could not stop. Check the program log.";
  refresh();
}

async function clearCache() {
  const r = await api("/api/cache/clear", {});
  $("actmsg").textContent = r.ok ? "Cache cleared." : friendly(r.error);
  refresh();
}

async function syncOpencode() {
  const r = await api("/api/opencode/sync", {});
  $("ocmsg").textContent = r.ok
    ? `opencode settings updated: ${r.models} models, context ${Number(r.context).toLocaleString("en-US")}. A backup was created.`
    : r.error;
}

// ---- downloads and installs ----
async function startModelDownload(key) {
  const info = catalog.models[key];
  if (!info) return;
  const size = (info.simple || {}).size || "";
  if (!confirm(`Download "${info.label}"${size ? " (" + size + ")" : ""}? It can take 10 to 40 minutes. You can close this window; the download continues.`)) return;
  const r = await api("/api/download", { model: key });
  if (!r.ok) { $("s-model-text").textContent = friendly(r.error); $("dlstate").textContent = friendly(r.error); return; }
  $("dlstate").textContent = "Downloading…";
  $("s-model-cancel").hidden = false;
  pollDownload(key);
}

function pollDownload(key) {
  clearInterval(dlTimer);
  dlTimer = setInterval(async () => {
    const d = await api(`/api/download/${encodeURIComponent(key)}`);
    const pct = d.percent == null ? "" : ` ${d.percent}%`;
    $("s-model-cancel").hidden = d.state !== "running";
    if (d.state === "cancelled") {
      clearInterval(dlTimer);
      $("s-model-text").textContent = "Download cancelled. The files so far are kept; the next download continues from there.";
      $("dlstate").textContent = "";
    } else if (d.state === "running") {
      $("dlstate").textContent = "Downloading…" + pct;
      $("s-model-text").textContent = "Downloading…" + pct + ". You can do other things meanwhile.";
    } else if (d.state === "done") {
      clearInterval(dlTimer);
      $("dlstate").textContent = "Done. The model is on disk.";
      $("s-model-text").textContent = "The model is downloaded.";
      catalog = await api("/api/catalog");
      refresh();
    } else if (d.state === "error") {
      clearInterval(dlTimer);
      $("s-model-text").textContent = d.error || "The download was interrupted. Click “Download model” again.";
      $("dlstate").textContent = "";
    }
  }, 2000);
}

async function installEngineForSimple() {
  const key = catalog.models[$("s-model").value].engine;
  const label = catalog.engines[key].label;
  if (!confirm(`Install "${label}"? It takes about 2 GB and 3–5 minutes. You can close this window; the install continues.`)) return;
  const r = await api("/api/components/install", { id: `engine:${key}` });
  if (!r.ok) { $("s-engine-text").textContent = friendly(r.error); return; }
  watchJob(r.job, label);
  loadComponents();
}

// ---- start and chat in the simple view ----
let transient = { text: "", until: 0 };
function say(text, ms = 8000) { transient = { text, until: Date.now() + ms }; }

async function startSimple() {
  const model = $("s-model").value;
  const preset = $("s-preset").value;
  if (simpleRisk && !confirm("This model may not fit in memory. Starting it can slow the Mac down a lot or fail. Start anyway?")) return;
  say("Starting…");
  const r = await api("/api/start", { model, preset });
  say(r.ok ? "The assistant is starting. This takes about a minute." : friendly(r.error), 10000);
  renderSimple();
  refresh();
}

function renderSimple() {
  if (!catalog) return;
  const model = $("s-model").value;
  const info = catalog.models[model];
  const engineKey = info ? info.engine : "mlx";
  const engItem = comps.find((c) => c.id === `engine:${engineKey}`) || {};
  const modelItem = comps.find((c) => c.id === `model:${model}`) || {};
  const engineOk = !!engItem.installed;
  const modelOk = !!(info && info.exists);
  const engJob = engItem.job && engItem.job.state === "running";
  const dl = modelItem.download;
  const running = !!(status && status.running);
  const isThis = running && status.model === model;

  // step 1
  const loaded = comps.length > 0;  // do not claim nothing is installed before the first answer
  $("st-engine").classList.toggle("done", engineOk);
  $("s-engine-text").innerHTML = !loaded ? "Checking…" : engineOk
    ? '<span class="good">Installed</span>'
    : (engJob ? "Installing, please wait a few minutes…" : "Not installed. Click “Install”.");
  setDis("s-engine-btn", !loaded || engineOk || engJob);
  setDis("s-model-btn", !loaded || modelOk || !!dl || !(info && info.can_download));

  // step 2
  $("st-model").classList.toggle("done", modelOk);
  const sm = (catalog.models[model] || {}).simple || {};
  $("s-model-info").textContent = info ? `${sm.size || ""}. ${sm.about || ""}` : "";
  if (modelOk) {
    $("s-model-text").innerHTML = '<span class="good">Model downloaded</span>';
  } else if (dl) {
    $("s-model-text").textContent = "Downloading…" + (dl.percent == null ? "" : " " + dl.percent + "%");
  } else {
    $("s-model-text").textContent = info && !info.can_download ? "This model must be placed on disk by hand." : "";
  }
  $("s-model-btn").textContent = modelOk ? "Downloaded" : "Download model";

  // step 3
  const ready1 = engineOk && modelOk;
  $("st-run").classList.toggle("done", isThis && status.ready);
  $("st-run").classList.toggle("locked", !ready1);
  setDis("s-start", !ready1 || running);
  setDis("s-stop", !running);
  if (transient.until > Date.now()) {
    $("s-run-text").textContent = transient.text;
  } else if (isThis && status.ready) {
    $("s-run-text").innerHTML = '<span class="good">The assistant is running. Type your question below.</span>';
  } else if (isThis) {
    $("s-run-text").textContent = "Loading, this takes about a minute…" + (status.load_error ? " " + friendly(status.load_error) : "");
  } else if (running) {
    $("s-run-text").textContent = "Another model is running. Stop it to start this one.";
  } else if (!ready1) {
    $("s-run-text").textContent = "Complete steps 1 and 2 first.";
  } else {
    $("s-run-text").textContent = "The assistant is stopped. Click “Start” when you are ready.";
  }

  // step 4
  $("st-chat").classList.toggle("locked", !(isThis && status.ready));
  setDis("s-send", !(isThis && status.ready));

  // single indicator: show one current action
  const ld = $("s-loader");
  let label = null, pct = null, indet = false;
  if (engJob) { label = "Installing the model program"; indet = true; }
  else if (dl) { label = "Downloading the model"; pct = dl.percent; }
  else if (running && !isThis) { label = "Another assistant is running"; }
  else if (isThis && !status.ready) { label = "Loading the model into memory, about a minute"; indet = true; }
  else if (chatBusy) { label = "Thinking about the answer"; indet = true; }
  const vis = label ? "visible" : "hidden";
  if (ld.style.visibility !== vis) ld.style.visibility = vis;
  if (ld.classList.contains("indet") !== indet) ld.classList.toggle("indet", indet);
  ld.querySelector(".ld-label").textContent = label || "";
  ld.querySelector(".ld-pct").textContent = pct != null ? Math.round(pct) + "%" : "";
  const fill = ld.querySelector(".ld-fill");
  const tf = indet ? "" : `scaleX(${(pct || 0) / 100})`;
  if (fill.style.transform !== tf) fill.style.transform = tf;

  // one primary button on screen: the one needed now
  const primary = (id, on) => setPrimary(id, on);
  primary("s-engine-btn", loaded && !engineOk && !engJob);
  primary("s-model-btn", loaded && engineOk && !modelOk && !dl);
  primary("s-start", ready1 && !running);
  primary("s-send", isThis && status.ready && !chatBusy);
}

let chatBusy = false;

function renderAnswer(text) {
  // Code blocks go into a box; the rest gets simple formatting (headings, bold, lists). Everything is escaped.
  const parts = String(text).split("```");
  return parts.map((part, i) => {
    if (i % 2 === 1) {
      const body = part.replace(/^[a-zA-Z0-9+#.-]*\n/, "");  // drop the language name on the first line
      return `<pre class="code"><code>${esc(body.replace(/\n$/, ""))}</code></pre>`;
    }
    return renderPlain(part);
  }).join("");
}

function renderPlain(text) {
  const lines = esc(text).split("\n").map((line) => {
    let l = line.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    const h = l.match(/^#{1,6}\s+(.*)$/);
    if (h) return `<h4>${h[1].replace(/\*\*/g, "")}</h4>`;
    const li = l.match(/^\s*[-*]\s+(.*)$/);
    if (li) return `<li>• ${li[1]}</li>`;
    return l.trim() ? `<p>${l}</p>` : "";
  });
  return lines.join("");
}

let lastAnswer = "";

async function sendChat(prompt, maxTokens, answerEl, statEl, mode) {
  statEl.textContent = "Thinking… An answer usually takes 2–30 seconds.";
  chatBusy = true;
  renderSimple();
  answerEl.innerHTML = "";
  const copyRow = $("s-copy-row");
  if (copyRow) $("s-copy").disabled = true;
  const r = await api("/api/chat", { prompt, max_tokens: maxTokens, mode: mode || null });
  chatBusy = false;
  if (r.ok) {
    lastAnswer = r.answer;
    answerEl.innerHTML = renderAnswer(r.answer);
    statEl.textContent = `Answered in ${r.seconds} s.`;
    if (copyRow) $("s-copy").disabled = false;
  } else {
    statEl.textContent = friendly(r.error);
  }
  refresh();
  refreshHistory();
}

// ---- components section ----
async function loadComponents() {
  loadFolders();
  const { items } = await api("/api/components");
  comps = items;
  $("comp-engines").innerHTML = items.filter((c) => c.kind === "engine").map(compRow).join("");
  $("comp-models").innerHTML = items.filter((c) => c.kind === "model").map(compRow).join("");
  document.querySelectorAll("#view-components button[data-act]").forEach((b) => {
    b.onclick = () => componentAction(b.dataset.act, b.dataset.id, b.dataset.label);
  });
  if (!catalog) refresh(); else renderSimple();  // the steps wait for the catalog: do not wait for the next refresh
  const running = items.find((c) => c.job && c.job.state === "running");
  if (running && (!jobWatch || jobWatch.id !== running.job.id)) watchJob(running.job.id, running.label);
  renderSimple();
}

function compRow(c) {
  const badge = c.installed ? '<span class="badge on">installed</span>' : '<span class="badge off">not installed</span>';
  const size = c.size_gib == null ? "—" : c.size_gib.toFixed(2) + " GiB";
  let extra = "";
  if (c.download) extra = c.download.percent == null ? "downloading…" : `downloading ${c.download.percent}%`;
  else if (c.job && c.job.state === "running") extra = c.job.action === "install" ? "installing…" : "removing…";
  else if (c.job && c.job.state === "error") extra = "error: " + friendly(c.job.error || "");
  const busy = !!(c.download || (c.job && c.job.state === "running"));
  const install = c.can_install ? `<button class="primary" data-act="install" data-id="${esc(c.id)}" data-label="${esc(c.label)}" ${busy ? "disabled" : ""}>Install</button>` : "";
  const remove = c.can_uninstall ? `<button data-act="uninstall" data-id="${esc(c.id)}" data-label="${esc(c.label)}" ${busy ? "disabled" : ""}>Remove</button>` : "";
  return `<div class="comp">
    <div><div class="name">${esc(c.label)}</div><div class="sub">${esc(c.note)}${extra ? ", " + esc(extra) : ""}</div></div>
    <div class="size">${esc(size)}</div>
    <div>${badge}</div>
    <div class="btns">${install}${remove}</div>
  </div>`;
}

async function componentAction(act, id, label) {
  if (act === "uninstall") {
    if (!confirm(`Remove "${label}"? Its files will be deleted. You can install it again later.`)) return;
    const r = await api("/api/components/uninstall", { id });
    if (!r.ok) { alert(friendly(r.error)); return; }
    watchJob(r.job, label);
  } else {
    const r = await api("/api/components/install", { id });
    if (!r.ok) { alert(friendly(r.error)); return; }
    if (r.job) watchJob(r.job, label);
    else { alert("The model download has started. Progress is shown in its row."); }
  }
  loadComponents();
}

// Cancel buttons: the model download (Simple view) and the running install or uninstall (Programs and models).
$("s-model-cancel").onclick = async () => {
  await api(`/api/download/${encodeURIComponent($("s-model").value)}/cancel`, {});
};
$("job-cancel").onclick = async () => {
  if (jobWatch) await api(`/api/jobs/${encodeURIComponent(jobWatch.id)}/cancel`, {});
};

function watchJob(jobId, label) {
  $("job-panel").hidden = false;
  $("job-title").textContent = label || "";
  clearInterval(jobWatch && jobWatch.timer);
  jobWatch = { id: jobId };
  const tick = async () => {
    const j = await api("/api/jobs/" + encodeURIComponent(jobId));
    if (!j || j.detail) return;
    const el = $("job-log");
    const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
    el.textContent = j.log;
    if (atEnd) el.scrollTop = el.scrollHeight;
    $("job-cancel").hidden = j.state !== "running";
    if (j.state !== "running") {
      clearInterval(jobWatch.timer);
      jobWatch = null;
      loadComponents();
      refresh();
    }
  };
  jobWatch.timer = setInterval(tick, 2000);
  tick();
}

// ---- general settings ----
let appSettings = null;
async function loadSettings() {
  appSettings = await api("/api/settings");
  try { localStorage.setItem("start_view", appSettings.start_view); } catch (e) {}  // read by index.html before paint
  $("st-autostart").checked = !!appSettings.autostart;
  $("st-view").value = appSettings.start_view;
  $("st-dir").value = appSettings.download_dir || "";
  $("st-dir-hint").textContent = `Models are currently stored in: ${appSettings.hf_cache_root}`;
  $("st-token").value = appSettings.hf_token ? "••••" : "";
  $("st-swap").value = appSettings.swap_warn_gb;
}

$("st-save").onclick = async () => {
  const body = {
    autostart: $("st-autostart").checked,
    start_view: $("st-view").value,
    download_dir: $("st-dir").value.trim(),
    hf_token: $("st-token").value,
    swap_warn_gb: +$("st-swap").value,
  };
  const r = await api("/api/settings", body);
  if (!r.ok) { $("st-msg").textContent = r.error; return; }
  $("st-msg").textContent = "Saved." + (body.autostart !== !!appSettings.autostart ? " The autostart change takes effect after the panel restarts." : "");
  await loadSettings();
  refresh();
};

// ---- model folders ----
async function loadFolders() {
  const d = await api("/api/model-dirs");
  $("folder-list").innerHTML = d.dirs.length
    ? d.dirs.map((p) => `<div class="comp" style="grid-template-columns:minmax(0,1fr) auto"><div class="name" style="font-size:15px;word-break:break-all">${esc(p)}</div><div class="btns"><button data-rm="${esc(p)}" class="small">Remove</button></div></div>`).join("")
    : '<p class="hint">No folders yet.</p>';
  $("folder-found").innerHTML = d.found.length
    ? d.found.map((m) => `<div class="comp" style="grid-template-columns:minmax(0,1fr) auto"><div><div class="name">${esc(m.label)}</div><div class="sub">${esc(m.path)}</div></div><div><span class="badge on">ready</span></div></div>`).join("")
    : '<p class="hint">Nothing found. Make sure the folder contains a model (a folder with config.json and .safetensors files, or .gguf files).</p>';
  document.querySelectorAll("#folder-list button[data-rm]").forEach((b) => {
    b.onclick = async () => {
      const r = await api("/api/model-dirs/remove", { path: b.dataset.rm });
      $("folder-msg").textContent = "Folder removed from the list. Models found: " + r.found + ".";
      catalog = await api("/api/catalog");
      rebuildSimpleModels();
      loadFolders(); loadComponents(); refresh();
    };
  });
}

$("folder-add").onclick = async () => {
  const path = $("folder-path").value.trim();
  if (!path) { $("folder-msg").textContent = "Paste the path to the folder."; return; }
  const r = await api("/api/model-dirs/add", { path });
  if (!r.ok) { $("folder-msg").textContent = r.error; return; }
  $("folder-msg").textContent = r.found ? `Models found: ${r.found}.` : "Folder added, but it contains no models.";
  $("folder-path").value = "";
  catalog = await api("/api/catalog");
  rebuildSimpleModels();
  loadFolders(); loadComponents(); refresh();
};

// ---- tabs ----
function route() {
  const h = location.hash || ("#" + ((appSettings && appSettings.start_view) || "simple"));
  const view = { "#panel": "panel", "#components": "components" }[h] || "simple";
  document.documentElement.dataset.view = view;  // keeps the pre-paint rule in index.html in sync
  $("view-simple").hidden = view !== "simple";
  $("view-panel").hidden = view !== "panel";
  $("view-components").hidden = view !== "components";
  $("tab-simple").classList.toggle("on", view === "simple");
  $("tab-panel").classList.toggle("on", view === "panel");
  $("tab-components").classList.toggle("on", view === "components");
  if (view === "components") { loadComponents(); loadUserModels(); }
}
window.addEventListener("hashchange", route);

// ---- theme: light, dark or follow the system ----
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  try { localStorage.setItem("theme", t || ""); } catch (e) {}
}
$("theme").onclick = () => {
  const cur = document.documentElement.dataset.theme || "";
  applyTheme(cur === "" ? "dark" : cur === "dark" ? "light" : "");
};
try { applyTheme(localStorage.getItem("theme") || ""); } catch (e) {}

// ---- models added from Hugging Face ----
async function loadUserModels() {
  const { models } = await api("/api/models/user");
  const box = $("user-models");
  box.innerHTML = "";
  if (!models.length) {
    const none = document.createElement("p");
    none.className = "hint";
    none.textContent = "No models added yet.";
    box.append(none);
    return;
  }
  for (const m of models) {
    const row = document.createElement("div");
    row.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:var(--s-4);padding:var(--s-2) 0;border-bottom:1px solid var(--hair)";
    const text = document.createElement("div");
    const name = document.createElement("div");
    name.textContent = m.label;
    const repo = document.createElement("div");
    repo.className = "hint";
    repo.textContent = `${m.repo} · ${m.engine}`;
    text.append(name, repo);
    const btn = document.createElement("button");
    btn.className = "small";
    btn.textContent = "Remove from list";
    btn.onclick = async () => {
      const r = await api("/api/models/remove", { key: m.key });
      if (!r.ok) { $("hf-msg").textContent = r.error; return; }
      catalog = await api("/api/catalog");
      loadComponents(); loadUserModels();
    };
    row.append(text, btn);
    box.append(row);
  }
}

$("hf-add").onclick = async () => {
  const repo = $("hf-repo").value.trim();
  if (!repo) return;
  $("hf-msg").textContent = "Checking the repository on Hugging Face…";
  const r = await api("/api/models/add", { repo });
  if (!r.ok) { $("hf-msg").textContent = r.error; return; }
  $("hf-msg").textContent = `Added ${r.label} (${r.engine}, about ${r.size_gib} GiB). Press Install in the list above to download it.`;
  $("hf-repo").value = "";
  catalog = await api("/api/catalog");
  loadComponents(); loadUserModels();
};

// ---- recommended model for this Mac ----
let recommendedKey = null;
async function refreshRecommend() {
  const purpose = $("s-purpose").value;
  const r = await api(`/api/recommend?purpose=${encodeURIComponent(purpose)}`);
  recommendedKey = r.ok ? r.key : null;
  $("s-recommend").textContent = r.ok ? `Recommended: ${r.label}. ${r.reason}` : (r.message || "No recommendation.");
  $("s-recommend-btn").hidden = !r.ok || r.key === $("s-model").value;
}

// ---- start ----
loadSettings().then(() => route());
refresh();
loadComponents();
refreshLog();
refreshHistory();
setInterval(refresh, 4000);
// Step 1 of the Simple view needs the component list too, so it is loaded on start and kept fresh on every view.
loadComponents();
setInterval(loadComponents, 6000);
setInterval(refreshLog, 4000);
setInterval(refreshHistory, 8000);
