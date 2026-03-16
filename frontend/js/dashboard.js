/**
 * dashboard.js - Dashboard page: stats, schedule list, monthly activity calendar.
 *
 * Calendar state is tracked as (_calYear, _calMonth) so the user can navigate
 * to any past or future month using the prev/next buttons.
 */

// ─── Calendar state ───────────────────────────────────────────────────────────

let _calYear  = new Date().getFullYear();
let _calMonth = new Date().getMonth(); // 0-indexed
let _calData  = [];   // cached API calendar data (60-day window, extended on demand)

// ─── Dashboard Init ───────────────────────────────────────────────────────────

async function initDashboard() {
  _calYear  = new Date().getFullYear();
  _calMonth = new Date().getMonth();
  await Promise.all([loadStats(), loadDashboardSchedules()]);
}

// ─── Stats Cards ──────────────────────────────────────────────────────────────

async function loadStats() {
  try {
    const stats = await API.getStats();

    _el('stat-total').textContent    = stats.total_schedules   ?? 0;
    _el('stat-enabled').textContent  = stats.enabled_schedules ?? 0;
    _el('stat-runs').textContent     = stats.total_runs        ?? 0;
    _el('stat-success').textContent  = stats.success_runs      ?? 0;
    _el('stat-error').textContent    = stats.error_runs        ?? 0;
    _el('stat-running').textContent  = stats.running_now       ?? 0;
    _el('stat-missed').textContent   = stats.missed_unrecovered ?? 0;

    _calData = stats.calendar || [];
    renderCalendar();
  } catch (e) {
    showToast('Failed to load stats: ' + e.message, 'error');
  }
}

function _el(id) { return document.getElementById(id); }

// ─── Calendar navigation ──────────────────────────────────────────────────────

function calPrevMonth() {
  _calMonth--;
  if (_calMonth < 0) { _calMonth = 11; _calYear--; }
  renderCalendar();
}

function calNextMonth() {
  _calMonth++;
  if (_calMonth > 11) { _calMonth = 0; _calYear++; }
  renderCalendar();
}

function calGoToday() {
  _calYear  = new Date().getFullYear();
  _calMonth = new Date().getMonth();
  renderCalendar();
}

// ─── Activity Calendar ────────────────────────────────────────────────────────

function renderCalendar() {
  const container = _el('calendar-grid');
  const monthLabel = _el('calendar-month');
  const navPrev    = _el('cal-nav-prev');
  const navNext    = _el('cal-nav-next');
  if (!container) return;

  const MONTH_NAMES = [
    'January','February','March','April','May','June',
    'July','August','September','October','November','December'
  ];
  const now   = new Date();
  const today = now.toISOString().slice(0, 10);
  const isCurrentMonth = (_calYear === now.getFullYear() && _calMonth === now.getMonth());

  if (monthLabel) monthLabel.textContent = `${MONTH_NAMES[_calMonth]} ${_calYear}`;
  if (navNext) navNext.disabled = isCurrentMonth && _calYear >= now.getFullYear();

  // Build lookup: date-string -> run record
  const byDate = {};
  _calData.forEach(r => { byDate[r.run_date] = r; });

  // Day-of-week header (Mon-start)
  const DAY_LABELS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  let html = DAY_LABELS.map(d =>
    `<div class="cal-weekday" role="columnheader">${d}</div>`
  ).join('');

  // Leading blank cells
  const firstDay = new Date(_calYear, _calMonth, 1);
  const startOffset = (firstDay.getDay() + 6) % 7; // Mon=0
  html += Array(startOffset).fill('<div class="cal-empty"></div>').join('');

  // Day cells
  const daysInMonth = new Date(_calYear, _calMonth + 1, 0).getDate();
  for (let d = 1; d <= daysInMonth; d++) {
    const iso = `${_calYear}-${String(_calMonth + 1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const rec = byDate[iso];
    let cls = 'cal-day';
    let titleText = '';
    let badge = '';

    if (iso === today) cls += ' today';

    if (rec) {
      const hasError = rec.success_cnt < rec.cnt;
      cls += hasError ? ' has-error' : ' has-run';
      titleText = `${rec.cnt} run(s)` + (hasError ? `, ${rec.cnt - rec.success_cnt} error(s)` : '');
      badge = `<span class="cal-badge">${rec.cnt}</span>`;
    }

    html += `<div class="${cls}" role="gridcell" aria-label="${iso}${titleText ? ': ' + titleText : ''}" title="${escHtml(titleText)}">
      <span class="cal-num">${d}</span>${badge}
    </div>`;
  }

  container.innerHTML = html;
}

// ─── Recent Schedules Summary ─────────────────────────────────────────────────

async function loadDashboardSchedules() {
  const tbody = _el('dash-sched-body');
  if (!tbody) return;

  try {
    const [schedules, history] = await Promise.all([
      API.getSchedules(),
      API.getHistory({ limit: 20 }),
    ]);

    // Map last run per schedule
    const lastRunMap = {};
    history.forEach(run => {
      if (!lastRunMap[run.schedule_id]) lastRunMap[run.schedule_id] = run;
    });

    if (!schedules.length) {
      tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state">
        <div class="empty-state-title">No backup schedules configured.</div>
        <div class="empty-state-sub">Go to Schedules to create your first backup.</div>
      </div></td></tr>`;
      return;
    }

    tbody.innerHTML = schedules.map(s => `<tr>
      <td class="truncate" title="${escHtml(s.name)}">${escHtml(s.name)}</td>
      <td>${statusBadge(s.status, s.enabled)}</td>
      <td class="text-sm text-secondary truncate">${escHtml(scheduleTypeName(s.schedule_type, s.schedule_config))}</td>
      <td class="text-sm text-secondary">${relativeTime(s.last_run)}</td>
      <td class="text-sm text-secondary">${relativeTime(s.next_run)}</td>
      <td>
        <button class="btn btn-secondary btn-sm" onclick="quickRunSchedule('${escHtml(s.id)}')">Run Now</button>
      </td>
    </tr>`).join('');
  } catch (e) {
    showToast('Failed to load schedules: ' + e.message, 'error');
  }
}

async function quickRunSchedule(id) {
  try {
    await API.runNow(id);
    showToast('Backup started.', 'success');
    setTimeout(initDashboard, 1500);
  } catch (e) {
    showToast('Failed to start backup: ' + e.message, 'error');
  }
}
