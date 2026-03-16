/**
 * history.js - Run history page: list of runs with status, details modal.
 */

// ─── Init ─────────────────────────────────────────────────────────────────────

async function initHistory() {
  await loadHistory();
}

// ─── Load ─────────────────────────────────────────────────────────────────────

async function loadHistory() {
  const tbody = document.getElementById('history-body');
  if (!tbody) return;

  const filterSched = document.getElementById('history-filter-sched')?.value || '';
  const limitVal    = document.getElementById('history-limit')?.value || '100';

  try {
    const params = { limit: limitVal };
    if (filterSched) params.schedule_id = filterSched;
    const runs = await API.getHistory(params);

    if (!runs.length) {
      tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state">
        <div class="empty-state-title">No backup runs recorded.</div>
        <div class="empty-state-sub">Runs will appear here after schedules execute.</div>
      </div></td></tr>`;
      return;
    }

    tbody.innerHTML = runs.map(r => {
      const duration = r.finished_at && r.started_at
        ? ((new Date(r.finished_at + (r.finished_at.endsWith('Z') ? '' : 'Z')) -
            new Date(r.started_at  + (r.started_at.endsWith('Z')  ? '' : 'Z'))) / 1000).toFixed(1) + 's'
        : '—';
      return `<tr onclick="openRunDetail('${escHtml(r.id)}')" style="cursor:pointer">
        <td class="text-sm text-secondary">${formatDatetime(r.started_at)}</td>
        <td class="truncate">${escHtml(r.schedule_name || '—')}</td>
        <td>${statusBadge(r.status)}</td>
        <td class="text-sm">${escHtml(r.triggered_by || '—')}</td>
        <td class="text-sm text-secondary">${duration}</td>
        <td class="text-sm text-secondary">${formatBytes(r.bytes_copied)}</td>
        <td class="text-sm text-secondary truncate" title="${escHtml(r.error_msg || '')}">
          ${r.error_msg ? `<span class="text-sm" style="color:var(--color-error-text)">${escHtml(r.error_msg.slice(0, 60))}${r.error_msg.length > 60 ? '...' : ''}</span>` : '—'}
        </td>
      </tr>`;
    }).join('');
  } catch (e) {
    showToast('Failed to load run history: ' + e.message, 'error');
  }
}

// ─── Load schedule filter options ────────────────────────────────────────────

async function loadHistorySchedFilter() {
  const sel = document.getElementById('history-filter-sched');
  if (!sel) return;
  try {
    const schedules = await API.getSchedules();
    let html = '<option value="">All Schedules</option>';
    schedules.forEach(s => {
      html += `<option value="${escHtml(s.id)}">${escHtml(s.name)}</option>`;
    });
    sel.innerHTML = html;
  } catch { /* ignore */ }
}

// ─── Run detail modal ─────────────────────────────────────────────────────────

async function openRunDetail(runId) {
  try {
    const run = await API.getRun(runId);
    const modal = document.getElementById('run-detail-modal');
    const body = document.getElementById('run-detail-body');

    const dests = run.destinations || [];
    const destHtml = dests.map(d => `
      <tr>
        <td class="truncate text-sm" title="${escHtml(d.dest_path)}">${escHtml(d.dest_path)}</td>
        <td>${statusBadge(d.status)}</td>
        <td class="text-mono text-sm truncate">${escHtml(d.output_name || '—')}</td>
        <td class="text-sm text-secondary">${formatBytes(d.bytes_copied)}</td>
        <td class="text-sm" style="color:var(--color-error-text)">${escHtml(d.error_msg || '')}</td>
      </tr>
    `).join('');

    body.innerHTML = `
      <div class="form-row" style="margin-bottom:var(--gap-md)">
        <div class="form-group">
          <label>Schedule</label>
          <div class="text-sm">${escHtml(run.schedule_name)}</div>
        </div>
        <div class="form-group">
          <label>Status</label>
          <div>${statusBadge(run.status)}</div>
        </div>
        <div class="form-group">
          <label>Triggered By</label>
          <div class="text-sm">${escHtml(run.triggered_by)}</div>
        </div>
      </div>
      <div class="form-row" style="margin-bottom:var(--gap-md)">
        <div class="form-group">
          <label>Started</label>
          <div class="text-sm">${formatDatetime(run.started_at)}</div>
        </div>
        <div class="form-group">
          <label>Finished</label>
          <div class="text-sm">${formatDatetime(run.finished_at)}</div>
        </div>
        <div class="form-group">
          <label>Total Copied</label>
          <div class="text-sm">${formatBytes(run.bytes_copied)}</div>
        </div>
      </div>
      ${run.error_msg ? `<div class="alert alert-error" style="margin-bottom:var(--gap-md)">${escHtml(run.error_msg)}</div>` : ''}
      <div class="form-section-title">Destination Results</div>
      ${dests.length ? `
        <div class="table-wrapper">
          <table>
            <thead><tr>
              <th style="width:30%">Destination Path</th>
              <th style="width:10%">Status</th>
              <th style="width:30%">Output File</th>
              <th style="width:10%">Size</th>
              <th>Error</th>
            </tr></thead>
            <tbody>${destHtml}</tbody>
          </table>
        </div>
      ` : '<p class="text-muted text-sm">No destination results recorded.</p>'}
    `;

    modal.classList.add('open');
  } catch (e) {
    showToast('Failed to load run details: ' + e.message, 'error');
  }
}

function closeRunDetail() {
  document.getElementById('run-detail-modal').classList.remove('open');
}
