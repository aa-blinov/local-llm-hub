// Точечные записи: трогаем DOM только если значение изменилось.
function setDis(id, v) { const el = document.getElementById(id); if (el && el.disabled !== !!v) el.disabled = !!v; }
function setCls(id, cls) { const el = document.getElementById(id); if (el && el.className !== cls) el.className = cls; }
function setPrimary(id, on) { const el = document.getElementById(id); if (el && el.classList.contains("primary") !== !!on) el.classList.toggle("primary", !!on); }

// Не трогаем DOM, если содержимое не изменилось: иначе обновление каждые несколько секунд мигает.
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

// Local LLM Hub: веб-интерфейс. Без сборки и внешних библиотек.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const gib = (v) => (v == null ? "—" : v.toFixed(2) + " ГиБ");
const fmt = (v, u = "") => (v == null ? "—" : v + u);

let catalog = null;
let status = null;
let comps = [];
let preflightTimer = null;
let dlTimer = null;
let jobWatch = null;

// Подписи для простого режима. Ключи — из config/registry.json.
const SIMPLE_MODELS = {
  "ornith-4bit": { name: "Умная (рекомендуется)", size: "≈18 ГБ", about: "Отвечает на вопросы и помогает с кодом. Подходит для большинства задач." },
  "ornith-6bit": { name: "Умная и точнее (занимает больше места)", size: "≈26 ГБ", about: "Чуть точнее предыдущей, но занимает больше места и работает медленнее." },
  "inkling-4-8bit": { name: "Альтернативная", size: "≈19 ГБ", about: "Альтернативная модель для вопросов и разговоров." },
  "inkling-gguf-q4km": { name: "Альтернативная, для опытных", size: "≈17 ГБ", about: "Нужна программа llama.cpp. Для опытных пользователей." },
  "smoke-qwen-0.5b": { name: "Тестовая, маленькая", size: "≈0,3 ГБ", about: "Маленькая и быстрая, только чтобы проверить, что всё работает. Для обычной работы не нужна." },
};
const SIMPLE_PRESETS = {
  chat: "Чат — для разговоров и вопросов (быстрый старт)",
  coding: "Кодинг — для работы с кодом (помнит больше текста)",
};

// Ошибки переводим на язык действия. Исходный текст остаётся в журнале.
const FRIENDLY = [
  [/порт (\d+) уже занят/, (m) => `Порт ${m[1]} занят другой программой. Закройте её или перезагрузите Mac.`],
  [/не найден бинарник/, () => "Программа для моделей не установлена. Установите её на шаге 1."],
  [/файлы модели не найдены/, () => "Модель не скачана. Скачайте её на шаге 2."],
  [/движок уже запущен/, () => "Ассистент уже запущен."],
  [/модель ещё загружается/, () => "Модель ещё загружается. Подождите около минуты и попробуйте снова."],
  [/движок не запущен/, () => "Сначала запустите ассистента (шаг 3)."],
  [/движок запущен: сначала остановите/, () => "Сначала остановите ассистента, потом удаляйте программу."],
  [/модель запущена/, () => "Сначала остановите ассистента, потом удаляйте модель."],
  [/уже выполняется/, () => "Эта операция уже идёт. Дождитесь её окончания."],
  [/нет такого пресета/, () => "Такого режима нет. Выберите режим из списка."],
];
function friendly(msg) {
  if (!msg) return "Что-то пошло не так. Посмотрите журнал программы.";
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

// ---- каталог ----
function fillCatalog(c) {
  catalog = c;
  // подробный режим
  const pre = $("preset");
  pre.add(new Option("— вручную —", ""));
  for (const [k, p] of Object.entries(c.presets)) pre.add(new Option(p.label, k));
  const eng = $("engine");
  for (const [k, e] of Object.entries(c.engines)) eng.add(new Option(e.label + (e.binary_ok ? "" : " (не установлена)"), k));
  eng.onchange = () => { fillModels(); fillCtx(); refreshPreflight(); };
  $("model").onchange = () => { fillCtx(); refreshPreflight(); updateDownload(); };
  $("ctx").onchange = refreshPreflight;
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

  // простой режим
  rebuildSimpleModels(d.model);
  const sm = $("s-model");
  const sp = $("s-preset");
  for (const [k, label] of Object.entries(SIMPLE_PRESETS)) if (c.presets[k]) sp.add(new Option(label, k));
  sp.value = "chat";
  sm.onchange = () => { renderSimple(); refreshPreflight(); };
  sp.onchange = () => { renderSimple(); refreshPreflight(); };
  $("s-engine-btn").onclick = installEngineForSimple;
  $("s-model-btn").onclick = () => startModelDownload($("s-model").value);
  $("s-start").onclick = startSimple;
  $("s-stop").onclick = stopEngine;
  $("s-send").onclick = () => sendChat($("s-prompt").value, 600, $("s-answer"), $("s-chatstat"));
  $("s-copy").onclick = async () => {
    try { await navigator.clipboard.writeText(lastAnswer); $("s-chatstat").textContent = "Ответ скопирован. Вставьте его в Word или Pages."; }
    catch (e) { $("s-chatstat").textContent = "Не удалось скопировать. Выделите текст ответа мышью и нажмите Command+C."; }
  };

  fillModels(d.model);
  refreshPreflight();
}

function rebuildSimpleModels(selected) {
  const sm = $("s-model");
  const keep = selected || sm.value;
  sm.innerHTML = "";
  for (const [k, info] of Object.entries(catalog.models)) {
    if (!(k in SIMPLE_MODELS) && !info.exists) continue;
    sm.add(new Option((SIMPLE_MODELS[k] || {}).name || info.label, k));
  }
  sm.value = [...sm.options].some((o) => o.value === keep) ? keep : (sm.options[0] ? sm.options[0].value : "");
}

function fillModels(selected) {
  const key = $("engine").value;
  const m = $("model");
  m.innerHTML = "";
  for (const [k, info] of Object.entries(catalog.models)) {
    if (info.engine !== key) continue;
    m.add(new Option(info.label + (info.exists ? "" : " (не скачана)"), k));
  }
  if (selected && [...m.options].some((o) => o.value === selected)) m.value = selected;
  updateDownload();
}

function fillCtx(selected) {
  const e = catalog.engines[$("engine").value];
  const cs = $("ctx");
  cs.innerHTML = "";
  for (const c of e.ctx_choices) cs.add(new Option(c.toLocaleString("ru") + " токенов", c));
  if (selected) cs.value = selected;
  $("mlxopts").style.display = $("engine").value === "mlx" ? "" : "none";
  fillPrefill();
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
  btn.textContent = info.exists ? "Модель на диске" : "Скачать модель";
  $("dlstate").textContent = info.can_download ? "" : "Эту модель нужно положить на диск вручную";
}

// ---- проверка памяти ----
function refreshPreflight() {
  clearTimeout(preflightTimer);
  preflightTimer = setTimeout(async () => {
    const model = $("model").value;
    const ctx = $("ctx").value;
    if (model && ctx) {
      const v = await api(`/api/preflight?model=${encodeURIComponent(model)}&ctx=${ctx}`);
      const el = $("verdict");
      el.className = "verdict " + ({ ok: "good", tight: "warn", risk: "bad" }[v.verdict] || "");
      el.textContent = v.verdict === "unknown" ? (v.message || "Проверка памяти недоступна") : v.message;
    }
    const sm = $("s-model").value;
    const sp = $("s-preset").value;
    const ctxSimple = catalog.presets[sp] ? catalog.presets[sp].ctx : 32768;
    if (sm) {
      const v = await api(`/api/preflight?model=${encodeURIComponent(sm)}&ctx=${ctxSimple}`);
      const text = {
        ok: ["good", "Памяти хватает."],
        tight: ["warn", "Памяти впритык. Закройте большие программы: браузер с множеством вкладок, видеоредакторы."],
        risk: ["bad", "Памяти может не хватить. Выберите режим «Чат» или закройте программы."],
      }[v.verdict] || ["", "Проверка памяти недоступна."];
      $("s-memory").className = "verdict " + text[0];
      $("s-memory").textContent = text[1];
    }
  }, 200);
}

// ---- состояние ----
function runningLabel(s) {
  // Какой режим сейчас запущен: ищем пресет с тем же моделью и длиной разговора.
  if (!s.running || !catalog) return "";
  const names = { chat: "Чат", coding: "Кодинг", long: "Длинный разговор" };
  const hit = Object.entries(catalog.presets).find(([, p]) => p.model === s.model && s.opts && p.ctx === s.opts.ctx);
  const mode = hit ? (names[hit[0]] || hit[1].label) : "Свои настройки";
  return `${mode}, ${(SIMPLE_MODELS[s.model] || {}).name || s.model_label || s.model}`;
}

let lastSyncedRun = null;
function render(s) {
  status = s;
  $("runinfo").textContent = runningLabel(s);
  // Поле «Режим» в настройках показывает запущенный режим, когда он поменялся.
  const runKey = s.running && catalog ? (Object.entries(catalog.presets).find(([, p]) => p.model === s.model && s.opts && p.ctx === s.opts.ctx) || [""])[0] : "";
  if (runKey !== lastSyncedRun) {
    lastSyncedRun = runKey;
    if (runKey) $("preset").value = runKey;
  }
  setCls("dot", "dot " + (s.ready ? "ok-bg" : s.running ? "wait-bg" : "off-bg"));
  $("state").textContent = s.ready ? "ассистент готов" : s.running ? "загружается…" : "остановлен";
  $("status").innerHTML = [
    ["Программа", s.running ? catalog.engines[s.engine].label : "—"],
    ["Модель", s.model_label || "—"],
    ["Номер процесса", fmt(s.pid)],
    ["Занято программой", fmt(s.rss_gib, " ГБ")],
    ["Объём памяти разговора", s.opts ? Number(s.opts.ctx).toLocaleString("ru") : "—"],
    ["Автоперезапусков за 10 мин", fmt(s.restarts_recent)],
    ["Порт", catalog.port],
  ].map(([a, b]) => `<div class="row"><span>${esc(a)}</span><span>${esc(b)}</span></div>`).join("");
  $("loaderr").textContent = s.load_error ? "Ошибка загрузки: " + friendly(s.load_error) : "";
  const m = s.memory;
  $("mem").innerHTML = [
    ["Свободно сейчас", gib(m.free_gib)],
    ["Доступно с учётом кэша (свободно + неактивная память)", gib(m.free_gib + m.inactive_gib)],
    ["Активная", gib(m.active_gib)],
    ["Неактивная (кэш системы)", gib(m.inactive_gib)],
    ["Системная (wired)", gib(m.wired_gib)],
    ["Сжатая", gib(m.compressor_gib)],
    ["Своп (дисковая память)", m.swap_used_gib == null ? "—" : `${m.swap_used_gib} из ${m.swap_total_gib} ГБ`],
  ].map(([a, b]) => `<div class="row"><span>${esc(a)}</span><span>${esc(b)}</span></div>`).join("");
  $("memwarn").textContent = m.swap_used_gib > ((appSettings && appSettings.swap_warn_gb) || 12)
    ? "Диск используется как память, работа станет медленнее. Закройте лишние программы." : "";
  $("cache").innerHTML = `<div class="row"><span>Запомненное начало разговоров</span><span>${gib(s.apc_disk_gib)}</span></div>`;
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
    $("state").textContent = "панель недоступна";
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
    start: "Запуск", stop: "Остановка", crash: "Сбой", restart: "Автоперезапуск",
    gave_up: "Перезапуски исчерпаны", chat: "Вопрос", cache_cleared: "Кэш очищен", watchdog_error: "Ошибка наблюдателя",
  };
  $("history").innerHTML = events.slice(0, 40).map((e) => {
    const extra = e.event === "chat" ? `, ${e.tok_s ?? "—"} tok/s` : (e.exit_code != null ? `, код ${e.exit_code}` : "");
    return `<div class="hist-row"><span class="t">${esc(e.ts.slice(5, 16).replace("T", " "))}</span> ${esc(names[e.event] || e.event)}${e.model ? " — " + esc(e.model) : ""}${esc(extra)}</div>`;
  }).join("") || '<p class="hint">Событий пока нет.</p>';
}

// ---- действия: подробный режим ----
async function startAdvanced() {
  $("actmsg").textContent = "Запуск…";
  const body = { model: $("model").value, ctx: +$("ctx").value };
  if ($("engine").value === "mlx") {
    body.prefill = +$("prefill").value;
    body.apc = $("apc").checked;
    body.apc_mem_gb = +$("apcmem").value;
  }
  const r = await api("/api/start", body);
  $("actmsg").textContent = r.ok ? "Ассистент запускается, модель загружается 1–2 минуты." : friendly(r.error);
  refresh();
}

async function stopEngine() {
  const r = await api("/api/stop", {});
  $("actmsg").textContent = r.ok ? "Остановлен." : "Не удалось остановить. Посмотрите журнал.";
  $("s-run-text").textContent = r.ok ? "Ассистент остановлен." : "Не удалось остановить. Посмотрите журнал программы.";
  refresh();
}

async function clearCache() {
  const r = await api("/api/cache/clear", {});
  $("actmsg").textContent = r.ok ? "Кэш очищен." : friendly(r.error);
  refresh();
}

async function syncOpencode() {
  const r = await api("/api/opencode/sync", {});
  $("ocmsg").textContent = r.ok
    ? `Настройки для opencode обновлены: ${r.models} моделей, контекст ${Number(r.context).toLocaleString("ru")}. Резервная копия создана.`
    : r.error;
}

// ---- загрузка и установка ----
async function startModelDownload(key) {
  const info = catalog.models[key];
  if (!info) return;
  const size = (SIMPLE_MODELS[key] || {}).size || "";
  if (!confirm(`Скачать «${info.label}»${size ? " (" + size + ")" : ""}? Загрузка может занять от 10 до 40 минут. Окно можно закрыть, загрузка продолжится.`)) return;
  const r = await api("/api/download", { model: key });
  if (!r.ok) { $("s-model-text").textContent = friendly(r.error); $("dlstate").textContent = friendly(r.error); return; }
  $("dlstate").textContent = "Загрузка…";
  pollDownload(key);
}

function pollDownload(key) {
  clearInterval(dlTimer);
  dlTimer = setInterval(async () => {
    const d = await api(`/api/download/${encodeURIComponent(key)}`);
    const pct = d.percent == null ? "" : ` ${d.percent}%`;
    if (d.state === "running") {
      $("dlstate").textContent = "Загрузка…" + pct;
      $("s-model-text").textContent = "Загрузка…" + pct + ". Можно заниматься другими делами.";
    } else if (d.state === "done") {
      clearInterval(dlTimer);
      $("dlstate").textContent = "Готово. Модель на диске.";
      $("s-model-text").textContent = "Модель скачана.";
      catalog = await api("/api/catalog");
      refresh();
    } else if (d.state === "error") {
      clearInterval(dlTimer);
      $("s-model-text").textContent = d.error || "Загрузка прервалась. Нажмите «Скачать модель» ещё раз.";
      $("dlstate").textContent = "";
    }
  }, 2000);
}

async function installEngineForSimple() {
  const key = catalog.models[$("s-model").value].engine;
  const label = catalog.engines[key].label;
  if (!confirm(`Установить «${label}»? Займёт около 2 ГБ и 3–5 минут. Окно можно закрыть, установка продолжится.`)) return;
  const r = await api("/api/components/install", { id: `engine:${key}` });
  if (!r.ok) { $("s-engine-text").textContent = friendly(r.error); return; }
  watchJob(r.job, label);
  loadComponents();
}

// ---- запуск и чат для простого режима ----
let transient = { text: "", until: 0 };
function say(text, ms = 8000) { transient = { text, until: Date.now() + ms }; }

async function startSimple() {
  const model = $("s-model").value;
  const preset = $("s-preset").value;
  say("Запускаю…");
  const r = await api("/api/start", { model, preset });
  say(r.ok ? "Ассистент запускается. Это занимает около минуты." : friendly(r.error), 10000);
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

  // шаг 1
  const loaded = comps.length > 0;  // до первого ответа не утверждаем, что ничего не установлено
  $("st-engine").classList.toggle("done", engineOk);
  $("s-engine-text").innerHTML = !loaded ? "Проверяю…" : engineOk
    ? '<span class="good">Установлено</span>'
    : (engJob ? "Установка идёт, подождите несколько минут…" : "Не установлено. Нажмите «Установить».");
  setDis("s-engine-btn", !loaded || engineOk || engJob);
  setDis("s-model-btn", !loaded || modelOk || !!dl || !(info && info.can_download));

  // шаг 2
  $("st-model").classList.toggle("done", modelOk);
  const sm = SIMPLE_MODELS[model] || {};
  $("s-model-info").textContent = info ? `${sm.size || ""}. ${sm.about || ""}` : "";
  if (modelOk) {
    $("s-model-text").innerHTML = '<span class="good">Модель скачана</span>';
  } else if (dl) {
    $("s-model-text").textContent = "Загрузка…" + (dl.percent == null ? "" : " " + dl.percent + "%");
  } else {
    $("s-model-text").textContent = info && !info.can_download ? "Эту модель нужно положить на диск вручную." : "";
  }
  $("s-model-btn").textContent = modelOk ? "Скачано" : "Скачать модель";

  // шаг 3
  const ready1 = engineOk && modelOk;
  $("st-run").classList.toggle("done", isThis && status.ready);
  $("st-run").classList.toggle("locked", !ready1);
  setDis("s-start", !ready1 || running);
  setDis("s-stop", !running);
  if (transient.until > Date.now()) {
    $("s-run-text").textContent = transient.text;
  } else if (isThis && status.ready) {
    $("s-run-text").innerHTML = '<span class="good">Ассистент работает. Напишите вопрос в поле ниже.</span>';
  } else if (isThis) {
    $("s-run-text").textContent = "Загружается, это около минуты…" + (status.load_error ? " " + friendly(status.load_error) : "");
  } else if (running) {
    $("s-run-text").textContent = "Сейчас запущена другая модель. Остановите её, чтобы запустить эту.";
  } else if (!ready1) {
    $("s-run-text").textContent = "Сначала выполните шаги 1 и 2.";
  } else {
    $("s-run-text").textContent = "Ассистент остановлен. Нажмите «Запустить», когда будете готовы.";
  }

  // шаг 4
  $("st-chat").classList.toggle("locked", !(isThis && status.ready));
  setDis("s-send", !(isThis && status.ready));

  // единый индикатор: показываем одно текущее действие
  const ld = $("s-loader");
  let label = null, pct = null, indet = false;
  if (engJob) { label = "Устанавливаю программу для моделей"; indet = true; }
  else if (dl) { label = "Скачиваю модель"; pct = dl.percent; }
  else if (running && !isThis) { label = "Сейчас работает другой ассистент"; }
  else if (isThis && !status.ready) { label = "Загружаю модель в память, это около минуты"; indet = true; }
  else if (chatBusy) { label = "Думаю над ответом"; indet = true; }
  const vis = label ? "visible" : "hidden";
  if (ld.style.visibility !== vis) ld.style.visibility = vis;
  if (ld.classList.contains("indet") !== indet) ld.classList.toggle("indet", indet);
  ld.querySelector(".ld-label").textContent = label || "";
  ld.querySelector(".ld-pct").textContent = pct != null ? Math.round(pct) + "%" : "";
  const fill = ld.querySelector(".ld-fill");
  const tf = indet ? "" : `scaleX(${(pct || 0) / 100})`;
  if (fill.style.transform !== tf) fill.style.transform = tf;

  // одна главная кнопка на экране: та, что нужна сейчас
  const primary = (id, on) => setPrimary(id, on);
  primary("s-engine-btn", loaded && !engineOk && !engJob);
  primary("s-model-btn", loaded && engineOk && !modelOk && !dl);
  primary("s-start", ready1 && !running);
  primary("s-send", isThis && status.ready && !chatBusy);
}

let chatBusy = false;

function renderAnswer(text) {
  // Блоки кода — в рамку; остальное — простая разметка (заголовки, жирный, списки). Всё экранируем.
  const parts = String(text).split("```");
  return parts.map((part, i) => {
    if (i % 2 === 1) {
      const body = part.replace(/^[a-zA-Z0-9+#.-]*\n/, "");  // убираем название языка в первой строке
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

async function sendChat(prompt, maxTokens, answerEl, statEl) {
  statEl.textContent = "Думаю… Ответ обычно приходит за 2–30 секунд.";
  chatBusy = true;
  renderSimple();
  answerEl.innerHTML = "";
  const copyRow = $("s-copy-row");
  if (copyRow) $("s-copy").disabled = true;
  const r = await api("/api/chat", { prompt, max_tokens: maxTokens });
  chatBusy = false;
  if (r.ok) {
    lastAnswer = r.answer;
    answerEl.innerHTML = renderAnswer(r.answer);
    statEl.textContent = `Ответ за ${r.seconds} с.`;
    if (copyRow) $("s-copy").disabled = false;
    if (answerEl.id === "s-answer") $("s-prompt").value = "";
  } else {
    statEl.textContent = friendly(r.error);
  }
  refresh();
  refreshHistory();
}

// ---- раздел «Компоненты» ----
async function loadComponents() {
  loadFolders();
  const { items } = await api("/api/components");
  comps = items;
  $("comp-engines").innerHTML = items.filter((c) => c.kind === "engine").map(compRow).join("");
  $("comp-models").innerHTML = items.filter((c) => c.kind === "model").map(compRow).join("");
  document.querySelectorAll("#view-components button[data-act]").forEach((b) => {
    b.onclick = () => componentAction(b.dataset.act, b.dataset.id, b.dataset.label);
  });
  if (!catalog) refresh(); else renderSimple();  // шаги ждут каталог: не ждём следующего обновления
  const running = items.find((c) => c.job && c.job.state === "running");
  if (running && (!jobWatch || jobWatch.id !== running.job.id)) watchJob(running.job.id, running.label);
  renderSimple();
}

function compRow(c) {
  const badge = c.installed ? '<span class="badge on">установлено</span>' : '<span class="badge off">нет</span>';
  const size = c.size_gib == null ? "—" : c.size_gib.toFixed(2) + " ГиБ";
  let extra = "";
  if (c.download) extra = c.download.percent == null ? "загрузка…" : `загрузка ${c.download.percent}%`;
  else if (c.job && c.job.state === "running") extra = c.job.action === "install" ? "установка…" : "удаление…";
  else if (c.job && c.job.state === "error") extra = "ошибка: " + friendly(c.job.error || "");
  const busy = !!(c.download || (c.job && c.job.state === "running"));
  const install = c.can_install ? `<button class="primary" data-act="install" data-id="${esc(c.id)}" data-label="${esc(c.label)}" ${busy ? "disabled" : ""}>Установить</button>` : "";
  const remove = c.can_uninstall ? `<button data-act="uninstall" data-id="${esc(c.id)}" data-label="${esc(c.label)}" ${busy ? "disabled" : ""}>Удалить</button>` : "";
  return `<div class="comp">
    <div><div class="name">${esc(c.label)}</div><div class="sub">${esc(c.note)}${extra ? ", " + esc(extra) : ""}</div></div>
    <div class="size">${esc(size)}</div>
    <div>${badge}</div>
    <div class="btns">${install}${remove}</div>
  </div>`;
}

async function componentAction(act, id, label) {
  if (act === "uninstall") {
    if (!confirm(`Удалить «${label}»? Файлы будут удалены. Вернуть можно повторной установкой.`)) return;
    const r = await api("/api/components/uninstall", { id });
    if (!r.ok) { alert(friendly(r.error)); return; }
    watchJob(r.job, label);
  } else {
    const r = await api("/api/components/install", { id });
    if (!r.ok) { alert(friendly(r.error)); return; }
    if (r.job) watchJob(r.job, label);
    else { alert("Загрузка модели запущена. Прогресс показан в строке."); }
  }
  loadComponents();
}

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

// ---- общие настройки ----
let appSettings = null;
async function loadSettings() {
  appSettings = await api("/api/settings");
  $("st-autostart").checked = !!appSettings.autostart;
  $("st-view").value = appSettings.start_view;
  $("st-dir").value = appSettings.download_dir || "";
  $("st-dir-hint").textContent = `Сейчас модели лежат в: ${appSettings.hf_cache_root}`;
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
  $("st-msg").textContent = "Сохранено." + (body.autostart !== !!appSettings.autostart ? " Автозапуск изменится после перезапуска панели." : "");
  await loadSettings();
  refresh();
};

// ---- папки с моделями ----
async function loadFolders() {
  const d = await api("/api/model-dirs");
  $("folder-list").innerHTML = d.dirs.length
    ? d.dirs.map((p) => `<div class="comp" style="grid-template-columns:minmax(0,1fr) auto"><div class="name" style="font-size:15px;word-break:break-all">${esc(p)}</div><div class="btns"><button data-rm="${esc(p)}" class="small">Убрать</button></div></div>`).join("")
    : '<p class="hint">Папок пока нет.</p>';
  $("folder-found").innerHTML = d.found.length
    ? d.found.map((m) => `<div class="comp" style="grid-template-columns:minmax(0,1fr) auto"><div><div class="name">${esc(m.label)}</div><div class="sub">${esc(m.path)}</div></div><div><span class="badge on">готова</span></div></div>`).join("")
    : '<p class="hint">Ничего не найдено. Проверьте, что в папке есть модель (папка с config.json и файлами .safetensors, или файлы .gguf).</p>';
  document.querySelectorAll("#folder-list button[data-rm]").forEach((b) => {
    b.onclick = async () => {
      const r = await api("/api/model-dirs/remove", { path: b.dataset.rm });
      $("folder-msg").textContent = "Папка убрана из списка. Найдено моделей: " + r.found + ".";
      catalog = await api("/api/catalog");
      rebuildSimpleModels();
      loadFolders(); loadComponents(); refresh();
    };
  });
}

$("folder-add").onclick = async () => {
  const path = $("folder-path").value.trim();
  if (!path) { $("folder-msg").textContent = "Вставьте путь к папке."; return; }
  const r = await api("/api/model-dirs/add", { path });
  if (!r.ok) { $("folder-msg").textContent = r.error; return; }
  $("folder-msg").textContent = r.found ? `Нашли моделей: ${r.found}.` : "Папка добавлена, но модели в ней не найдены.";
  $("folder-path").value = "";
  catalog = await api("/api/catalog");
  rebuildSimpleModels();
  loadFolders(); loadComponents(); refresh();
};

// ---- вкладки ----
function route() {
  const h = location.hash || ("#" + ((appSettings && appSettings.start_view) || "simple"));
  const view = { "#panel": "panel", "#components": "components" }[h] || "simple";
  $("view-simple").hidden = view !== "simple";
  $("view-panel").hidden = view !== "panel";
  $("view-components").hidden = view !== "components";
  $("tab-simple").classList.toggle("on", view === "simple");
  $("tab-panel").classList.toggle("on", view === "panel");
  $("tab-components").classList.toggle("on", view === "components");
  if (view === "components") loadComponents();
}
window.addEventListener("hashchange", route);

// ---- тема: светлая, тёмная или как в системе ----
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  try { localStorage.setItem("theme", t || ""); } catch (e) {}
}
$("theme").onclick = () => {
  const cur = document.documentElement.dataset.theme || "";
  applyTheme(cur === "" ? "dark" : cur === "dark" ? "light" : "");
};
try { applyTheme(localStorage.getItem("theme") || ""); } catch (e) {}

// ---- старт ----
loadSettings().then(() => route());
refresh();
loadComponents();
refreshLog();
refreshHistory();
setInterval(refresh, 4000);
setInterval(loadComponents, 6000);
setInterval(refreshLog, 4000);
setInterval(refreshHistory, 8000);
