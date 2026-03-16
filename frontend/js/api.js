/**
 * api.js - Thin wrapper around the Backupman REST API.
 * All methods return parsed JSON or throw an Error.
 */

const API_BASE = '';

async function apiFetch(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(API_BASE + path, opts);
  const data = await res.json();
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

const API = {
  // --- Schedules ---
  getSchedules:    ()          => apiFetch('GET',    '/api/schedules'),
  getSchedule:     (id)        => apiFetch('GET',    `/api/schedules/${id}`),
  createSchedule:  (data)      => apiFetch('POST',   '/api/schedules', data),
  updateSchedule:  (id, data)  => apiFetch('PUT',    `/api/schedules/${id}`, data),
  deleteSchedule:  (id)        => apiFetch('DELETE', `/api/schedules/${id}`),
  toggleSchedule:  (id)        => apiFetch('POST',   `/api/schedules/${id}/toggle`),
  runNow:          (id)        => apiFetch('POST',   `/api/schedules/${id}/run`),

  // --- History ---
  getHistory:      (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch('GET', `/api/history${qs ? '?' + qs : ''}`);
  },
  getRun:          (id)        => apiFetch('GET',    `/api/history/${id}`),

  // --- Credentials ---
  getCredentials:  ()          => apiFetch('GET',    '/api/credentials'),
  createCredential:(data)      => apiFetch('POST',   '/api/credentials', data),
  deleteCredential:(id)        => apiFetch('DELETE', `/api/credentials/${id}`),

  // --- Utilities ---
  validatePath:    (data)      => apiFetch('POST',   '/api/validate-path', data),
  previewName:     (data)      => apiFetch('POST',   '/api/preview-name', data),
  getStats:        ()          => apiFetch('GET',    '/api/stats'),
  browse:          (path)      => {
    const qs = path ? `?path=${encodeURIComponent(path)}` : '';
    return apiFetch('GET', `/api/browse${qs}`);
  },
  // Opens a native OS folder picker dialog (backend uses PowerShell on Windows)
  browseDialog:    ()          => apiFetch('GET',    '/api/browse-dialog'),

  // --- Active Runs ---
  getActiveRuns:   ()          => apiFetch('GET',    '/api/active-runs'),
  cancelRun:       (id)        => apiFetch('POST',   `/api/active-runs/${id}/cancel`),
};


