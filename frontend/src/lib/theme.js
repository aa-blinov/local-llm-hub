// Theme behaviour: light, dark, or follow the system. The monos-ui kit reads
// data-mode on the root element; themes.css does the colours. The choice is
// saved in localStorage under "theme"; the button cycles auto, dark, light.
import { writable } from 'svelte/store';

const systemDark = typeof matchMedia !== 'undefined' ? matchMedia('(prefers-color-scheme: dark)') : null;

export const themeChoice = writable('');

export function applyTheme(t) {
  themeChoice.set(t || '');
  const mode = (t || '') || (systemDark && systemDark.matches ? 'dark' : 'light');
  document.documentElement.dataset.mode = mode;
  try { localStorage.setItem('theme', t || ''); } catch (e) {}
}

let currentChoice = '';
themeChoice.subscribe((v) => { currentChoice = v; });

export function cycleTheme() {
  applyTheme(currentChoice === '' ? 'dark' : currentChoice === 'dark' ? 'light' : '');
}

// The saved choice is applied before this module loads, by the pre-paint
// script in index.html; the store here only follows it.
try { applyTheme(localStorage.getItem('theme') || ''); } catch (e) {}

// In auto mode the page follows the system when it changes.
if (systemDark) systemDark.addEventListener('change', () => {
  let choice = '';
  themeChoice.subscribe((v) => { choice = v; })();
  if (!choice) applyTheme('');
});
