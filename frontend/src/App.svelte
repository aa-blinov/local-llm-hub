<script>
  // Application shell: sidebar on desktop, top bar on narrow screens, and the
  // three sections selected by the hash (#simple, #panel, #components).
  import { onMount } from 'svelte';
  import { Button, SidebarItem, Tabs, Toaster } from '@monos/ui';
  import { themeChoice as themeChoiceStore, cycleTheme } from './lib/theme.js';
  import { view, initRouting, route } from './lib/view.js';
  import {
    status, statusError, runningLabel,
    refreshStatus, loadComponents, loadSettings, loadUserModels,
    refreshLog, refreshHistory,
  } from './lib/state.js';
  import Simple from './views/Simple.svelte';
  import Settings from './views/Settings.svelte';
  import ComponentsView from './views/ComponentsView.svelte';
  import ConfirmDialog from './components/ConfirmDialog.svelte';

  const tabItems = [
    { id: 'simple', label: 'Simple' },
    { id: 'panel', label: 'Settings' },
    { id: 'components', label: 'Programs and models' },
  ];

  // Narrow screens use the pill tab bar; clicking changes the hash, which
  // updates the view store.
  function onTab(e) {
    location.hash = '#' + e.detail;
    route();
  }

  // The button cycles auto, dark, light.
  $: themeLabel = 'Theme: ' + ($themeChoiceStore || 'auto');

  let runLabel = '';
  $: if ($status) runLabel = runningLabel($status);

  const dotClass = (s) => !s ? '' : s.ready ? 'ok-bg' : s.running ? 'wait-bg' : 'off-bg';
  const stateText = (s) => $statusError ? 'panel unavailable' : !s ? '—' : s.ready ? 'assistant ready' : s.running ? 'loading…' : 'stopped';

  onMount(() => {
    initRouting();
    loadSettings().then(() => route());
    refreshStatus();
    loadComponents();
    refreshLog();
    refreshHistory();
    // The same polling the panel has always used: status every 4 s,
    // components every 6 s, log every 4 s, history every 8 s.
    const timers = [
      setInterval(refreshStatus, 4000),
      setInterval(loadComponents, 6000),
      setInterval(refreshLog, 4000),
      setInterval(refreshHistory, 8000),
    ];
    // The Simple view needs the component list too, so it stays fresh on every view.
    // previous starts at null so the immediate subscription tick counts: a panel
    // opened straight at #components loads the user models like a later visit does.
    let previous = null;
    const unsub = view.subscribe((v) => {
      if (v === 'components' && previous !== 'components') {
        loadComponents();
        loadUserModels();
      }
      previous = v;
    });
    return () => { timers.forEach(clearInterval); unsub(); };
  });
</script>

<aside class="sidebar">
  <span class="brand">Local LLM Hub</span>
  <nav class="tabs" aria-label="Sections">
    <SidebarItem href="#simple" active={$view === 'simple'} class="min-h-11">Simple</SidebarItem>
    <SidebarItem href="#panel" active={$view === 'panel'} class="min-h-11">Settings</SidebarItem>
    <SidebarItem href="#components" active={$view === 'components'} class="min-h-11 max-[640px]:hidden">Programs and models</SidebarItem>
    <SidebarItem href="#components" active={$view === 'components'} class="min-h-11 min-[641px]:hidden">Models</SidebarItem>
  </nav>
  <div class="tabs-pill">
    <Tabs items={tabItems} value={$view} on:change={onTab} variant="pill" label="Sections" />
  </div>
  <div class="side-foot">
    <span class="runinfo">{runLabel}</span>
    <span class="state"><span class="dot {dotClass($status)}"></span><span>{stateText($status)}</span></span>
    <Button variant="quiet" on:click={cycleTheme} class="side-theme justify-start text-sm min-h-11" title="Light or dark theme">{themeLabel}</Button>
  </div>
</aside>

<main>
  {#if $view === 'simple'}
    <div class="view-simple"><Simple /></div>
  {:else if $view === 'panel'}
    <div class="view-panel"><Settings /></div>
  {:else}
    <div class="view-components"><ComponentsView /></div>
  {/if}
</main>

<ConfirmDialog />
<Toaster position="bottom-right" />
