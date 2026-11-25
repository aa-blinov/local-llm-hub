<script>
  // Simple view: four steps in one column. All texts and states follow the
  // original panel: checking, installed, installing, downloading with
  // progress, ready, loading, stopped.
  import { Button, Card, Progress, Select, Notice, TextArea } from '@monos/ui';
  import {
    status, comps, verdictSimple, runTransient, simpleModelMsg, simpleEngineMsg, catalog,
    simpleChatStat, chatBusy, lastAnswer, cancelVisible,
    recommendText, recommendButton, simpleModes, simp,
    simpleModelOptions, purposeOptions, SIMPLE_PRESETS,
    setSimpleModel, setSimplePreset, setSimpleMode, setSimplePurpose,
    refreshRecommend, useRecommendedModel, startModelDownload, cancelModelDownload,
    installEngineForSimple, startSimple, stopEngineAction, sendChatAction, copyAnswer,
  } from '../lib/state.js';
  import { renderAnswer } from '../lib/markup.js';
  import { nowTick } from '../lib/nowTick.js';
  import { friendly } from '../api.js';

  // The recommended model is fetched when the catalog first arrives and
  // whenever the purpose changes.
  $: if ($catalog && $catalog.presets) void refreshRecommend($simp.purpose);

  let prompt = '';
  let answerHtml = '';
  let sending = false;

  // ---- the reactive replica of renderSimple() ----
  $: model = $simp.model;
  $: info = $catalog && $catalog.models ? $catalog.models[model] : null;
  $: engineKey = info ? info.engine : 'mlx';
  $: engineItem = $comps.find((c) => c.id === `engine:${engineKey}`) || {};
  $: modelItem = $comps.find((c) => c.id === `model:${model}`) || {};
  $: engineOk = !!engineItem.installed;
  $: modelOk = !!(info && info.exists);
  $: engineJob = !!(engineItem.job && engineItem.job.state === 'running');
  $: dl = modelItem.download || null;
  $: running = !!($status && $status.running);
  $: isThis = running && $status.model === model;
  $: loaded = $comps.length > 0; // do not claim nothing is installed before the first answer
  $: ready1 = engineOk && modelOk;
  $: sm = (info && info.simple) || {};

  // step 1
  $: engineText = !loaded ? 'Checking…' : engineOk ? 'Installed'
    : (engineJob ? 'Installing, please wait a few minutes…'
    : ($simpleEngineMsg || 'Not installed. Click “Install”.'));
  $: engineBtnDisabled = !loaded || engineOk || engineJob;
  $: engineBtnHidden = loaded && engineOk;
  $: engineBtnPrimary = loaded && !engineOk && !engineJob;

  // step 2
  $: modelInfoText = info ? `${sm.size || ''}. ${sm.about || ''}` : '';
  // The polling channel only shows through when the steady state has nothing
  // to say, as in the old renderSimple() ordering.
  $: modelCase = modelOk ? 'good' : dl ? 'dl' : (info && !info.can_download) ? 'manual' : '';
  $: modelText = modelCase === 'good' ? 'Model downloaded'
    : modelCase === 'dl' ? 'Downloading…' + (dl.percent == null ? '' : ' ' + dl.percent + '%')
    : modelCase === 'manual' ? 'This model must be placed on disk by hand.'
    : $simpleModelMsg;
  $: modelBtnDisabled = !loaded || modelOk || !!dl || !(info && info.can_download);
  $: modelBtnPrimary = loaded && engineOk && !modelOk && !dl;

  // step 3
  $: runText = $runTransient.until > $nowTick ? $runTransient.text
    : isThis && $status.ready ? 'The assistant is running. Type your question below.'
    : isThis ? 'Loading, this takes about a minute…' + ($status.load_error ? ' ' + friendly($status.load_error) : '')
    : running ? 'Another model is running. Stop it to start this one.'
    : !ready1 ? 'Complete steps 1 and 2 first.'
    : 'The assistant is stopped. Click “Start” when you are ready.';
  $: runGood = isThis && $status.ready && $runTransient.until <= $nowTick;
  $: startDisabled = !ready1 || running;
  $: startPrimary = ready1 && !running;
  $: stopDisabled = !running;

  // step 4
  $: chatReady = isThis && $status && $status.ready;

  // one current action, one indicator
  $: loaderState = engineJob ? { label: 'Installing the model program', pct: null, indet: true }
    : dl ? { label: 'Downloading the model', pct: dl.percent, indet: false }
    : running && !isThis ? { label: 'Another assistant is running', pct: null, indet: true }
    : isThis && $status && !$status.ready ? { label: 'Loading the model into memory, about a minute', pct: null, indet: true }
    : $chatBusy ? { label: 'Thinking about the answer', pct: null, indet: true }
    : null;
  $: loaderVisible = !!loaderState;
  $: loaderLabel = loaderState ? loaderState.label : '';
  $: loaderPct = loaderState && loaderState.pct != null ? Math.round(loaderState.pct) : '';

  // preset choices of the simple view: only the two labelled modes
  $: simplePresetOptions = $catalog
    ? Object.entries(SIMPLE_PRESETS).filter(([k]) => $catalog.presets[k]).map(([k, label]) => ({ value: k, label }))
    : [];

  async function send() {
    if ($chatBusy) return;
    simpleChatStat.set('Thinking… An answer usually takes 2–30 seconds.');
    answerHtml = '';
    sending = true;
    const r = await sendChatAction(prompt, 600, $simp.mode);
    sending = false;
    if (r.ok) {
      answerHtml = renderAnswer(r.answer);
      simpleChatStat.set(`Answered in ${r.seconds} s.`);
    } else {
      simpleChatStat.set(friendly(r.error));
    }
  }
</script>

<div class="steps">
  <div>
    <div class="loader" style:visibility={loaderVisible ? 'visible' : 'hidden'}>
      <div class="ld-top">
        <span>{loaderLabel}</span>
        <span class="ld-pct">{loaderPct != '' ? loaderPct + '%' : ''}</span>
      </div>
      <Progress value={loaderPct === '' ? 0 : loaderPct} indeterminate={loaderState ? loaderState.indet : false} label={loaderLabel} />
    </div>
    <p class="intro">Complete the steps in order. A green step is done.</p>
  </div>

  <div class="step" class:done={engineOk}>
    <div class="num">1</div>
    <div>
      <h3>Install the model program</h3>
      <p class="explain">This is the program that runs models on your Mac. You install it once: about 2 GB, 3–5 minutes.</p>
      <Card>
        <div class="msg" class:good={engineOk}>{engineText}</div>
        <div class="row-actions">
          {#if !engineBtnHidden}
            <Button variant={engineBtnPrimary ? 'primary' : 'secondary'} disabled={engineBtnDisabled} on:click={installEngineForSimple}>Install</Button>
          {/if}
        </div>
      </Card>
    </div>
  </div>

  <div class="step" class:done={modelOk}>
    <div class="num">2</div>
    <div>
      <h3>Choose and download a model</h3>
      <p class="explain">The model is the assistant itself: all its knowledge is stored in it. It downloads once and takes a lot of disk space.</p>
      <Card>
        <label class="lbl first" for="s-purpose">What do you need it for?</label>
        <Select id="s-purpose" options={purposeOptions} value={$simp.purpose} on:change={(e) => setSimplePurpose(e.detail.value)} />
        <div class="row-actions" style="align-items:center">
          <span class="muted" style="flex:1 1 auto;min-width:0">{$recommendText}</span>
          {#if $recommendButton}
            <Button size="md" on:click={useRecommendedModel}>Use the recommended model</Button>
          {/if}
        </div>
        <label class="lbl" for="s-model">Model</label>
        <Select id="s-model" options={simpleModelOptions($catalog)} value={model} on:change={(e) => setSimpleModel(e.detail.value)} />
        <p class="muted" style="margin:var(--ui-space-snug) 0 0">{modelInfoText}</p>
        {#if $simpleModes.length >= 2}
          <label class="lbl" for="s-mode">How it answers</label>
          <Select id="s-mode" options={$simpleModes} value={$simp.mode} on:change={(e) => setSimpleMode(e.detail.value)} />
        {/if}
        <div class="row-actions">
          <Button variant={modelBtnPrimary ? 'primary' : 'secondary'} disabled={modelBtnDisabled} on:click={() => startModelDownload(model)}>
            {modelOk ? 'Downloaded' : 'Download model'}
          </Button>
          {#if $cancelVisible}
            <Button variant="secondary" on:click={cancelModelDownload}>Cancel download</Button>
          {/if}
        </div>
        <div class="msg" class:good={modelOk}>{modelText}</div>
      </Card>
    </div>
  </div>

  <div class="step" class:done={isThis && $status && $status.ready}>
    <div class="num">3</div>
    <div>
      <h3>Start the assistant</h3>
      <p class="explain">Chat is for everyday questions and starts faster. Coding is for working with programs, remembers more text and needs more memory.</p>
      <Card class={ready1 ? '' : 'opacity-60'}>
        <label class="lbl first" for="s-preset">Mode</label>
        <Select id="s-preset" options={simplePresetOptions} value={$simp.preset} on:change={(e) => setSimplePreset(e.detail.value)} />
        {#if $verdictSimple}
          <Notice tone={$verdictSimple.tone || 'info'} class="mt-3">{$verdictSimple.message}</Notice>
        {/if}
        <div class="actions" style="margin-top:var(--ui-space-comfortable)">
          <Button size="lg" class="min-h-[52px]" variant={startPrimary ? 'primary' : 'secondary'} disabled={startDisabled} on:click={startSimple}>Start</Button>
          <Button size="lg" class="min-h-[52px]" variant="secondary" disabled={stopDisabled} on:click={stopEngineAction}>Stop</Button>
        </div>
        <div class="msg" class:good={runGood}>{runText}</div>
      </Card>
    </div>
  </div>

  <div class="step" class:done={false}>
    <div class="num">4</div>
    <div>
      <h3>Ask the assistant</h3>
      <p class="explain">Type a question and press Send. An answer usually takes 2–30 seconds.</p>
      <Card class={chatReady ? '' : 'opacity-60'}>
        <TextArea bind:value={prompt} placeholder="For example: explain in simple words what a model is" rows={4} />
        <div class="row-actions" style="margin-top:var(--ui-space-base)">
          <Button variant={$chatBusy ? 'secondary' : 'primary'} disabled={!chatReady || $chatBusy} on:click={send}>Send</Button>
        </div>
        <div class="answer">{@html answerHtml}</div>
        <div class="row-actions">
          <Button variant="secondary" disabled={!$lastAnswer || $chatBusy || sending} on:click={copyAnswer}>Copy answer</Button>
        </div>
        <p class="muted" id="s-chatstat">{$simpleChatStat}</p>
        <p class="muted" style="margin-top:var(--ui-space-base)">The assistant can make mistakes. Check important facts in reliable sources.</p>
      </Card>
    </div>
  </div>
</div>
