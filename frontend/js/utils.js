/**
 * utils.js - Shared UI utilities.
 */

// ─── Toast Notifications ─────────────────────────────────────────────────────

function showToast(msg, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

// ─── Formatting ───────────────────────────────────────────────────────────────

function formatBytes(bytes) {
  if (!bytes || bytes < 0) return '—';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1024 ** 3) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  return (bytes / 1024 ** 3).toFixed(2) + ' GB';
}

function formatDatetime(iso) {
  if (!iso) return '—';
  try {
    // new Date() handles all ISO formats including +HH:MM timezone offsets
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
      + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}

function formatDateOnly(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return iso; }
}

function relativeTime(iso) {
  if (!iso) return '—';
  try {
    const now = Date.now();
    // Do NOT append 'Z' — APScheduler returns ISO with +HH:MM offset (e.g. +00:00)
    // Adding 'Z' after an existing offset makes an invalid date string -> NaN
    const ts = new Date(iso).getTime();
    if (isNaN(ts)) return iso;
    const diff = now - ts;
    if (diff < 0) {
      const s = Math.abs(diff) / 1000;
      if (s < 60)    return 'in <1 min';
      if (s < 3600)  return `in ${Math.round(s / 60)} min`;
      if (s < 86400) return `in ${Math.round(s / 3600)} hr`;
      return `in ${Math.round(s / 86400)} day(s)`;
    }
    const s = diff / 1000;
    if (s < 60)    return 'just now';
    if (s < 3600)  return `${Math.round(s / 60)} min ago`;
    if (s < 86400) return `${Math.round(s / 3600)} hr ago`;
    return `${Math.round(s / 86400)} day(s) ago`;
  } catch { return iso; }
}

function statusBadge(status, enabled = true) {
  if (!enabled) return `<span class="badge badge-disabled">Disabled</span>`;
  const map = {
    success: 'badge-success',
    error:   'badge-error',
    running: 'badge-running',
    idle:    'badge-idle',
    pending: 'badge-idle',
    cancelled: 'badge-disabled',
    missed: 'badge-error',
  };
  const cls = map[status] || 'badge-idle';
  let label = status || 'idle';
  if (status === 'missed') label = 'Missed';
  return `<span class="badge ${cls}">${escHtml(label)}</span>`;
}

function scheduleTypeName(type, config = {}) {
  switch (type) {
    case 'daily':    return `Daily at ${config.hour ?? 0}:${String(config.minute ?? 0).padStart(2,'0')}`;
    case 'weekly': {
      const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
      const d = days[config.day_of_week ?? 0] || '?';
      return `Weekly, ${d} at ${config.hour ?? 0}:${String(config.minute ?? 0).padStart(2,'0')}`;
    }
    case 'monthly':  return `Monthly on day ${config.day ?? 1}`;
    case 'interval': return `Every ${config.days ?? 1} day(s)`;
    case 'calendar': return `Calendar (${(config.dates || []).length} date(s))`;
    default: return type;
  }
}

function escHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ─── Navigation ───────────────────────────────────────────────────────────────

let _currentPage = null;

const PAGE_INIT = {
    dashboard:   () => initDashboard(),
    schedules:   () => initSchedules(),
    history:     () => initHistory(),
    credentials: () => initCredentials(),
    progress:    () => initProgress(),
};

function navigateTo(pageId) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const page = document.getElementById(`page-${pageId}`);
  if (page) page.classList.add('active');

  const navItem = document.querySelector(`.nav-item[data-page="${pageId}"]`);
  if (navItem) navItem.classList.add('active');

  _currentPage = pageId;

  // Trigger page-specific refresh
  if (window.PAGE_INIT && window.PAGE_INIT[pageId]) {
    window.PAGE_INIT[pageId]();
  }
}

// ─── Path Browser Component ───────────────────────────────────────────────────

class PathBrowser {
  constructor(inputEl, opts = {}) {
    this.input = inputEl;
    this.opts = opts; // { allowNewDir: true }
    this.currentPath = '';
    this._listEl = null;
    this._wrap = null;
    this._buildUI();
  }

  _buildUI() {
    this._wrap = document.createElement('div');
    this._wrap.className = 'path-browser';

    const nav = document.createElement('div');
    nav.className = 'path-input-row';
    nav.style.padding = '6px 8px';
    nav.style.background = 'var(--color-bg-2)';
    nav.style.borderBottom = '1px solid var(--color-border)';

    const upBtn = document.createElement('button');
    upBtn.className = 'btn btn-ghost btn-sm';
    upBtn.textContent = 'Up';
    upBtn.onclick = () => {
      const parts = this.currentPath.replace(/[/\\]+$/, '').split(/[/\\]/);
      parts.pop();
      const parent = parts.join('\\') || '';
      this.load(parent);
    };

    const refreshBtn = document.createElement('button');
    refreshBtn.className = 'btn btn-ghost btn-sm';
    refreshBtn.textContent = 'Refresh';
    refreshBtn.onclick = () => this.load(this.currentPath);

    nav.appendChild(upBtn);
    nav.appendChild(refreshBtn);
    this._wrap.appendChild(nav);

    this._listEl = document.createElement('div');
    this._wrap.appendChild(this._listEl);

    const parent = this.input.parentNode;
    this.input.insertAdjacentElement('afterend', this._wrap);

    this.load('');
  }

  async load(path) {
    this.currentPath = path;
    this._listEl.innerHTML = '<div style="padding:8px 16px;color:var(--color-text-muted)">Loading...</div>';

    try {
      const entries = await API.browse(path);
      if (!entries || !Array.isArray(entries)) {
        throw new Error('Invalid response');
      }
      this._render(entries);
    } catch (e) {
      this._listEl.innerHTML = `<div style="padding:8px 16px;color:var(--color-error-text)">Error: ${escHtml(e.message)}</div>`;
    }
  }

  _render(entries) {
    this._listEl.innerHTML = '';
    if (!entries.length) {
      this._listEl.innerHTML = '<div style="padding:8px 16px;color:var(--color-text-muted)">Empty directory.</div>';
      return;
    }
    entries.forEach(entry => {
      const row = document.createElement('div');
      row.className = 'path-browser-entry' + (entry.is_dir ? ' pb-dir' : '');
      row.innerHTML = `<span class="pb-icon">${entry.is_dir ? '[D]' : '[F]'}</span><span class="truncate">${escHtml(entry.name)}</span>`;
      row.onclick = () => {
        if (entry.is_dir) {
          this.input.value = entry.path;
          this.load(entry.path);
        } else {
          this.input.value = entry.path;
        }
      };
      this._listEl.appendChild(row);
    });
  }

  destroy() {
    if (this._wrap) this._wrap.remove();
  }
}

// ─── Name preview helper ──────────────────────────────────────────────────────

async function refreshNamePreview(templateInput, extInput, nameInput, previewEl) {
  try {
    const result = await API.previewName({
      template: templateInput.value || '{name}_{date}_{id}.{ext}',
      ext: extInput.value || 'bak',
      name: nameInput ? nameInput.value : 'backup',
    });
    previewEl.textContent = result.preview || '';
  } catch (e) {
    previewEl.textContent = 'Preview error';
  }
}

// ─── Schedule config form helpers ─────────────────────────────────────────────

function buildScheduleFields(container, scheduleType, config = {}) {
  container.innerHTML = '';

  const DOW_LABELS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

  function mkGroup(label, inputHtml, hint = '') {
    return `<div class="form-group">
      <label>${label}</label>
      ${inputHtml}
      ${hint ? `<span class="form-hint">${hint}</span>` : ''}
    </div>`;
  }

  switch (scheduleType) {
    case 'daily':
      container.innerHTML = `<div class="form-row">
        ${mkGroup('Time (24h)', `<div class="flex flex-gap-sm align-center">
          <input type="number" id="sc-hour" min="0" max="23" value="${config.hour ?? 3}" style="width:80px">
          <span class="text-muted">:</span>
          <input type="number" id="sc-minute" min="0" max="59" value="${config.minute ?? 0}" style="width:80px">
        </div>`, 'HH : MM')}
      </div>`;
      break;

    case 'weekly':
      container.innerHTML = `<div class="form-row">
        ${mkGroup('Day of week', `<select id="sc-dow">${DOW_LABELS.map((d,i)=>
          `<option value="${i}" ${(config.day_of_week ?? 0) == i ? 'selected':''}>${d}</option>`).join('')}</select>`)}
        ${mkGroup('Time (24h)', `<div class="flex flex-gap-sm align-center">
          <input type="number" id="sc-hour" min="0" max="23" value="${config.hour ?? 3}" style="width:80px">
          <span class="text-muted">:</span>
          <input type="number" id="sc-minute" min="0" max="59" value="${config.minute ?? 0}" style="width:80px">
        </div>`, 'HH : MM')}
      </div>`;
      break;

    case 'monthly':
      container.innerHTML = `<div class="form-row">
        ${mkGroup('Day of month', `<input type="number" id="sc-day" min="1" max="31" value="${config.day ?? 1}">`)}
        ${mkGroup('Time (24h)', `<div class="flex flex-gap-sm align-center">
          <input type="number" id="sc-hour" min="0" max="23" value="${config.hour ?? 3}" style="width:80px">
          <span class="text-muted">:</span>
          <input type="number" id="sc-minute" min="0" max="59" value="${config.minute ?? 0}" style="width:80px">
        </div>`, 'HH : MM')}
      </div>`;
      break;

    case 'interval':
      container.innerHTML = `<div class="form-row">
        ${mkGroup('Every N days', `<input type="number" id="sc-days" min="1" max="365" value="${config.days ?? 7}">`, 'Minimum 1 day')}
      </div>`;
      break;

    case 'calendar':
      const existingDates = (config.dates || []).join('\n');
      container.innerHTML = `<div class="form-group full-width">
        <label>Run dates <span class="text-muted">(one per line, format: YYYY-MM-DD HH:MM)</span></label>
        <textarea id="sc-dates" style="min-height:120px" placeholder="2026-04-01 02:00&#10;2026-05-01 02:00">${escHtml(existingDates)}</textarea>
        <span class="form-hint">Dates in UTC. Past dates will be skipped.</span>
      </div>`;
      break;

    default:
      container.innerHTML = `<p class="text-muted text-sm">Select a schedule type above.</p>`;
  }
}

function readScheduleConfig(scheduleType) {
  const config = {};
  const hour = document.getElementById('sc-hour');
  const minute = document.getElementById('sc-minute');
  if (hour) config.hour = parseInt(hour.value) || 0;
  if (minute) config.minute = parseInt(minute.value) || 0;

  switch (scheduleType) {
    case 'weekly': {
      const dow = document.getElementById('sc-dow');
      if (dow) config.day_of_week = parseInt(dow.value);
      break;
    }
    case 'monthly': {
      const day = document.getElementById('sc-day');
      if (day) config.day = parseInt(day.value) || 1;
      break;
    }
    case 'interval': {
      const days = document.getElementById('sc-days');
      if (days) config.days = parseInt(days.value) || 1;
      break;
    }
    case 'calendar': {
      const ta = document.getElementById('sc-dates');
      if (ta) {
        config.dates = ta.value.split('\n')
          .map(s => s.trim()).filter(Boolean);
      }
      break;
    }
  }
  return config;
}
