// The panel's logic layer: everything the old app.js did with shared state.
// Module-level variables became Svelte stores; DOM writes became store
// updates. The views read these and bind their fields to them.
import { writable, get } from 'svelte/store';
import {
  friendly, getStatus, getCatalog, getLog, getHistory, getComponents,
  getSettings, getModelDirs, getUserModels, getDownloadState, getJob, getRecommend,
  getContextAdvice, getPreflight, startEngine, stopEngine, clearCache, syncOpencode,
  sendChat, saveSettings, startDownload, cancelDownload, installComponent, uninstallComponent,
  addModelDir, removeModelDir, addUserModel, removeUserModel,
} from '../api.js';
import { gib, fmt } from './markup.js';
import { toast } from './toastBridge.js';
import { confirmBox } from './confirm.js';

// Labels for the simple view. Keys come from config/registry.json.
export const SIMPLE_PRESETS = {
  chat: 'Chat — for conversations and questions (quick start)',
  coding: 'Coding — for code (remembers more text)',
};

// ---- shared data ----
export const catalog = writable(null);
export const status = writable(null);
export const comps = writable([]);
export const appSettings = writable(null);
export const logText = writable('');
export const historyEvents = writable([]);
export const statusError = writable(false); // "panel unavailable"

// memory verdicts of the two launch views; the last verdict being "risk" makes
// Start ask first.
export const verdictAdv = writable({ verdict: '', message: 'Checking memory…' });
export const verdictSimple = writable({ verdict: '', message: 'Checking whether there is enough memory…' });
export const simpleRisk = writable(false);

// fields of the Settings launch panel (the old #launch selects and options)
export const adv = writable({
  preset: '', engine: '', model: '', ctx: '', prefill: '',
  apc: true, apcmem: 6, kvbits: '4',
});
export const ctxAdviced = writable(false); // context advice keeps the short cache limit until the user handled it

// fields of the Simple view (the old #s-* controls)
export const simp = writable({ purpose: 'agent', model: '', preset: 'chat', mode: '' });
export const simpleModes = writable([]); // sampling modes of the selected model

// messages that several actions write through
export const actMsg = writable('');                 // Settings launch: what the last action did
export const dlStateMsg = writable('');             // Settings: state of the model download
export const simpleModelMsg = writable('');         // Simple step 2 text (downloads and errors)
export const simpleEngineMsg = writable('');        // Simple step 1 text
export const ocMsg = writable('');                  // opencode sync result
export const hfMsg = writable('');                  // add-a-model result
export const folderMsg = writable('');              // model folders result
export const settingsMsg = writable('');            // settings save result
export const chatBusy = writable(false);
export const lastAnswer = writable('');
export const cancelVisible = writable(false);       // Cancel download button in Simple
export const recommendedKey = writable(null);
export const recommendText = writable('');
export const recommendButton = writable(false);
export const jobPanel = writable(null);             // { id, label, log, running } while a job is watched
export const folders = writable({ dirs: [], found: [] });
export const userModels = writable([]);

// ---- option builders (the old fillModels / fillCtx / fillPrefill / fillModes) ----
export const modelsForEngine = (c, engineKey) => {
  if (!c) return [];
  return Object.entries(c.models)
    .filter(([, info]) => info.engine === engineKey)
    .map(([k, info]) => ({ value: k, label: info.label + (info.exists ? '' : ' (not downloaded)') }));
};

export const engineOptions = (c) => {
  if (!c) return [];
  return Object.entries(c.engines)
    .map(([k, e]) => ({ value: k, label: e.label + (e.binary_ok ? '' : ' (not installed)') }));
};

// The modes the old panel offered: the presets only. With nothing running, the first one is selected.
export const presetOptions = (c) => (c ? Object.entries(c.presets).map(([k, p]) => ({ value: k, label: p.label })) : []);

export const simpleModelOptions = (c) => {
  if (!c) return [];
  return Object.entries(c.models)
    .filter(([, info]) => info.simple || info.exists)
    .map(([k, info]) => ({ value: k, label: info.label }));
};

export const purposeOptions = Object.entries({
  agent: 'Agentic coding (uses tools)',
  chat: 'Chat',
  quick: 'Quick answers',
}).map(([value, label]) => ({ value, label }));

// Sampling modes of the selected model; hidden when the model has none.
export function refreshSimpleModes(resetToDefault) {
  const c = get(catalog);
  const s = get(simp);
  const info = c && c.models[s.model];
  const modes = (info && info.modes) || [];
  const keep = s.mode;
  simpleModes.set(modes.map((m) => ({ value: m.key, label: m.label })));
  const keepable = !resetToDefault && modes.some((m) => m.key === keep);
  simp.update((v) => ({
    ...v,
    mode: keepable && keep ? keep : ((info && info.default_mode) || (modes[0] ? modes[0].key : '')),
  }));
}

// ---- catalog ----
function initFromCatalog(c) {
  const d = c.default || {};
  const engineKey = (c.models[d.model] || {}).engine || Object.keys(c.engines)[0];
  const engineModels = modelsForEngine(c, engineKey);
  const e = c.engines[engineKey];
  adv.update((v) => ({
    ...v,
    preset: '',
    engine: engineKey,
    // A <select> shows its first option when the wanted value is not in the list.
    model: engineModels.some((o) => o.value === d.model) ? d.model : (engineModels[0] ? engineModels[0].value : ''),
    ctx: (e.ctx_choices || []).includes(d.ctx) ? String(d.ctx) : (e.ctx_choices && e.ctx_choices.length ? String(e.ctx_choices[0]) : ''),
    prefill: (e.prefill_choices || []).includes(d.prefill) ? String(d.prefill) : (e.prefill_choices && e.prefill_choices.length ? String(e.prefill_choices[0]) : ''),
    apc: d.apc !== false,
    apcmem: d.apc_mem_gb || 6,
  }));
  // Simple view: keep the saved model when the list offers it, else the first one.
  const opts = simpleModelOptions(c);
  const keep = opts.some((o) => o.value === d.model) ? d.model : (opts[0] ? opts[0].value : '');
  simp.update((v) => ({ ...v, model: keep, preset: 'chat' }));
  refreshSimpleModes();
  refreshPreflight();
  refreshCtxAdvice();
}

let catalogStarted = false;
export async function ensureCatalog() {
  if (catalogStarted) return;
  catalogStarted = true;
  try {
    const c = await getCatalog();
    catalog.set(c);
    initFromCatalog(c);
  } catch (e) {
    catalogStarted = false;
  }
}

// ---- context advice ----
// The KV compression choice changes the memory estimate, so the checks send it
// too (MLX only).
export function kvQuery() {
  const a = get(adv);
  return a.kvbits && a.engine === 'mlx' ? `&kv_bits=${a.kvbits}` : '';
}

// Context advice from this Mac's total memory. Until the user picks a context,
// the field follows the advice.
export async function refreshCtxAdvice() {
  const a = get(adv);
  const key = a.model;
  if (!key || a.engine !== 'mlx') { ctxAdviced.set(''); return; }
  const c = get(catalog);
  if (!c || !c.models[key]) return;
  const result = await getContextAdvice(key, kvQuery());
  const text = !result || !result.ok ? (result && result.message) || ''
    : `${result.message} Reading step ${result.prefill}, prefix cache ${result.apc_mem_gb} GB.`;
  ctxAdviced.set(text);
  if (!a.ctxTouched && result && result.ok && result.ctx) {
    adv.update((v) => ({ ...v, ctx: String(result.ctx) }));
    refreshPreflight();
  }
}

// ---- memory check ----
let preflightTimer = null;
export function refreshPreflight() {
  clearTimeout(preflightTimer);
  preflightTimer = setTimeout(doPreflight, 200);
}

async function doPreflight() {
  const c = get(catalog);
  const a = get(adv);
  if (a.model && a.ctx) {
    const v = await getPreflight(`model=${encodeURIComponent(a.model)}&ctx=${a.ctx}${kvQuery()}`);
    verdictAdv.set({
      verdict: v.verdict || '',
      message: v.verdict === 'unknown' ? (v.message || 'Memory check is not available') : v.message,
    });
  }
  const s = get(simp);
  const ctxSimple = c && c.presets[s.preset] ? c.presets[s.preset].ctx : 32768;
  if (s.model) {
    const v = await getPreflight(`model=${encodeURIComponent(s.model)}&ctx=${ctxSimple}`);
    const text = {
      ok: { tone: 'success', message: 'There is enough memory.' },
      tight: { tone: 'warning', message: 'Memory is tight. Close large apps such as browsers with many tabs or video editors.' },
      risk: { tone: 'danger', message: 'There may not be enough memory. Choose the Chat mode or close other apps.' },
    }[v.verdict] || { tone: 'neutral', message: 'Memory check is not available.' };
    verdictSimple.set({ verdict: v.verdict || '', message: text.message, tone: text.tone });
    simpleRisk.set(v.verdict === 'risk');
  }
}

// ---- field handlers of the Settings launch panel ----
export function setAdvEngine(key) {
  // fillModels() + fillCtx(): a fresh option list makes the selects fall back
  // to their first choice, so the model, context and prefill follow.
  const c = get(catalog);
  const e = c.engines[key];
  const models = modelsForEngine(c, key);
  const first = (list) => String(list && list.length ? list[0] : '');
  adv.update((v) => {
    const keepModel = models.some((o) => o.value === v.model) ? v.model : (models[0] ? models[0].value : '');
    const keepCtx = (e.ctx_choices || []).includes(Number(v.ctx)) && String(v.ctx) !== '' ? v.ctx : first(e.ctx_choices);
    const keepPrefill = (e.prefill_choices || []).includes(Number(v.prefill)) && String(v.prefill) !== '' ? v.prefill : first(e.prefill_choices);
    return { ...v, engine: key, model: keepModel, ctx: keepCtx, prefill: keepPrefill };
  });
  refreshPreflight();
  refreshCtxAdvice();
}

export function setAdvModel(key) {
  // ctxTouched = false: until the user picks a context, the field follows the advice.
  adv.update((v) => ({ ...v, model: key, ctxTouched: false }));
  refreshCtxAdvice();
  refreshPreflight();
}

export function setAdvCtx(value) {
  adv.update((v) => ({ ...v, ctx: value, ctxTouched: true }));
  refreshPreflight();
}

export function patchAdv(patch, recheck = true) {
  adv.update((v) => ({ ...v, ...patch }));
  if (recheck) refreshPreflight();
}

export function applyPreset(key) {
  const c = get(catalog);
  const p = c && c.presets[key];
  if (!p) { adv.update((v) => ({ ...v, preset: key })); return; }
  adv.update((v) => {
    const e = c.engines[p.engine];
    const first = (list) => String(list && list.length ? list[0] : '');
    return {
      ...v,
      preset: key,
      engine: p.engine,
      model: modelsForEngine(c, p.engine).some((o) => o.value === p.model)
        ? p.model
        : (modelsForEngine(c, p.engine)[0] ? modelsForEngine(c, p.engine)[0].value : ''),
      ctx: (e.ctx_choices || []).includes(p.ctx) ? String(p.ctx) : first(e.ctx_choices),
      prefill: (e.prefill_choices || []).includes(p.prefill) ? String(p.prefill) : first(e.prefill_choices),
      apc: p.apc !== false,
      apcmem: p.apc_mem_gb || v.apcmem,
      ctxTouched: v.ctxTouched,
    };
  });
  refreshCtxAdvice();
  refreshPreflight();
}

// ---- field handlers of the Simple view ----
export function setSimpleModel(key) {
  simp.update((v) => ({ ...v, model: key }));
  refreshSimpleModes(true); // onchange with reset: modes fall back to the model's default
  refreshPreflight();
  cancelVisible.set(false);
}

export function setSimplePreset(key) {
  simp.update((v) => ({ ...v, preset: key }));
  refreshPreflight();
}

export function setSimpleMode(key) { simp.update((v) => ({ ...v, mode: key })); }
export function setSimplePurpose(purpose) { refreshRecommend(purpose); }

// ---- the recommended model for this Mac ----
export async function refreshRecommend(purpose) {
  const r = await getRecommend(purpose);
  recommendedKey.set(r.ok ? r.key : null);
  recommendText.set(r.ok ? `Recommended: ${r.label}. ${r.reason}` : (r.message || 'No recommendation.'));
  const simpV = get(simp);
  recommendButton.set(!!r.ok && r.key !== simpV.model);
}

export function useRecommendedModel() {
  const key = get(recommendedKey);
  if (!key) return;
  setSimpleModel(key);
}

// ---- downloads ----
export async function startModelDownload(key) {
  const c = get(catalog);
  const info = c.models[key];
  if (!info) return;
  const size = (info.simple || {}).size || '';
  const yes = await confirmBox(`Download "${info.label}"${size ? ' (' + size + ')' : ''}? It can take 10 to 40 minutes. You can close this window; the download continues.`);
  if (!yes) return;
  const r = await startDownload(key);
  if (!r.ok) { flashMsg(simpleModelMsg, friendly(r.error)); dlStateMsg.set(friendly(r.error)); return; }
  dlStateMsg.set('Downloading…');
  cancelVisible.set(true);
  pollDownload(key);
}

export async function cancelModelDownload() {
  const key = get(simp).model;
  await cancelDownload(key);
}

function pollDownload(key) {
  const timer = setInterval(async () => {
    const d = await getDownloadState(key);
    const pct = d.percent == null ? '' : ` ${d.percent}%`;
    cancelVisible.set(d.state === 'running');
    if (d.state === 'cancelled') {
      clearInterval(timer);
      simpleModelMsg.set('Download cancelled. The files so far are kept; the next download continues from there.');
      dlStateMsg.set('');
    } else if (d.state === 'running') {
      dlStateMsg.set('Downloading…' + pct);
      simpleModelMsg.set('Downloading…' + pct + '. You can do other things meanwhile.');
    } else if (d.state === 'done') {
      clearInterval(timer);
      dlStateMsg.set('Done. The model is on disk.');
      simpleModelMsg.set('The model is downloaded.');
      catalog.set(await getCatalog());
      refreshStatus();
    } else if (d.state === 'error') {
      clearInterval(timer);
      simpleModelMsg.set(d.error || 'The download was interrupted. Click “Download model” again.');
      dlStateMsg.set('');
    }
  }, 2000);
  return timer;
}

// ---- install the engine from the Simple view ----
export async function installEngineForSimple() {
  const c = get(catalog);
  const s = get(simp);
  const key = c.models[s.model].engine;
  const label = c.engines[key].label;
  const yes = await confirmBox(`Install "${label}"? It takes about 2 GB and 3–5 minutes. You can close this window; the install continues.`);
  if (!yes) return;
  const r = await installComponent(`engine:${key}`);
  if (!r.ok) { flashMsg(simpleEngineMsg, friendly(r.error)); return; }
  watchJob(r.job, label);
  loadComponents();
}

// ---- start and stop ----
export async function startAdvanced() {
  const a = get(adv);
  if (get(verdictAdv).verdict === 'risk') {
    const yes = await confirmBox('This model may not fit in memory. Starting it can slow the Mac down a lot or fail. Start anyway?');
    if (!yes) return;
  }
  actMsg.set('Starting…');
  const body = { model: a.model, ctx: +a.ctx };
  if (a.engine === 'mlx') {
    body.prefill = +a.prefill;
    body.apc = a.apc;
    body.apc_mem_gb = +a.apcmem;
    if (a.kvbits) body.kv_bits = +a.kvbits;
  }
  const r = await startEngine(body);
  actMsg.set(r.ok ? 'The assistant is starting. The model loads in 1–2 minutes.' : friendly(r.error));
  refreshStatus();
}

export async function startSimple() {
  const s = get(simp);
  if (get(simpleRisk)) {
    const yes = await confirmBox('This model may not fit in memory. Starting it can slow the Mac down a lot or fail. Start anyway?');
    if (!yes) return;
  }
  say('Starting…');
  const r = await startEngine({ model: s.model, preset: s.preset });
  say(r.ok ? 'The assistant is starting. This takes about a minute.' : friendly(r.error), 10000);
  refreshStatus();
}

export async function stopEngineAction() {
  const r = await stopEngine();
  actMsg.set(r.ok ? 'Stopped.' : 'Could not stop. Check the log.');
  say(r.ok ? 'The assistant is stopped.' : 'Could not stop. Check the program log.');
  refreshStatus();
}

export async function clearCacheAction() {
  const r = await clearCache();
  actMsg.set(r.ok ? 'Cache cleared.' : friendly(r.error));
  refreshStatus();
}

export async function syncOpencodeAction() {
  const a = get(adv);
  const r = await syncOpencode({ ctx: Number(a.ctx) || undefined });
  ocMsg.set(r.ok
    ? `opencode settings updated: ${r.models} models, context ${Number(r.context).toLocaleString('en-US')}. A backup was created.` + (r.note ? ' ' + r.note : '')
    : r.error);
}

// ---- chat (both views) ----
// Transient message in step 3: shown for a moment, then the state takes over.
export const runTransient = writable({ text: '', until: 0 });
let transientTimer = null;
function say(text, ms = 8000) {
  runTransient.set({ text, until: Date.now() + ms });
  clearTimeout(transientTimer);
  transientTimer = setTimeout(() => runTransient.set({ text: '', until: 0 }), ms);
}

// A message that the next state render would overwrite in the old panel; here
// it clears itself after a short moment.
function flashMsg(store, text, ms = 8000) {
  store.set(text);
  clearTimeout(store.__timer);
  store.__timer = setTimeout(() => store.set(''), ms);
}

// The chat request itself; the views render whatever comes back.
export async function sendChatAction(prompt, maxTokens, mode) {
  chatBusy.set(true);
  const r = await sendChat({ prompt, max_tokens: maxTokens, mode: mode || null });
  chatBusy.set(false);
  if (r.ok) lastAnswer.set(r.answer);
  refreshStatus();
  refreshHistory();
  return r;
}

export async function copyAnswer() {
  try {
    await navigator.clipboard.writeText(get(lastAnswer));
    simpleChatStat.set('Answer copied. Paste it into Word or Pages.');
  } catch (e) {
    simpleChatStat.set('Could not copy. Select the answer with the mouse and press Command+C.');
  }
}

export const simpleChatStat = writable('');

// ---- status, log, history ----
export function runningLabel(s) {
  // Which mode is running: find the preset with the same model and context length.
  const c = get(catalog);
  if (!s.running || !c) return '';
  const names = { chat: 'Chat', coding: 'Coding', long: 'Long context' };
  const hit = Object.entries(c.presets).find(([, p]) => p.model === s.model && s.opts && p.ctx === s.opts.ctx);
  const mode = hit ? (names[hit[0]] || hit[1].label) : 'Custom settings';
  return `${mode}, ${s.model_label || s.model}`;
}

let lastSyncedRun = null;
function syncRunningMode(s) {
  // The mode field shows the running mode whenever it changes.
  const c = get(catalog);
  const runKey = s.running && c ? (Object.entries(c.presets).find(([, p]) => p.model === s.model && s.opts && p.ctx === s.opts.ctx) || [''])[0] : '';
  if (runKey !== lastSyncedRun) {
    lastSyncedRun = runKey;
    if (runKey) {
      adv.update((v) => ({ ...v, preset: runKey }));
      // Step 3 shows the same mode as the header, so a beginner never sees
      // "Chat" while Coding runs.
      if (SIMPLE_PRESETS[runKey]) simp.update((v) => ({ ...v, preset: runKey }));
    }
  }
  return runKey;
}

export async function refreshStatus() {
  try {
    const s = await getStatus();
    statusError.set(false);
    status.set(s);
    if (!get(catalog)) await ensureCatalog();
    syncRunningMode(s);
  } catch (e) {
    statusError.set(true);
  }
}

export function deriveStatusRows(s, c = get(catalog)) {
  return [
    ['Program', s.running && c ? c.engines[s.engine].label : '—'],
    ['Model', s.model_label || '—'],
    ['Process ID', fmt(s.pid)],
    ['Used by the program', fmt(s.rss_gib, ' GiB')],
    ['Conversation length', s.opts ? Number(s.opts.ctx).toLocaleString('en-US') : '—'],
    ['Automatic restarts (10 min)', fmt(s.restarts_recent)],
    ['Port', c ? c.port : '—'],
  ];
}

export function deriveMemoryRows(s) {
  const m = s.memory || {};
  // A missing field shows "—", not NaN.
  const both = (x, y) => (x == null || y == null ? null : x + y);
  return [
    ['Free now', gib(m.free_gib)],
    ['Available including cache (free + inactive)', gib(both(m.free_gib, m.inactive_gib))],
    ['Active', gib(m.active_gib)],
    ['Inactive (system cache)', gib(m.inactive_gib)],
    ['Wired (system)', gib(m.wired_gib)],
    ['Compressed', gib(m.compressor_gib)],
    ['Swap (disk used as memory)', m.swap_used_gib == null ? '—' : `${m.swap_used_gib} of ${m.swap_total_gib} GiB`],
  ];
}

export async function refreshLog() {
  try {
    const { log } = await getLog();
    logText.set(log);
  } catch (e) {}
}

export async function refreshHistory() {
  try {
    const { events } = await getHistory();
    historyEvents.set(events.slice(0, 40));
  } catch (e) {}
}

export const historyNames = {
  start: 'Start', stop: 'Stop', crash: 'Crash', restart: 'Automatic restart',
  gave_up: 'Restarts exhausted', chat: 'Question', cache_cleared: 'Cache cleared', watchdog_error: 'Watchdog error',
};

// ---- components ----
export async function loadComponents() {
  loadFolders();
  try {
    const { items } = await getComponents();
    comps.set(items);
  } catch (e) {
    return;
  }
  // reveal a job that started elsewhere (a fresh install, a download)
  const running = get(comps).find((c) => c.job && c.job.state === 'running');
  const watched = get(jobPanel);
  if (running && (!watched || watched.id !== running.job.id)) watchJob(running.job.id, running.label);
}

export async function componentAction(act, id, label) {
  if (act === 'uninstall') {
    const yes = await confirmBox(`Remove "${label}"? Its files will be deleted. You can install it again later.`);
    if (!yes) return null;
    const r = await uninstallComponent(id);
    if (!r.ok) { toast({ description: friendly(r.error), tone: 'danger' }); return null; }
    watchJob(r.job, label);
  } else {
    const r = await installComponent(id);
    if (!r.ok) { toast({ description: friendly(r.error), tone: 'danger' }); return null; }
    if (r.job) watchJob(r.job, label);
    else toast({ description: 'The model download has started. Progress is shown in its row.' });
  }
  loadComponents();
  return true;
}

export async function cancelWatchedJob() {
  const watched = get(jobPanel);
  if (watched) await cancelJob(watched.id);
}

// One watcher for one job, exactly as the old panel kept.
let jobWatchTimer = null;
let jobWatchId = null;

export function watchJob(jobId, label) {
  if (jobWatchTimer) clearInterval(jobWatchTimer);
  jobWatchId = jobId;
  jobPanel.set({ id: jobId, label: label || '', log: '', running: true });
  const tick = async () => {
    const j = await getJob(jobId);
    if (!j || j.detail) return;
    jobPanel.update((p) => (p && p.id === jobId ? { ...p, log: j.log, running: j.state === 'running' } : p));
    if (j.state !== 'running' && jobWatchId === jobId) {
      clearInterval(jobWatchTimer);
      jobWatchTimer = null;
      jobWatchId = null;
      jobPanel.set(null);
      loadComponents();
      refreshStatus();
    }
  };
  jobWatchTimer = setInterval(tick, 2000);
  tick();
}

// ---- model folders ----
export async function loadFolders() {
  try {
    const d = await getModelDirs();
    folders.set({ dirs: d.dirs || [], found: d.found || [] });
  } catch (e) {}
}

export async function addFolder(path) {
  const clean = path.trim();
  if (!clean) { folderMsg.set('Paste the path to the folder.'); return false; }
  const r = await addModelDir(clean);
  if (!r.ok) { folderMsg.set(r.error); return false; }
  folderMsg.set(r.found ? `Models found: ${r.found}.` : 'Folder added, but it contains no models.');
  await afterFolderChange();
  return true;
}

export async function removeFolder(path) {
  const r = await removeModelDir(path);
  folderMsg.set('Folder removed from the list. Models found: ' + r.found + '.');
  await afterFolderChange();
}

async function afterFolderChange() {
  catalog.set(await getCatalog());
  // as in app.js: the simple model list drops models that are gone
  const c = get(catalog);
  const s = get(simp);
  const opts = simpleModelOptions(c);
  const model = opts.some((o) => o.value === s.model) ? s.model : (opts[0] ? opts[0].value : '');
  simp.update((v) => ({ ...v, model }));
  refreshSimpleModes();
  loadFolders();
  loadComponents();
  refreshStatus();
}

// ---- models added from Hugging Face ----
export async function loadUserModels() {
  try {
    const { models } = await getUserModels();
    userModels.set(models);
  } catch (e) {}
}

export async function addHfModel(repo) {
  const clean = repo.trim();
  if (!clean) return;
  hfMsg.set('Checking the repository on Hugging Face…');
  const r = await addUserModel(clean);
  if (!r.ok) { hfMsg.set(r.error); return false; }
  hfMsg.set(`Added ${r.label} (${r.engine}, about ${r.size_gib} GiB). Press Install in the list above to download it.`);
  catalog.set(await getCatalog());
  loadComponents();
  loadUserModels();
  return true;
}

export async function removeHfModel(key) {
  const r = await removeUserModel(key);
  if (!r.ok) { hfMsg.set(r.error); return; }
  catalog.set(await getCatalog());
  loadComponents();
  loadUserModels();
}

// ---- general settings ----
export async function loadSettings() {
  try {
    const s = await getSettings();
    appSettings.set(s);
    try { localStorage.setItem('start_view', s.start_view); } catch (e) {}
  } catch (e) {}
}

export async function saveSettingsFrom(body) {
  const r = await saveSettings(body);
  const prev = get(appSettings);
  if (!r.ok) { settingsMsg.set(r.error); return false; }
  settingsMsg.set('Saved.' + (body.autostart !== !!prev.autostart ? ' The autostart change takes effect after the panel restarts.' : ''));
  await loadSettings();
  refreshStatus();
  return true;
}
