/**
 * progress.js - Real-time backup progress monitoring.
 */

let _progressInterval = null;

async function initProgress() {
  loadActiveRuns();
  // Poll every 1.5 seconds while on this page
  if (_progressInterval) clearInterval(_progressInterval);
  _progressInterval = setInterval(loadActiveRuns, 1500);
}

// Clear interval when navigating away
window.addEventListener('hashchange', () => {
  if (window.location.hash !== '#progress' && _progressInterval) {
    clearInterval(_progressInterval);
    _progressInterval = null;
  }
});

async function loadActiveRuns() {
  const container = document.getElementById('progress-list');
  if (!container || _currentPage !== 'progress') {
    if (_progressInterval) clearInterval(_progressInterval);
    return;
  }

  try {
    const tasks = await API.getActiveRuns();

    if (!tasks.length) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-title">No active backups</div>
          <p>Running tasks will appear here automatically.</p>
        </div>`;
      return;
    }

    container.innerHTML = tasks.map(task => `
      <div class="panel progress-card" id="task-${task.run_id}">
        <div class="panel-header">
          <span class="panel-title">${escHtml(task.schedule_name)}</span>
          <button class="btn btn-ghost btn-sm" onclick="cancelBackup('${task.run_id}')" style="color:var(--color-error)">Cancel</button>
        </div>
        <div class="panel-body">
          <div class="flex justify-between text-sm mb-xs">
            <span class="text-secondary">${escHtml(task.step)}</span>
            <span class="text-bold">${task.progress}%</span>
          </div>
          <div class="progress-bar-wrap">
            <div class="progress-bar-fill" style="width: ${task.progress}%"></div>
          </div>
          <div class="text-xs text-muted mt-sm">
            Started: ${formatDatetime(task.started_at)}
          </div>
        </div>
      </div>
    `).join('');

  } catch (e) {
    console.error('Failed to load active runs:', e);
  }
}

async function cancelBackup(runId) {
  if (!confirm('Are you sure you want to cancel this backup? Partial files will be removed.')) return;
  try {
    await API.cancelRun(runId);
    showToast('Cancellation signal sent.', 'info');
    loadActiveRuns();
  } catch (e) {
    showToast('Failed to cancel: ' + e.message, 'error');
  }
}

// Add API method to API object in api.js context if not already there
// Assuming api.js is loaded first. 
// Note: Actual API object is extended in api.js edit.
