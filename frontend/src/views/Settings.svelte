<script>
  // Settings view: Launch and status, Diagnostics (collapsed by default),
  // General settings. The fields, options and messages are the panel's own.
  import { Button, Card, Checkbox, TextField, Select, Notice, TextArea } from '@monos/ui';
  import {
    catalog, status, appSettings, adv, verdictAdv, actMsg, dlStateMsg, ocMsg,
    settingsMsg, ctxAdviced, chatBusy,
    engineOptions, presetOptions, modelsForEngine,
    setAdvEngine, setAdvModel, setAdvCtx, patchAdv, applyPreset,
    startAdvanced, stopEngineAction, clearCacheAction, syncOpencodeAction,
    startModelDownload, sendChatAction, refreshLog, saveSettingsFrom,
    deriveStatusRows, deriveMemoryRows, logText, historyEvents, historyNames,
  } from '../lib/state.js';
  import { renderAnswer } from '../lib/markup.js';
  import { friendly } from '../api.js';

  $: c = $catalog;
  $: a = $adv;
  $: engine = c ? c.engines[a.engine] : null;
  $: ctxChoices = engine ? engine.ctx_choices : [];
  $: prefillChoices = engine ? engine.prefill_choices : [];
  $: showMlx = a.engine === 'mlx';
  $: modelCase = c && c.models ? c.models[a.model] : null;

  $: statusRows = $status ? deriveStatusRows($status) : [];
  $: memoryRows = $status ? deriveMemoryRows($status) : [];
  $: loadErrText = $status && $status.load_error ? 'Loading error: ' + friendly($status.load_error) : '';
  $: memWarnText = $status && $status.memory && $status.memory.swap_used_gib != null
    && $status.memory.swap_used_gib > (($appSettings && $appSettings.swap_warn_gb) || 12)
    ? 'The disk is being used as memory, so work will be slower. Close other programs.' : '';

  const kvOptions = [
    { value: '', label: 'Off (full precision)' },
    { value: '8', label: '8-bit' },
    { value: '4', label: '4-bit (recommended)' },
  ];
  const viewOptions = [
    { value: 'simple', label: 'Simple' },
    { value: 'panel', label: 'Settings' },
    { value: 'components', label: 'Programs and models' },
  ];

  // ---- diagnostics: answer check ----
  let promptText = 'Explain in two sentences why the sky is blue.';
  let maxTok = '600';
  let answerHtml = '';
  let diagStat = '';
  async function sendDiag() {
    diagStat = 'Thinking… An answer usually takes 2–30 seconds.';
    answerHtml = '';
    const r = await sendChatAction(promptText, +maxTok || 600, null);
    diagStat = r.ok ? `Answered in ${r.seconds} s.` : friendly(r.error);
    answerHtml = r.ok ? renderAnswer(r.answer) : '';
  }

  // ---- diagnostics: the log keeps its place when read to the end ----
  let logEl;
  let logStick = true;
  function onLogScroll() {
    logStick = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 20;
  }
  $: if (logEl && $logText !== undefined) {
    if (logStick) logEl.scrollTop = logEl.scrollHeight;
  }

  // ---- diagnostics: history ----
  function histText(e) {
    const extra = e.event === 'chat' ? `, ${e.tok_s ?? '—'} tok/s` : (e.exit_code != null ? `, exit code ${e.exit_code}` : '');
    return `${historyNames[e.event] || e.event}${e.model ? ' — ' + e.model : ''}${extra}`;
  }

  // ---- general settings ----
  let draft = null;
  $: if ($appSettings && !draft) {
    draft = {
      autostart: !!$appSettings.autostart,
      start_view: $appSettings.start_view || 'simple',
      download_dir: $appSettings.download_dir || '',
      hf_token: $appSettings.hf_token ? '••••' : '',
      swap_warn_gb: $appSettings.swap_warn_gb,
    };
  }
  async function saveSettings() {
    const before = $appSettings;
    const body = {
      autostart: draft.autostart,
      start_view: draft.start_view,
      download_dir: draft.download_dir.trim(),
      hf_token: draft.hf_token,
      swap_warn_gb: +draft.swap_warn_gb,
    };
    const ok = await saveSettingsFrom(body);
    if (ok) draft = null; // refilled from the saved settings
  }
</script>

<div class="flex flex-col gap-8 pb-12">
  <!-- Launch and status -->
  <section>
    <h2 class="sec-title">Launch and status</h2>
    <div class="launch-grid">
      <Card padding="lg" class="shadow-none">
        <h2 class="panel-title">Launch</h2>
        <label class="lbl first" for="preset">Mode</label>
        <p class="hint">A ready-made set: Chat for questions, Coding for programs.</p>
        <Select id="preset" options={presetOptions(c)} value={a.preset} on:change={(e) => applyPreset(e.detail.value)} />
        <Notice tone={{ ok: 'success', tight: 'warning', risk: 'danger' }[$verdictAdv.verdict] || 'info'} class="mt-3">
          {$verdictAdv.message}
        </Notice>
        <div class="actions">
          <Button variant="primary" disabled={!!($status && $status.running)} on:click={startAdvanced}>Start</Button>
          <Button variant="secondary" disabled={!($status && $status.running)} on:click={stopEngineAction}>Stop</Button>
        </div>
        <p class="hint" style="min-height:2.6em">{$actMsg}</p>

        <label class="lbl" for="engine">Program for the model</label>
        <p class="hint">It runs the model. MLX is faster on Apple Silicon.</p>
        <Select id="engine" options={engineOptions(c)} value={a.engine} on:change={(e) => setAdvEngine(e.detail.value)} />
        <label class="lbl" for="model">Model</label>
        <Select id="model" options={modelsForEngine(c, a.engine)} value={a.model} on:change={(e) => setAdvModel(e.detail.value)} />
        <div class="row-actions">
          <Button variant="secondary"
            disabled={!modelCase || modelCase.exists || !modelCase.can_download}
            on:click={() => startModelDownload(a.model)}>
            {modelCase && modelCase.exists ? 'Model on disk' : 'Download model'}
          </Button>
          <span class="hint">{$dlStateMsg || (modelCase && !modelCase.can_download ? 'This model must be placed on disk by hand' : '')}</span>
        </div>

        <label class="lbl" for="ctx">Conversation length, tokens</label>
        <p class="hint">How much text the assistant keeps in mind. More means more memory.</p>
        <Select id="ctx" options={ctxChoices.map((v) => ({ value: String(v), label: v.toLocaleString('en-US') + ' tokens' }))} value={a.ctx} on:change={(e) => setAdvCtx(e.detail.value)} />
        <p class="hint">{$ctxAdviced}</p>

        {#if showMlx}
          <div>
            <label class="lbl" for="prefill">Reading step (prefill)</label>
            <p class="hint">How much text is read at once. Smaller saves memory but is slower.</p>
            <Select id="prefill" options={prefillChoices.map((p) => ({ value: String(p), label: String(p) }))} value={a.prefill} on:change={(e) => patchAdv({ prefill: e.detail.value })} />
            <div class="check">
              <Checkbox checked={a.apc} on:change={(e) => patchAdv({ apc: e.target.checked })}>Cache the start of the conversation (APC)</Checkbox>
            </div>
            <p class="hint">Saves the start of the conversation to disk so it is not re-read for every question.</p>
            <label class="lbl" for="apcmem">Cache limit, GB</label>
            <TextField id="apcmem" type="number" bind:value={$adv.apcmem} min="1" max="20" step="1" variant="boxed" />
            <label class="lbl" for="kvbits">Compress the conversation memory (KV cache)</label>
            <p class="hint">Stores the conversation in fewer bits: less memory for long contexts, with some loss of quality. 8-bit is close to full precision; 4-bit saves more but can make answers worse.</p>
            <Select id="kvbits" options={kvOptions} value={a.kvbits} on:change={(e) => patchAdv({ kvbits: e.detail.value })} />
          </div>
        {/if}
      </Card>

      <Card padding="lg" class="shadow-none">
        <h2 class="panel-title">Status</h2>
        <div class="rows">
          {#each statusRows as [k, v]}
            <div class="row"><span>{k}</span><span>{v}</span></div>
          {/each}
        </div>
        <p class="hint bad" style="min-height:2.6em">{loadErrText}</p>
        <h2 class="panel-sub">Memory</h2>
        <div class="rows">
          {#each memoryRows as [k, v]}
            <div class="row"><span>{k}</span><span>{v}</span></div>
          {/each}
        </div>
        <p class="hint warn">{memWarnText}</p>
        <h2 class="panel-sub">Cache and opencode</h2>
        <div class="rows">
          {#if $status}
            <div class="row">
              <span>Saved conversation starts</span>
              <span>{$status.apc_disk_gib == null ? '—' : $status.apc_disk_gib.toFixed(2) + ' GiB'}</span>
            </div>
          {/if}
        </div>
        <div class="row-actions">
          <Button variant="secondary" disabled={!!($status && $status.running)} on:click={clearCacheAction}>Clear cache</Button>
          <Button variant="secondary" on:click={syncOpencodeAction}>Update opencode config</Button>
        </div>
        <p class="hint" style="min-height:2.6em">{$ocMsg}</p>
      </Card>
    </div>
  </section>

  <!-- Diagnostics: collapsed by default -->
  <section>
    <h2 class="sec-title">Diagnostics</h2>
    <Card padding="none" class="shadow-none">
      <details class="diag">
        <summary>
          <h2 class="panel-title">Diagnostics: answer check, program log, history</h2>
        </summary>
        <div class="diag-grid">
          <Card padding="lg" class="shadow-none">
            <h2 class="panel-title">Answer check</h2>
            <label class="lbl first" for="prompt">Prompt</label>
            <TextArea id="prompt" bind:value={promptText} rows={4} />
            <label class="lbl" for="maxtok">Maximum tokens in the answer</label>
            <TextField id="maxtok" type="number" bind:value={maxTok} variant="boxed" min="1" max="2048" />
            <div class="actions"><Button variant="secondary" disabled={!(($status && $status.ready)) || $chatBusy} on:click={sendDiag}>Send</Button></div>
            <p class="hint">{diagStat}</p>
            <div class="answer">{@html answerHtml}</div>
          </Card>
          <Card padding="lg" class="shadow-none logpanel">
            <h2 class="panel-title">
              Program log
              <Button variant="secondary" class="ml-3" on:click={refreshLog}>Refresh</Button>
            </h2>
            <pre bind:this={logEl} on:scroll={onLogScroll}>{$logText}</pre>
          </Card>
          <Card padding="lg" class="shadow-none histpanel">
            <h2 class="panel-title">History</h2>
            {#if $historyEvents.length}
              {#each $historyEvents as e}
                <div class="hist-row"><span class="t">{e.ts.slice(5, 16).replace('T', ' ')}</span> {histText(e)}</div>
              {/each}
            {:else}
              <p class="hint">No events yet.</p>
            {/if}
          </Card>
        </div>
      </details>
    </Card>
  </section>

  <!-- General settings -->
  <section>
    <h2 class="sec-title">General settings</h2>
    <Card padding="lg" class="shadow-none">
      {#if draft}
        <Checkbox bind:checked={draft.autostart}>Start the panel at login</Checkbox>
        <p class="hint">The assistant starts by itself after a restart. Turn it off if you do not need that.</p>
        <label class="lbl" for="st-view">Section to open first</label>
        <Select id="st-view" options={viewOptions} bind:value={draft.start_view} />
        <label class="lbl" for="st-dir">Folder for downloaded models</label>
        <TextField id="st-dir" type="text" bind:value={draft.download_dir} placeholder="Empty — default folder" variant="boxed" />
        <p class="hint">Models are currently stored in: {$appSettings.hf_cache_root}</p>
        <label class="lbl" for="st-token">Hugging Face token (only needed for gated models)</label>
        <TextField id="st-token" type="password" bind:value={draft.hf_token} placeholder="Leave empty if you do not need it" autocomplete="off" variant="boxed" />
        <label class="lbl" for="st-swap">Warn when swap usage exceeds, GB</label>
        <TextField id="st-swap" type="number" bind:value={draft.swap_warn_gb} variant="boxed" min="1" max="64" step="1" />
        <div class="row-actions"><Button variant="secondary" on:click={saveSettings}>Save settings</Button></div>
        <p class="hint">{$settingsMsg}</p>
      {/if}
    </Card>
  </section>
</div>
