// Hash routing: #simple, #panel, #components, exactly as before. When there
// is no hash, the saved start view is used (localStorage "start_view").
import { writable } from 'svelte/store';

const valid = (h) => (h === 'panel' || h === 'components' ? h : 'simple');

export function currentView() {
  try {
    const wanted = location.hash.replace('#', '') || localStorage.getItem('start_view') || 'simple';
    return valid(wanted);
  } catch (e) {
    return 'simple';
  }
}

export const view = writable(currentView());

export function route() {
  view.set(currentView());
}

export function initRouting() {
  window.addEventListener('hashchange', route);
}
