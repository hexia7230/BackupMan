"""
backup_engine.py - Core backup execution logic.

Flow per run:
  1. Connect to source (network credentials if needed).
  2. Copy source to staging work directory.
  3. For each destination defined on the schedule:
     a. Connect to destination (network credentials if needed).
     b. Resolve output filename from naming template.
     c. Copy staged archive to destination.
     d. If delete_old is set, remove previous backups matching the name prefix.
  4. Clean up staging directory.
  5. Update run history in DB.
"""
import os
import shutil
import logging
import uuid
import json
from datetime import datetime
from pathlib import Path

from . import db, naming_engine, network_handler

logger = logging.getLogger(__name__)

WORK_DIR = os.path.join(os.path.dirname(__file__), '..', 'workdir')

# Global tracking for active backup tasks
# { run_id: { 'stop_event': Event, 'progress': int, 'step': str, 'schedule_name': str } }
ACTIVE_TASKS = {}
import threading


def _get_cred(cred_id: str) -> dict | None:
    """Fetch a credential record from DB."""
    if not cred_id:
        return None
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM credentials WHERE id=?", (cred_id,)).fetchone()
    if row:
        return dict(row)
    return None


def _ensure_connection(path: str, cred_id: str = None) -> tuple[bool, str, dict | None]:
    """
    Ensure the path is accessible, connecting with credentials if needed.

    :return: (ok, message, cred_dict_or_None)
    """
    cred = _get_cred(cred_id)
    if path.startswith('\\\\') and cred:
        password = network_handler.decode_password(cred['password_b64'])
        ok, msg = network_handler.connect_network_path(path, cred['username'], password)
        return ok, msg, cred
    else:
        if os.path.exists(path):
            return True, "OK", cred
        else:
            return False, f"Path not found: {path}", cred


def _stage_source(source_path: str, run_id: str) -> str:
    """
    Copy source (file or directory) into the staging work directory.

    :return: Path of staged copy.
    """
    os.makedirs(WORK_DIR, exist_ok=True)
    stage_dir = os.path.join(WORK_DIR, run_id)
    os.makedirs(stage_dir, exist_ok=True)

    source_name = os.path.basename(source_path.rstrip('/\\'))
    dest = os.path.join(stage_dir, source_name)

    if os.path.isdir(source_path):
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(source_path, dest)
    else:
        shutil.copy2(source_path, dest)

    return dest


def _get_dir_size(path: str) -> int:
    """Return total byte size of a directory or file."""
    total = 0
    if os.path.isdir(path):
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    else:
        try:
            total = os.path.getsize(path)
        except OSError:
            pass
    return total


def _delete_old_backups(dest_dir: str, name_prefix: str, current_filename: str):
    """
    Delete previous backup files in dest_dir that start with name_prefix,
    excluding the current file just written.
    """
    try:
        for entry in os.listdir(dest_dir):
            if entry == current_filename:
                continue
            if entry.startswith(name_prefix):
                full = os.path.join(dest_dir, entry)
                try:
                    if os.path.isdir(full):
                        shutil.rmtree(full)
                    else:
                        os.remove(full)
                    logger.info(f"Deleted old backup: {full}")
                except Exception as e:
                    logger.warning(f"Could not delete old backup {full}: {e}")
    except Exception as e:
        logger.warning(f"Could not list directory for cleanup {dest_dir}: {e}")


def _copy_to_dest(staged_path: str, dest_path: str, output_name: str, compress_zip: bool = False, stop_event: threading.Event = None) -> tuple[bool, str, int]:
    """
    Copy the staged source to the destination directory with the given output name.
    """
    try:
        if stop_event and stop_event.is_set():
            return False, "Cancelled by user", 0

        os.makedirs(dest_path, exist_ok=True)
        out_full = os.path.join(dest_path, output_name)

        # Remove existing file/folder with the same name if exists
        if os.path.exists(out_full):
            shutil.rmtree(out_full) if os.path.isdir(out_full) else os.remove(out_full)

        if compress_zip:
            if stop_event and stop_event.is_set(): return False, "Cancelled", 0
            if os.path.isdir(staged_path):
                tmp_dir = os.path.dirname(staged_path)
                tmp_archive_base = os.path.join(tmp_dir, f"tmp_zip_{uuid.uuid4().hex}")
                shutil.make_archive(tmp_archive_base, 'zip', staged_path)
                shutil.move(tmp_archive_base + '.zip', out_full)
            else:
                import zipfile
                with zipfile.ZipFile(out_full, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.write(staged_path, os.path.basename(staged_path))
        else:
            if os.path.isdir(staged_path):
                # For simplicity in this scale, we use copytree.
                # In a real high-perf app, we'd loop files to check stop_event.
                shutil.copytree(staged_path, out_full)
            else:
                shutil.copy2(staged_path, out_full)

        if stop_event and stop_event.is_set():
            # Clean up partial copy if cancelled
            if os.path.isdir(out_full): shutil.rmtree(out_full)
            else: os.remove(out_full)
            return False, "Cancelled by user", 0

        size = _get_dir_size(out_full)
        return True, '', size
    except Exception as e:
        return False, str(e), 0


def run_backup(schedule_id: str, triggered_by: str = 'scheduler',
               progress_callback=None) -> str:
    """
    Execute a full backup run for the given schedule.
    """
    conn = db.get_conn()
    run_id = str(uuid.uuid4())
    started_at = datetime.utcnow().isoformat()

    # Create stop event for this run
    stop_event = threading.Event()

    # --- Load schedule ---
    sched = conn.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone()
    if not sched:
        logger.error(f"Schedule {schedule_id} not found.")
        return run_id
    sched = dict(sched)

    # Register in active tasks
    ACTIVE_TASKS[run_id] = {
        'stop_event': stop_event,
        'progress': 0,
        'step': 'Starting',
        'schedule_name': sched['name'],
        'schedule_id': schedule_id,
        'started_at': started_at
    }

    dests = conn.execute(
        "SELECT * FROM destinations WHERE schedule_id=? ORDER BY sort_order ASC",
        (schedule_id,)
    ).fetchall()
    dests = [dict(d) for d in dests]

    # --- Insert run record ---
    conn.execute(
        """INSERT INTO run_history (id, schedule_id, started_at, status, triggered_by)
           VALUES (?, ?, ?, 'running', ?)""",
        (run_id, schedule_id, started_at, triggered_by)
    )
    # Update schedule status
    conn.execute("UPDATE schedules SET status='running', last_run=? WHERE id=?",
                 (started_at, schedule_id))
    conn.commit()

    def _cleanup():
        # Remove from active tasks
        ACTIVE_TASKS.pop(run_id, None)
        # Clean staging
        stage_run_dir = os.path.join(WORK_DIR, run_id)
        try:
            if os.path.exists(stage_run_dir):
                shutil.rmtree(stage_run_dir)
        except Exception as e:
            logger.warning(f"Could not clean staging dir {stage_run_dir}: {e}")

    def _fail(msg, status='error'):
        conn.execute(
            "UPDATE run_history SET status=?, finished_at=?, error_msg=? WHERE id=?",
            (status, datetime.utcnow().isoformat(), msg, run_id)
        )
        conn.execute("UPDATE schedules SET status=? WHERE id=?", (status, schedule_id))
        conn.commit()
        _cleanup()

    def _progress(step: str, pct: int):
        if run_id in ACTIVE_TASKS:
            ACTIVE_TASKS[run_id]['progress'] = pct
            ACTIVE_TASKS[run_id]['step'] = step
        if progress_callback:
            progress_callback(step, pct)

    try:
        if stop_event.is_set():
            _fail("Cancelled by user", 'missed')
            return run_id

        _progress("Connecting to source", 5)
        # --- Connect source ---
        ok, msg, _ = _ensure_connection(sched['source_path'], sched.get('source_cred_id'))
        if not ok:
            _fail(f"Source connection failed: {msg}")
            return run_id

        if stop_event.is_set():
            _fail("Cancelled by user", 'missed')
            return run_id

        _progress("Staging source data", 20)
        # --- Stage source ---
        try:
            staged = _stage_source(sched['source_path'], run_id)
        except Exception as e:
            _fail(f"Staging failed: {e}")
            return run_id

        from concurrent.futures import ThreadPoolExecutor, as_completed

        total_bytes = 0
        total_dests = len(dests)
        results = []

        source_name = os.path.basename(sched['source_path'].rstrip('/\\'))
        name_context_base = {
            'name': sched['name'],
            'source_name': source_name,
        }

        def process_destination(i, dest):
            if stop_event.is_set():
                return {'dest_id': dest['id'], 'ok': False, 'msg': 'Cancelled'}

            rdest_id = str(uuid.uuid4())
            # Use a new connection for each thread to avoid SQLite concurrency issues
            thread_conn = db.get_conn() 
            
            thread_conn.execute(
                """INSERT INTO run_destinations
                   (id, run_id, dest_id, dest_path, status)
                   VALUES (?, ?, ?, ?, 'running')""",
                (rdest_id, run_id, dest['id'], dest['dest_path'])
            )
            thread_conn.commit()

            try:
                # 1. Connect to destination
                ok2, msg2, _ = _ensure_connection(dest['dest_path'], dest.get('dest_cred_id'))
                if not ok2:
                    thread_conn.execute(
                        "UPDATE run_destinations SET status='error', error_msg=? WHERE id=?",
                        (f"Destination connection failed: {msg2}", rdest_id)
                    )
                    thread_conn.commit()
                    return {'dest_id': dest['id'], 'ok': False, 'msg': msg2, 'size': 0}

                # 2. Resolve output filename
                local_context = name_context_base.copy()
                local_context['seq'] = i + 1
                template = dest.get('name_template', '')
                ext = dest.get('ext', '')
                output_name = naming_engine.resolve(template, ext, local_context)
                
                compress_zip = dest.get('compress_zip', 0) == 1
                if compress_zip and '.' not in output_name:
                    output_name += '.zip'

                # 3. Copy staged to destination
                ok3, err3, size3 = _copy_to_dest(staged, dest['dest_path'], output_name, compress_zip, stop_event)

                if stop_event.is_set():
                    return {'dest_id': dest['id'], 'ok': False, 'msg': 'Cancelled', 'size': 0}

                # 4. Delete old if requested
                if sched['delete_old'] and ok3:
                    name_prefix = local_context.get('name', 'backup')
                    _delete_old_backups(dest['dest_path'], name_prefix, output_name)

                # 5. Update DB
                status = 'success' if ok3 else 'error'
                thread_conn.execute(
                    """UPDATE run_destinations
                       SET status=?, output_name=?, bytes_copied=?, error_msg=?
                       WHERE id=?""",
                    (status, output_name, size3, err3 if not ok3 else None, rdest_id)
                )
                thread_conn.commit()
                return {'dest_id': dest['id'], 'ok': ok3, 'msg': err3, 'size': size3, 'output_name': output_name}
            except Exception as e:
                return {'dest_id': dest['id'], 'ok': False, 'msg': str(e), 'size': 0}

        # Execute destinations in parallel (up to 4 at a time to not over-tax disk/network)
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_dest = {executor.submit(process_destination, i, d): d for i, d in enumerate(dests)}
            
            completed_count = 0
            for future in as_completed(future_to_dest):
                res = future.result()
                results.append(res)
                total_bytes += res.get('size', 0)
                completed_count += 1
                
                pct = 40 + int((completed_count / max(total_dests, 1)) * 55)
                _progress(f"Processed destinations: {completed_count}/{total_dests}", pct)

        if stop_event.is_set():
            _fail("Cancelled by user", 'missed')
            return run_id

        _progress("Cleaning staging area", 97)
        _cleanup()
        _progress("Done", 100)

        # --- Finalize run record ---
        final_status = 'success' if all(r.get('ok', False) for r in results) else 'error'
        all_err = '; '.join(str(r.get('msg', 'Error')) for r in results if not r.get('ok')) or None
        conn.execute(
            """UPDATE run_history
               SET status=?, finished_at=?, bytes_copied=?, error_msg=?
               WHERE id=?""",
            (final_status, datetime.utcnow().isoformat(), total_bytes, all_err, run_id)
        )
        conn.execute("UPDATE schedules SET status=? WHERE id=?", (final_status, schedule_id))
        conn.commit()

    except Exception as e:
        logger.error(f"Run {run_id} crashed: {e}")
        _fail(f"System error: {e}")

    return run_id
