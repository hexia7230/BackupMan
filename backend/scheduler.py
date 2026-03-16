"""
scheduler.py - APScheduler-based backup scheduler.

Responsibilities:
  - Add/remove/update jobs when schedules change.
  - On app startup, detect missed runs and re-execute them.
  - Translate schedule_type + schedule_config into APScheduler triggers.
"""
import json
import logging
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from . import db, backup_engine

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone='UTC')
_lock = threading.Lock()


def _job_id(schedule_id: str) -> str:
    return f"backup_{schedule_id}"


def _make_trigger(schedule_type: str, config: dict):
    """
    Convert schedule_type and config dict into an APScheduler trigger.

    schedule_type values and their expected config keys:
      'daily'    - hour, minute (int)
      'weekly'   - day_of_week (0=Mon..6=Sun), hour, minute
      'monthly'  - day (1-31), hour, minute
      'interval' - days (int), hour, minute (time of first fire relative)
      'calendar' - dates (list of 'YYYY-MM-DD HH:MM' strings)
    """
    hour = config.get('hour', 0)
    minute = config.get('minute', 0)

    if schedule_type == 'daily':
        return CronTrigger(hour=hour, minute=minute, timezone='UTC')

    elif schedule_type == 'weekly':
        dow = config.get('day_of_week', 0)  # 0=Mon, 6=Sun
        dow_str = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][dow % 7]
        return CronTrigger(day_of_week=dow_str, hour=hour, minute=minute, timezone='UTC')

    elif schedule_type == 'monthly':
        day = config.get('day', 1)
        return CronTrigger(day=day, hour=hour, minute=minute, timezone='UTC')

    elif schedule_type == 'interval':
        days = max(1, config.get('days', 1))
        return IntervalTrigger(days=days)

    elif schedule_type == 'calendar':
        # For calendar, we add individual date triggers.
        # Only the next upcoming date is used here; remaining are re-added after run.
        dates = config.get('dates', [])
        now = datetime.utcnow()
        future = [d for d in dates if datetime.fromisoformat(d) > now]
        if not future:
            return None
        next_dt = datetime.fromisoformat(sorted(future)[0])
        return DateTrigger(run_date=next_dt, timezone='UTC')

    return None


def _execute_schedule(schedule_id: str):
    """Job function called by APScheduler."""
    logger.info(f"Scheduler fired for schedule {schedule_id}")
    try:
        backup_engine.run_backup(schedule_id, triggered_by='scheduler')
    except Exception as e:
        logger.error(f"Backup failed for schedule {schedule_id}: {e}")


def add_or_update_job(schedule_id: str):
    """Add or update the APScheduler job for a schedule."""
    conn = db.get_conn()
    sched = conn.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone()
    if not sched:
        return

    sched = dict(sched)
    if not sched['enabled']:
        remove_job(schedule_id)
        return

    config = json.loads(sched.get('schedule_config') or '{}')
    trigger = _make_trigger(sched['schedule_type'], config)
    if trigger is None:
        logger.warning(f"No valid trigger for schedule {schedule_id}")
        return

    jid = _job_id(schedule_id)
    with _lock:
        if _scheduler.get_job(jid):
            _scheduler.remove_job(jid)
        _scheduler.add_job(
            _execute_schedule,
            trigger=trigger,
            id=jid,
            args=[schedule_id],
            replace_existing=True,
            misfire_grace_time=None,  # We handle missed runs ourselves
        )
    logger.info(f"Job added/updated: {jid}")

    # Update next_run in DB
    job = _scheduler.get_job(jid)
    if job and job.next_run_time:
        conn.execute(
            "UPDATE schedules SET next_run=? WHERE id=?",
            (job.next_run_time.isoformat(), schedule_id)
        )
        conn.commit()


def remove_job(schedule_id: str):
    """Remove an APScheduler job."""
    jid = _job_id(schedule_id)
    with _lock:
        if _scheduler.get_job(jid):
            _scheduler.remove_job(jid)
    logger.info(f"Job removed: {jid}")


def recover_missed_runs():
    """
    On startup, find schedules whose next_run was in the past
    and whose last completed run was before that, then execute them.
    """
    conn = db.get_conn()
    now = datetime.utcnow().isoformat()

    # Schedules that are enabled and have a next_run in the past
    overdues = conn.execute("""
        SELECT s.id, s.name, s.next_run, s.last_run
        FROM schedules s
        WHERE s.enabled=1
          AND s.next_run IS NOT NULL
          AND s.next_run < ?
          AND s.status != 'running'
    """, (now,)).fetchall()

    for row in overdues:
        schedule_id = row['id']
        sched_at = row['next_run']
        logger.info(f"Recovering missed run for schedule {schedule_id} (was due {sched_at})")

        missed_id = f"missed_{schedule_id}_{sched_at}"
        conn.execute("""
            INSERT OR IGNORE INTO missed_runs (id, schedule_id, scheduled_at)
            VALUES (?, ?, ?)
        """, (missed_id, schedule_id, sched_at))
        conn.commit()

        try:
            run_id = backup_engine.run_backup(schedule_id, triggered_by='missed')
            conn.execute("""
                UPDATE missed_runs SET recovered=1, recovered_at=?
                WHERE id=?
            """, (datetime.utcnow().isoformat(), missed_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Missed run recovery failed for {schedule_id}: {e}")


def start():
    """Start the scheduler and recover missed runs."""
    _scheduler.start()
    logger.info("Scheduler started.")

    # Load all enabled schedules and add jobs
    conn = db.get_conn()
    schedules = conn.execute("SELECT id FROM schedules WHERE enabled=1").fetchall()
    for row in schedules:
        add_or_update_job(row['id'])

    # Recover missed jobs
    threading.Thread(target=recover_missed_runs, daemon=True).start()


def stop():
    """Shut down the scheduler gracefully."""
    _scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")


def get_next_run(schedule_id: str) -> str | None:
    """Return the next run time ISO string for a schedule."""
    jid = _job_id(schedule_id)
    job = _scheduler.get_job(jid)
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None
