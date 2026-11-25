// All network calls of the panel live in this module, with the same endpoints
// the panel's front-end has always used. GET without a body, POST with JSON.
export async function api(path, body) {
  const opts = body === undefined
    ? {}
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const r = await fetch(path, opts);
  return r.json();
}

export const getStatus = () => api('/api/status');
export const getCatalog = () => api('/api/catalog');
export const getLog = () => api('/api/log');
export const getHistory = () => api('/api/history');
export const getComponents = () => api('/api/components');
export const getSettings = () => api('/api/settings');
export const getModelDirs = () => api('/api/model-dirs');
export const getUserModels = () => api('/api/models/user');
export const getDownloadState = (key) => api(`/api/download/${encodeURIComponent(key)}`);
export const getJob = (id) => api(`/api/jobs/${encodeURIComponent(id)}`);
export const getRecommend = (purpose) => api(`/api/recommend?purpose=${encodeURIComponent(purpose)}`);
export const getContextAdvice = (model, kvQuery) => api(`/api/context-advice?model=${encodeURIComponent(model)}${kvQuery}`);
export const getPreflight = (query) => api(`/api/preflight?${query}`);

export const startEngine = (body) => api('/api/start', body);
export const stopEngine = () => api('/api/stop', {});
export const clearCache = () => api('/api/cache/clear', {});
export const syncOpencode = (body) => api('/api/opencode/sync', body);
export const sendChat = (body) => api('/api/chat', body);
export const saveSettings = (body) => api('/api/settings', body);
export const startDownload = (key) => api('/api/download', { model: key });
export const cancelDownload = (key) => api(`/api/download/${encodeURIComponent(key)}/cancel`, {});
export const cancelJob = (id) => api(`/api/jobs/${encodeURIComponent(id)}/cancel`, {});
export const installComponent = (id) => api('/api/components/install', { id });
export const uninstallComponent = (id) => api('/api/components/uninstall', { id });
export const addModelDir = (path) => api('/api/model-dirs/add', { path });
export const removeModelDir = (path) => api('/api/model-dirs/remove', { path });
export const addUserModel = (repo) => api('/api/models/add', { repo });
export const removeUserModel = (key) => api('/api/models/remove', { key });

// Turn backend errors into plain instructions. The original text stays in the log.
const FRIENDLY = [
  [/another operation on this component/, () => 'This operation is already running. Wait for it to finish.'],
  [/port (\d+) is already in use/, (m) => `Port ${m[1]} is used by another program. Close it or restart your Mac.`],
  [/engine binary not found/, () => 'The model engine is not installed. Install it in step 1.'],
  [/model files not found/, () => 'The model is not downloaded. Download it in step 2.'],
  [/the engine is already running/, () => 'The assistant is already running.'],
  [/the model is still loading/, () => 'The model is still loading. Wait about a minute and try again.'],
  [/the engine is not running/, () => 'Start the assistant first (step 3).'],
  [/the engine is running: stop it first/, () => 'Stop the assistant first, then remove the program.'],
  [/the model is running: stop/, () => 'Stop the assistant first, then remove the model.'],
  [/the download is already running/, () => 'The download is already in progress.'],
  [/no such preset/, () => 'This mode does not exist. Choose one from the list.'],
];

export function friendly(msg) {
  if (!msg) return 'Something went wrong. Check the program log.';
  for (const [re, fn] of FRIENDLY) {
    const m = String(msg).match(re);
    if (m) return fn(m);
  }
  return msg;
}
