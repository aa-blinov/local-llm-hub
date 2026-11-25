<script>
  // Programs and models view: engines and models with install and remove,
  // adding a model from Hugging Face, model folders, the job log.
  import { Button, Card, Badge, TextField } from '@monos/ui';
  import {
    comps, folders, userModels, jobPanel, hfMsg, folderMsg,
    componentAction, cancelWatchedJob,
    addHfModel, removeHfModel, addFolder, removeFolder,
  } from '../lib/state.js';
  import { friendly } from '../api.js';

  let hfRepo = '';
  let folderPath = '';

  // The job log keeps its place when read to the end, like the program log.
  let jobEl;
  let jobStick = true;
  function onJobScroll() {
    if (jobEl) jobStick = jobEl.scrollTop + jobEl.clientHeight >= jobEl.scrollHeight - 20;
  }
  $: if (jobEl && $jobPanel) {
    if (jobStick) jobEl.scrollTop = jobEl.scrollHeight;
  }

  const rowExtra = (c) => {
    if (c.download) return c.download.percent == null ? 'downloading…' : `downloading ${c.download.percent}%`;
    if (c.job && c.job.state === 'running') return c.job.action === 'install' ? 'installing…' : 'removing…';
    if (c.job && c.job.state === 'error') return 'error: ' + friendly(c.job.error || '');
    return '';
  };
  $: engines = $comps.filter((c) => c.kind === 'engine');
  $: models = $comps.filter((c) => c.kind === 'model');
  const sizeText = (c) => (c.size_gib == null ? '—' : c.size_gib.toFixed(2) + ' GiB');

  async function onFolderAdd() {
    const added = await addFolder(folderPath);
    if (added) folderPath = '';
  }
  async function onFolderRemove(path) {
    await removeFolder(path);
  }
</script>

<Card padding="lg" class="shadow-none">
  <h2 class="panel-title">Programs for models</h2>
  {#each engines as c (c.id)}
    <div class="comp">
      <div>
        <div class="name">{c.label}</div>
        <div class="sub">{c.note}{rowExtra(c) ? ', ' + rowExtra(c) : ''}</div>
      </div>
      <div class="size">{sizeText(c)}</div>
      <div>
        {#if c.installed}<Badge tone="success" class="border border-line rounded-full px-2">installed</Badge>
        {:else}<Badge class="border border-line rounded-full px-2">not installed</Badge>{/if}
      </div>
      <div class="btns">
        {#if c.can_install}
          <Button variant="primary" disabled={!!(c.download || (c.job && c.job.state === 'running'))} on:click={() => componentAction('install', c.id, c.label)}>Install</Button>
        {/if}
        {#if c.can_uninstall}
          <Button variant="secondary" disabled={!!(c.download || (c.job && c.job.state === 'running'))} on:click={() => componentAction('uninstall', c.id, c.label)}>Remove</Button>
        {/if}
      </div>
    </div>
  {/each}

  <h2 class="panel-sub">Models</h2>
  {#each models as c (c.id)}
    <div class="comp">
      <div>
        <div class="name">{c.label}</div>
        <div class="sub">{c.note}{rowExtra(c) ? ', ' + rowExtra(c) : ''}</div>
      </div>
      <div class="size">{sizeText(c)}</div>
      <div>
        {#if c.installed}<Badge tone="success" class="border border-line rounded-full px-2">installed</Badge>
        {:else}<Badge class="border border-line rounded-full px-2">not installed</Badge>{/if}
      </div>
      <div class="btns">
        {#if c.can_install}
          <Button variant="primary" disabled={!!(c.download || (c.job && c.job.state === 'running'))} on:click={() => componentAction('install', c.id, c.label)}>Install</Button>
        {/if}
        {#if c.can_uninstall}
          <Button variant="secondary" disabled={!!(c.download || (c.job && c.job.state === 'running'))} on:click={() => componentAction('uninstall', c.id, c.label)}>Remove</Button>
        {/if}
      </div>
    </div>
  {/each}

  <h2 class="panel-sub">Add a model from Hugging Face</h2>
  <p class="hint">Paste a repository name, for example mlx-community/Qwen3.6-27B-4bit. The app checks it first. Nothing is downloaded until you press Install.</p>
  <div class="row-actions" style="margin-top:var(--ui-space-base)">
    <TextField bind:value={hfRepo} placeholder="owner/model-name" variant="boxed" class="flex-1 min-w-0" />
    <Button variant="secondary" on:click={() => { addHfModel(hfRepo).then((ok) => { if (ok) hfRepo = ''; }); }}>Add</Button>
  </div>
  <p class="hint" style="min-height:2.6em">{$hfMsg}</p>

  {#if $userModels.length}
    <div>
      {#each $userModels as m (m.key)}
        <div class="row flex items-center justify-between gap-4 py-2 border-b border-line">
          <div class="min-w-0">
            <div>{m.label}</div>
            <div class="hint">{m.repo} · {m.engine}</div>
          </div>
          <Button variant="secondary" on:click={() => removeHfModel(m.key)}>Remove from list</Button>
        </div>
      {/each}
    </div>
  {:else}
    <p class="hint">No models added yet.</p>
  {/if}
</Card>

<Card padding="lg" class="shadow-none">
  <h2 class="panel-title">Model folders</h2>
  <p class="hint">If models are already on your disk (an external drive, LM Studio, another folder), add that folder. The app finds them and does not download them again.</p>
  <div class="row-actions" style="margin-top:var(--ui-space-base)">
    <TextField bind:value={folderPath} placeholder="For example: /Volumes/Models or ~/.lmstudio/models" variant="boxed" class="flex-1 min-w-0" />
    <Button variant="secondary" on:click={onFolderAdd}>Add folder</Button>
  </div>
  <p class="hint" style="min-height:2.6em">{$folderMsg}</p>

  <div class="mt-4">
    {#if $folders.dirs.length}
      {#each $folders.dirs as p (p)}
        <div class="comp comp-slim">
          <div class="name break-all text-[15px]">{p}</div>
          <div class="btns"><Button variant="secondary" on:click={() => onFolderRemove(p)}>Remove</Button></div>
        </div>
      {/each}
    {:else}
      <p class="hint">No folders yet.</p>
    {/if}
  </div>
  <h2 class="panel-sub">Found in folders</h2>
  {#if $folders.found.length}
    {#each $folders.found as m}
      <div class="comp comp-slim">
        <div>
          <div class="name">{m.label}</div>
          <div class="sub">{m.path}</div>
        </div>
        <div><Badge tone="success" class="border border-line rounded-full px-2 normal-case">ready</Badge></div>
      </div>
    {/each}
  {:else}
    <p class="hint">Nothing found. Make sure the folder contains a model (a folder with config.json and .safetensors files, or .gguf files).</p>
  {/if}
</Card>

{#if $jobPanel}
  <Card padding="lg" class="shadow-none">
    <h2 class="panel-title">Operation log <span class="hint inline-block ml-3">{$jobPanel.label}</span></h2>
    <div class="row-actions">
      {#if $jobPanel.running}
        <Button variant="secondary" on:click={cancelWatchedJob}>Cancel</Button>
      {/if}
    </div>
    <pre bind:this={jobEl} on:scroll={onJobScroll} style="max-height:220px">{$jobPanel.log}</pre>
  </Card>
{/if}
