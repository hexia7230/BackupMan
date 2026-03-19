/**
 * schedules.js - Schedules page: list, create, edit, delete, run.
 */

// ─── State ────────────────────────────────────────────────────────────────────

let _editingScheduleId = null;
let _destCounter = 0;
let _credentials = [];

// ─── Init ─────────────────────────────────────────────────────────────────────

async function initSchedules() {
  await loadSchedulesList();
}

// ─── List ───────────────────────────────────────────────────────────────────

async function loadSchedulesList() {
  const tbody = document.getElementById('sched-table-body');
  if (!tbody) return;

  try {
    const schedules = await API.getSchedules();

    if (!schedules.length) {
      tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state">
        <div class="empty-state-title">No schedules defined.</div>
        <div class="empty-state-sub">Click "New Schedule" to get started.</div>
      </div></td></tr>`;
      return;
    }

    tbody.innerHTML = schedules.map(s => {
      const destCount = (s.destinations || []).length;
      return `<tr>
        <td class="truncate" title="${escHtml(s.name)}">${escHtml(s.name)}</td>
        <td>${statusBadge(s.status, s.enabled)}</td>
        <td class="text-sm text-secondary truncate" title="${escHtml(s.source_path)}">
          <span class="path-text">${escHtml(s.source_path)}</span>
        </td>
        <td class="text-sm text-secondary">${escHtml(scheduleTypeName(s.schedule_type, s.schedule_config))}</td>
        <td class="text-sm text-secondary">${destCount} destination${destCount !== 1 ? 's' : ''}</td>
        <td class="text-sm text-secondary">${relativeTime(s.next_run)}</td>
        <td>
          <div class="flex flex-gap-sm align-center">
            <button class="btn btn-secondary btn-sm" onclick="openEditModal('${escHtml(s.id)}')">Edit</button>
            <button class="btn btn-ghost btn-sm" onclick="schedRunNow('${escHtml(s.id)}')">Run</button>
            <button class="btn btn-ghost btn-sm" onclick="schedToggle('${escHtml(s.id)}', ${s.enabled})">${s.enabled ? 'Disable' : 'Enable'}</button>
            <button class="btn btn-danger btn-sm" onclick="schedDelete('${escHtml(s.id)}')">Delete</button>
          </div>
        </td>
      </tr>`;
    }).join('');
  } catch (e) {
    showToast('Failed to load schedules: ' + e.message, 'error');
  }
}

// ─── Quick actions ────────────────────────────────────────────────────────────

async function schedRunNow(id) {
  if (!confirm('Start backup now?')) return;
  try {
    await API.runNow(id);
    showToast('Backup started.', 'success');
    setTimeout(loadSchedulesList, 1200);
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

async function schedToggle(id, currentEnabled) {
  try {
    await API.toggleSchedule(id);
    showToast(currentEnabled ? 'Schedule disabled.' : 'Schedule enabled.', 'success');
    loadSchedulesList();
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

async function schedDelete(id) {
  if (!confirm('Delete this schedule? Run history will also be removed.')) return;
  try {
    await API.deleteSchedule(id);
    showToast('Schedule deleted.', 'success');
    loadSchedulesList();
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

// ─── Modal Open ───────────────────────────────────────────────────────────────

async function openNewModal() {
  _editingScheduleId = null;
  _destCounter = 0;

  // Open modal immediately so the user sees instant feedback
  document.getElementById('modal-title').textContent = 'New Schedule';
  document.getElementById('sched-name').value = '';
  document.getElementById('sched-source').value = '';
  document.getElementById('sched-delete-old').checked = false;
  document.getElementById('sched-enabled').checked = true;
  document.getElementById('dest-list').innerHTML = '';
  document.getElementById('sc-config-fields').innerHTML =
    '<p class="text-muted text-sm">Select a schedule type above.</p>';
  document.getElementById('sched-type').value = 'daily';
  onScheduleTypeChange();
  // Hide Run Now and Delete buttons — no schedule to run/delete yet
  document.getElementById('btn-modal-run-now').style.display = 'none';
  document.getElementById('btn-modal-delete-sched').style.display = 'none';
  document.getElementById('sched-modal').classList.add('open');
  switchSchedTab('basic', document.querySelector('#sched-modal .tab-btn'));

  // Load credentials in background
  try {
    _credentials = await API.getCredentials();
  } catch (e) {
    _credentials = [];
    showToast('Could not load credentials: ' + e.message, 'warning');
  }
  document.getElementById('sched-source-cred').innerHTML = credOptions();

  addDestinationCard();
}

async function openEditModal(id) {
  _editingScheduleId = id;
  _destCounter = 0;

  // Show modal skeleton immediately
  document.getElementById('modal-title').textContent = 'Edit Schedule';
  document.getElementById('dest-list').innerHTML =
    '<p class="text-muted text-sm" style="padding:var(--gap-md)">Loading...</p>';
  // Show Run Now and Delete buttons for existing schedules
  const runBtn = document.getElementById('btn-modal-run-now');
  runBtn.style.display = '';
  runBtn.disabled = false;
  runBtn.textContent = 'Run Now';
  
  const delBtn = document.getElementById('btn-modal-delete-sched');
  delBtn.style.display = '';
  
  document.getElementById('sched-modal').classList.add('open');

  try {
    const [s, creds] = await Promise.all([API.getSchedule(id), API.getCredentials()]);
    _credentials = creds;

    document.getElementById('sched-name').value = s.name;
    document.getElementById('sched-source').value = s.source_path;
    document.getElementById('sched-source-cred').innerHTML = credOptions(s.source_cred_id);
    document.getElementById('sched-delete-old').checked = !!s.delete_old;
    document.getElementById('sched-enabled').checked = !!s.enabled;

    document.getElementById('sched-type').value = s.schedule_type;
    onScheduleTypeChange(s.schedule_config);

    document.getElementById('dest-list').innerHTML = '';
    (s.destinations || []).forEach(d => addDestinationCard(d));
    if (!s.destinations || !s.destinations.length) addDestinationCard();
  } catch (e) {
    showToast('Failed to load schedule: ' + e.message, 'error');
    closeSchedModal();
  }
}

function closeSchedModal() {
  document.getElementById('sched-modal').classList.remove('open');
}

// ─── Schedule type change ─────────────────────────────────────────────────────

function onScheduleTypeChange(existingConfig = null) {
  const type = document.getElementById('sched-type').value;
  const container = document.getElementById('sc-config-fields');
  buildScheduleFields(container, type, existingConfig || {});
}

// ─── Credentials options helper ───────────────────────────────────────────────

function credOptions(selectedId = null) {
  let html = `<option value="">None (local path)</option>`;
  _credentials.forEach(c => {
    const sel = c.id === selectedId ? 'selected' : '';
    html += `<option value="${escHtml(c.id)}" ${sel}>${escHtml(c.label)} (${escHtml(c.username)}@${escHtml(c.server)})</option>`;
  });
  return html;
}

// ─── Destination Cards ────────────────────────────────────────────────────────

function addDestinationCard(existing = null) {
  _destCounter++;
  const n = _destCounter;
  const d = existing || {};

  const card = document.createElement('div');
  card.className = 'dest-card';
  card.id = `dest-card-${n}`;

  card.innerHTML = `
    <div class="dest-card-header">
      <span class="dest-card-num">Destination ${n}</span>
      <button class="btn btn-danger btn-sm" type="button" onclick="removeDestCard(${n})">Remove</button>
    </div>
    <div class="form-row">
      <div class="form-group full-width">
        <label>Destination Path <span class="required">*</span></label>
        <div class="path-input-row">
          <input type="text" id="dest-path-${n}" placeholder="C:\\Backups or \\\\server\\share\\backups"
                 value="${escHtml(d.dest_path || '')}" oninput="refreshDestPreview(${n})">
          <button class="btn btn-secondary btn-sm" type="button" onclick="browseDestPath(${n})">Browse</button>
        </div>
        <div id="dest-browser-wrap-${n}"></div>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Network Credential</label>
        <select id="dest-cred-${n}">${credOptions(d.dest_cred_id)}</select>
        <span class="form-hint">Required only for network paths</span>
      </div>
    </div>

    <div class="form-section-title mt-sm" style="margin-top:14px">Output File Naming</div>
    <div class="form-row">
      <div class="form-group full-width">
        <label>Name Template</label>
        <input type="text" id="dest-tpl-${n}" placeholder="{name}_{date}_{id}.{ext}"
               value="${escHtml(d.name_template !== undefined ? d.name_template : '')}"
               oninput="refreshDestPreview(${n})">
        <span class="form-hint">
          Placeholders: {name} {date} {datetime} {year} {month} {day} {time} {id} {seq} {source_name}
        </span>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Custom label for {name}</label>
        <input type="text" id="dest-name-label-${n}" placeholder="backup"
               value="${escHtml(d._name_label || '')}" oninput="refreshDestPreview(${n})">
      </div>
    </div>
    <div class="toggle-row" style="margin-bottom:var(--gap-sm);">
      <input type="checkbox" id="dest-zip-${n}" ${d.compress_zip ? 'checked' : ''} onchange="refreshDestPreview(${n})">
      <label for="dest-zip-${n}">Compress to Zip file</label>
    </div>
    <div class="form-group full-width">
      <label style="font-size:11px;color:var(--color-text-muted)">Preview</label>
      <div class="preview-box" id="dest-preview-${n}">—</div>
    </div>
  `;

  document.getElementById('dest-list').appendChild(card);
  refreshDestPreview(n);
}

function removeDestCard(n) {
  const el = document.getElementById(`dest-card-${n}`);
  if (el) el.remove();
}

let _previewTimers = {};

function refreshDestPreview(n) {
  clearTimeout(_previewTimers[n]);
  _previewTimers[n] = setTimeout(async () => {
    const tplEl = document.getElementById(`dest-tpl-${n}`);
    const nameEl = document.getElementById(`dest-name-label-${n}`);
    const prevEl = document.getElementById(`dest-preview-${n}`);
    if (!tplEl || !prevEl) return;

    try {
      // Allow empty string as a valid template value
      const template = tplEl.value !== undefined ? tplEl.value : '{name}_{date}_{id}.{ext}';
      
      // Get source name from the source path input for better preview
      let sourcePath = document.getElementById('sched-source')?.value || '';
      // Remove trailing slash if present
      sourcePath = sourcePath.replace(/[\\/]+$/, '');
      const sourceName = sourcePath ? sourcePath.split(/[\\/]/).pop() : 'source';

      const result = await API.previewName({
        template: template,
        ext: '',
        name: nameEl ? nameEl.value || 'backup' : 'backup',
        source_name: sourceName
      });
      let previewText = '';
      if (result.preview && result.preview.trim()) {
        previewText = result.preview;
      } else if (!template.trim()) {
        previewText = sourceName || 'Original Filename';
      } else {
        previewText = '—';
      }
      
      const isZip = document.getElementById(`dest-zip-${n}`)?.checked;
      if (isZip && previewText !== '—' && !previewText.includes('.')) {
        previewText += '.zip';
      }
      prevEl.textContent = previewText;
    } catch (e) {
      prevEl.textContent = 'Preview error';
    }
  }, 400);
}

// ─── Native OS folder dialog ──────────────────────────────────────────────────

// Called by the source Browse button in index.html
async function browseSourcePath() {
  const input = document.getElementById('sched-source');
  const msgEl = document.getElementById('source-validate-msg');
  msgEl.textContent = 'Opening folder picker...';
  msgEl.style.color = '';
  try {
    const r = await API.browseDialog();
    if (r.path) {
      input.value = r.path;
    }
    msgEl.textContent = '';
  } catch (e) {
    msgEl.textContent = 'Could not open dialog: ' + e.message;
    msgEl.style.color = 'var(--color-error-text)';
  }
}

// Called by each destination card Browse button
async function browseDestPath(n) {
  const input = document.getElementById(`dest-path-${n}`);
  if (!input) return;
  try {
    const r = await API.browseDialog();
    if (r.path) {
      input.value = r.path;
      refreshDestPreview(n);
    }
  } catch (e) {
    showToast('Could not open folder picker: ' + e.message, 'error');
  }
}

// ─── Run Now from Edit modal ──────────────────────────────────────────────────

async function runNowFromModal() {
  if (!_editingScheduleId) return;
  const btn = document.getElementById('btn-modal-run-now');
  btn.disabled = true;
  btn.textContent = 'Starting...';
  try {
    await API.runNow(_editingScheduleId);
    showToast('Backup started.', 'success');
  } catch (e) {
    showToast('Failed: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Run Now';
  }
}

async function schedDeleteFromModal() {
  if (!_editingScheduleId) return;
  const id = _editingScheduleId;
  if (!confirm('Delete this schedule? Run history will also be removed.')) return;
  try {
    await API.deleteSchedule(id);
    showToast('Schedule deleted.', 'success');
    closeSchedModal();
    loadSchedulesList();
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
}

// ─── Collect dest data ────────────────────────────────────────────────────────

function collectDestinations() {
  const cards = document.querySelectorAll('.dest-card');
  return Array.from(cards).map(card => {
    const n = card.id.replace('dest-card-', '');
    const tplVal = document.getElementById(`dest-tpl-${n}`)?.value;
    return {
      dest_path:     document.getElementById(`dest-path-${n}`)?.value || '',
      dest_type:     document.getElementById(`dest-path-${n}`)?.value?.startsWith('\\\\') ? 'network' : 'local',
      dest_cred_id:  document.getElementById(`dest-cred-${n}`)?.value || null,
      name_template: tplVal !== undefined ? tplVal : '',
      ext:           '',
      compress_zip:  document.getElementById(`dest-zip-${n}`)?.checked ? 1 : 0
    };
  });
}

// ─── Save ─────────────────────────────────────────────────────────────────────

async function saveSchedule() {
  const name          = document.getElementById('sched-name').value.trim();
  const sourcePath    = document.getElementById('sched-source').value.trim();
  const sourceCredId  = document.getElementById('sched-source-cred').value || null;
  const deleteOld     = document.getElementById('sched-delete-old').checked;
  const enabled       = document.getElementById('sched-enabled').checked;
  const schedType     = document.getElementById('sched-type').value;
  const schedConfig   = readScheduleConfig(schedType);
  const destinations  = collectDestinations();

  if (!name) { showToast('Schedule name is required.', 'error'); return; }
  if (!sourcePath) { showToast('Source path is required.', 'error'); return; }
  if (!destinations.length || !destinations[0].dest_path) {
    showToast('At least one destination is required.', 'error'); return;
  }

  const payload = {
    name,
    source_path: sourcePath,
    source_type: sourcePath.startsWith('\\\\') ? 'network' : 'local',
    source_cred_id: sourceCredId,
    delete_old: deleteOld,
    enabled,
    schedule_type: schedType,
    schedule_config: schedConfig,
    destinations,
  };

  const saveBtn = document.getElementById('btn-save-sched');
  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving...';

  try {
    if (_editingScheduleId) {
      await API.updateSchedule(_editingScheduleId, payload);
      showToast('Schedule updated.', 'success');
    } else {
      await API.createSchedule(payload);
      showToast('Schedule created.', 'success');
    }
    closeSchedModal();
    loadSchedulesList();
  } catch (e) {
    showToast('Save failed: ' + e.message, 'error');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save';
  }
}

