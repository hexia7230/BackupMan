"""
api.py - Flask REST API endpoints for Backupman.

All responses are JSON. Frontend communicates exclusively through this API.
"""
import json
import os
import uuid
import threading
import subprocess
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory

from . import db, scheduler, backup_engine, network_handler, naming_engine, settings_manager

# Path to the frontend directory
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')

app = Flask(__name__, static_folder=FRONTEND_DIR)

# ─── Utility ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().isoformat()


def _err(msg: str, code: int = 400):
    return jsonify({'ok': False, 'error': msg}), code


def _ok(data: dict = None):
    payload = {'ok': True}
    if data:
        payload.update(data)
    return jsonify(payload)


# ─── Frontend Serving ──────────────────────────────────────────────────────────

@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    # Never serve API paths as static files
    if path.startswith('api/'):
        return _err('Not found', 404)
    return send_from_directory(FRONTEND_DIR, path)


# ─── Schedules ────────────────────────────────────────────────────────────────

@app.route('/api/schedules', methods=['GET'])
def list_schedules():
    conn = db.get_conn()
    rows = conn.execute("SELECT * FROM schedules ORDER BY name ASC").fetchall()

    result = []
    for row in rows:
        s = dict(row)
        s['schedule_config'] = json.loads(s.get('schedule_config') or '{}')
        # Load destinations
        dests = conn.execute(
            "SELECT * FROM destinations WHERE schedule_id=? ORDER BY sort_order",
            (s['id'],)
        ).fetchall()
        s['destinations'] = [dict(d) for d in dests]
        # Refresh next_run from scheduler
        nxt = scheduler.get_next_run(s['id'])
        if nxt:
            s['next_run'] = nxt
        result.append(s)

    return jsonify(result)


@app.route('/api/schedules', methods=['POST'])
def create_schedule():
    data = request.json or {}
    required = ['name', 'source_path', 'schedule_type', 'schedule_config']
    for field in required:
        if field not in data:
            return _err(f"Missing required field: {field}")

    sid = str(uuid.uuid4())
    now = _now()

    conn = db.get_conn()
    conn.execute("""
        INSERT INTO schedules
          (id, name, enabled, source_path, source_type, source_cred_id,
           schedule_type, schedule_config, delete_old, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sid,
        data['name'],
        int(data.get('enabled', True)),
        data['source_path'],
        data.get('source_type', 'local'),
        data.get('source_cred_id'),
        data['schedule_type'],
        json.dumps(data['schedule_config']),
        int(data.get('delete_old', False)),
        now, now
    ))

    # Insert destinations
    dests = data.get('destinations', [])
    for i, dest in enumerate(dests):
        conn.execute("""
            INSERT INTO destinations
              (id, schedule_id, dest_path, dest_type, dest_cred_id,
               name_template, ext, sort_order, compress_zip)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()), sid,
            dest['dest_path'],
            dest.get('dest_type', 'local'),
            dest.get('dest_cred_id'),
            dest.get('name_template', ''),
            dest.get('ext', ''),
            i,
            int(dest.get('compress_zip', False))
        ))

    conn.commit()
    scheduler.add_or_update_job(sid)
    return _ok({'id': sid})


@app.route('/api/schedules/<sid>', methods=['GET'])
def get_schedule(sid):
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM schedules WHERE id=?", (sid,)).fetchone()
    if not row:
        return _err("Schedule not found", 404)
    s = dict(row)
    s['schedule_config'] = json.loads(s.get('schedule_config') or '{}')
    dests = conn.execute(
        "SELECT * FROM destinations WHERE schedule_id=? ORDER BY sort_order",
        (sid,)
    ).fetchall()
    s['destinations'] = [dict(d) for d in dests]
    return jsonify(s)


@app.route('/api/schedules/<sid>', methods=['PUT'])
def update_schedule(sid):
    conn = db.get_conn()
    row = conn.execute("SELECT id FROM schedules WHERE id=?", (sid,)).fetchone()
    if not row:
        return _err("Schedule not found", 404)

    data = request.json or {}
    now = _now()

    conn.execute("""
        UPDATE schedules SET
          name=?, enabled=?, source_path=?, source_type=?, source_cred_id=?,
          schedule_type=?, schedule_config=?, delete_old=?, updated_at=?
        WHERE id=?
    """, (
        data.get('name'),
        int(data.get('enabled', True)),
        data.get('source_path'),
        data.get('source_type', 'local'),
        data.get('source_cred_id'),
        data.get('schedule_type'),
        json.dumps(data.get('schedule_config', {})),
        int(data.get('delete_old', False)),
        now, sid
    ))

    # Replace destinations
    conn.execute("DELETE FROM destinations WHERE schedule_id=?", (sid,))
    for i, dest in enumerate(data.get('destinations', [])):
        conn.execute("""
            INSERT INTO destinations
              (id, schedule_id, dest_path, dest_type, dest_cred_id,
               name_template, ext, sort_order, compress_zip)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()), sid,
            dest['dest_path'],
            dest.get('dest_type', 'local'),
            dest.get('dest_cred_id'),
            dest.get('name_template', ''),
            dest.get('ext', ''),
            i,
            int(dest.get('compress_zip', False))
        ))

    conn.commit()
    scheduler.add_or_update_job(sid)
    return _ok()


@app.route('/api/schedules/<sid>', methods=['DELETE'])
def delete_schedule(sid):
    conn = db.get_conn()
    conn.execute("DELETE FROM schedules WHERE id=?", (sid,))
    conn.commit()
    scheduler.remove_job(sid)
    return _ok()


@app.route('/api/schedules/<sid>/toggle', methods=['POST'])
def toggle_schedule(sid):
    conn = db.get_conn()
    row = conn.execute("SELECT enabled FROM schedules WHERE id=?", (sid,)).fetchone()
    if not row:
        return _err("Not found", 404)
    new_enabled = 0 if row['enabled'] else 1
    conn.execute("UPDATE schedules SET enabled=? WHERE id=?", (new_enabled, sid))
    conn.commit()
    scheduler.add_or_update_job(sid)
    return _ok({'enabled': bool(new_enabled)})


@app.route('/api/schedules/<sid>/run', methods=['POST'])
def run_now(sid):
    """Manually trigger a backup run in a background thread."""
    def _bg():
        backup_engine.run_backup(sid, triggered_by='manual')

    thread = threading.Thread(target=_bg, daemon=True)
    thread.start()
    return _ok({'message': 'Backup started'})


# ─── Active Runs & Progress ───────────────────────────────────────────────────

@app.route('/api/active-runs', methods=['GET'])
def list_active_runs():
    """List ongoing backup tasks and their progress."""
    tasks = []
    for rid, task in backup_engine.ACTIVE_TASKS.items():
        tasks.append({
            'run_id': rid,
            'schedule_id': task['schedule_id'],
            'schedule_name': task['schedule_name'],
            'progress': task['progress'],
            'step': task['step'],
            'started_at': task['started_at']
        })
    return jsonify(tasks)


@app.route('/api/active-runs/<rid>/cancel', methods=['POST'])
def cancel_run(rid):
    """Signal a running backup task to stop."""
    task = backup_engine.ACTIVE_TASKS.get(rid)
    if not task:
        return _err("Task not found or already completed", 404)

    task['stop_event'].set()
    return _ok({'message': 'Cancellation signal sent'})

@app.route('/api/history', methods=['GET'])
def get_history():
    conn = db.get_conn()
    limit = int(request.args.get('limit', 100))
    schedule_id = request.args.get('schedule_id')

    if schedule_id:
        rows = conn.execute("""
            SELECT rh.*, s.name as schedule_name
            FROM run_history rh
            JOIN schedules s ON s.id = rh.schedule_id
            WHERE rh.schedule_id=?
            ORDER BY rh.started_at DESC LIMIT ?
        """, (schedule_id, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT rh.*, s.name as schedule_name
            FROM run_history rh
            JOIN schedules s ON s.id = rh.schedule_id
            ORDER BY rh.started_at DESC LIMIT ?
        """, (limit,)).fetchall()

    result = []
    for row in rows:
        r = dict(row)
        dests = conn.execute(
            "SELECT * FROM run_destinations WHERE run_id=?", (r['id'],)
        ).fetchall()
        r['destinations'] = [dict(d) for d in dests]
        result.append(r)

    return jsonify(result)


@app.route('/api/history/<run_id>', methods=['GET'])
def get_run(run_id):
    conn = db.get_conn()
    row = conn.execute("""
        SELECT rh.*, s.name as schedule_name
        FROM run_history rh
        JOIN schedules s ON s.id = rh.schedule_id
        WHERE rh.id=?
    """, (run_id,)).fetchone()
    if not row:
        return _err("Not found", 404)
    r = dict(row)
    dests = conn.execute(
        "SELECT * FROM run_destinations WHERE run_id=?", (run_id,)
    ).fetchall()
    r['destinations'] = [dict(d) for d in dests]
    return jsonify(r)


# ─── Credentials ──────────────────────────────────────────────────────────────

@app.route('/api/credentials', methods=['GET'])
def list_credentials():
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, label, server, username, created_at FROM credentials"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/credentials', methods=['POST'])
def create_credential():
    data = request.json or {}
    for field in ['label', 'server', 'username', 'password']:
        if not data.get(field):
            return _err(f"Missing field: {field}")

    # Validate the credential by testing path access
    test_path = data.get('test_path') or data['server']
    ok, msg = network_handler.validate_path_access(
        test_path, data['username'], data['password']
    )
    if not ok:
        return _err(f"Credential validation failed: {msg}")

    cid = str(uuid.uuid4())
    b64pw = network_handler.encode_password(data['password'])
    conn = db.get_conn()
    conn.execute("""
        INSERT INTO credentials (id, label, server, username, password_b64, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (cid, data['label'], data['server'], data['username'], b64pw, _now()))
    conn.commit()
    return _ok({'id': cid})


@app.route('/api/credentials/<cid>', methods=['DELETE'])
def delete_credential(cid):
    conn = db.get_conn()
    conn.execute("DELETE FROM credentials WHERE id=?", (cid,))
    conn.commit()
    return _ok()


# ─── Path Validation ──────────────────────────────────────────────────────────

@app.route('/api/validate-path', methods=['POST'])
def validate_path():
    data = request.json or {}
    path = data.get('path', '')
    cred_id = data.get('cred_id')

    if cred_id:
        conn = db.get_conn()
        cred = conn.execute("SELECT * FROM credentials WHERE id=?", (cred_id,)).fetchone()
        if cred:
            cred = dict(cred)
            pwd = network_handler.decode_password(cred['password_b64'])
            ok, msg = network_handler.validate_path_access(path, cred['username'], pwd)
        else:
            ok, msg = False, "Credential not found."
    else:
        ok, msg = network_handler.validate_path_access(path)

    return _ok({'accessible': ok, 'message': msg})


# ─── Naming Preview ───────────────────────────────────────────────────────────

@app.route('/api/preview-name', methods=['POST'])
def preview_name():
    data = request.json or {}
    template = data.get('template', '')
    ext = data.get('ext', '')
    context = {
        'name': data.get('name', 'backup'),
        'seq': data.get('seq', 1),
        'source_name': data.get('source_name', 'source'),
    }
    result = naming_engine.resolve(template, ext, context)
    return _ok({'preview': result})


# ─── Dashboard Stats ──────────────────────────────────────────────────────────

@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = db.get_conn()
    total_schedules = conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
    enabled_schedules = conn.execute("SELECT COUNT(*) FROM schedules WHERE enabled=1").fetchone()[0]
    total_runs = conn.execute("SELECT COUNT(*) FROM run_history").fetchone()[0]
    success_runs = conn.execute(
        "SELECT COUNT(*) FROM run_history WHERE status='success'"
    ).fetchone()[0]
    error_runs = conn.execute(
        "SELECT COUNT(*) FROM run_history WHERE status='error'"
    ).fetchone()[0]
    running_now = conn.execute(
        "SELECT COUNT(*) FROM run_history WHERE status='running'"
    ).fetchone()[0]
    missed_unrecovered = conn.execute(
        "SELECT COUNT(*) FROM missed_runs WHERE recovered=0"
    ).fetchone()[0]

    # Recent runs for calendar
    recent = conn.execute("""
        SELECT date(started_at) as run_date, COUNT(*) as cnt, 
               SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success_cnt
        FROM run_history
        WHERE started_at >= date('now', '-60 days')
        GROUP BY run_date
    """).fetchall()

    return jsonify({
        'total_schedules': total_schedules,
        'enabled_schedules': enabled_schedules,
        'total_runs': total_runs,
        'success_runs': success_runs,
        'error_runs': error_runs,
        'running_now': running_now,
        'missed_unrecovered': missed_unrecovered,
        'calendar': [dict(r) for r in recent],
    })


# ─── Browse local filesystem (for path picker) ────────────────────────────────

@app.route('/api/browse', methods=['GET'])
def browse():
    path = request.args.get('path', '')
    if not path:
        # Return drive letters on Windows
        import string
        drives = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                drives.append({'name': drive, 'path': drive, 'is_dir': True})
        return jsonify(drives)

    if not os.path.exists(path):
        return _err("Path does not exist", 404)

    entries = []
    try:
        for entry in sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower())):
            entries.append({
                'name': entry.name,
                'path': entry.path,
                'is_dir': entry.is_dir(),
            })
    except PermissionError:
        return _err("Access denied", 403)

    return jsonify(entries)


# ─── Native folder picker dialog (Windows) ────────────────────────────────────

@app.route('/api/browse-dialog', methods=['GET'])
def browse_dialog():
    """
    Opens a native Windows FolderBrowserDialog via PowerShell.
    Blocks until the user selects a folder or cancels.
    Returns: { ok: true, path: "C:\\selected\\folder" } or { ok: true, path: null }
    """
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$d.Description = 'Select a folder'; "
        "$d.ShowNewFolderButton = $true; "
        "$d.RootFolder = 'MyComputer'; "
        "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath } else { '' }"
    )
    try:
        result = subprocess.run(
            ['powershell', '-WindowStyle', 'Hidden', '-NonInteractive', '-Command', ps_script],
            capture_output=True,
            text=True,
            timeout=300,   # give user up to 5 minutes to pick
        )
        path = result.stdout.strip()
        return _ok({'path': path if path else None})
    except subprocess.TimeoutExpired:
        return _ok({'path': None})
    except Exception as e:
        return _err(f"Could not open folder dialog: {e}")

@app.route('/api/open-file-dialog', methods=['GET'])
def open_file_dialog():
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.OpenFileDialog; "
        "$d.Filter = 'JSON Files (*.json)|*.json|All Files (*.*)|*.*'; "
        "if ($d.ShowDialog() -eq 'OK') { $d.FileName } else { '' }"
    )
    try:
        result = subprocess.run(
            ['powershell', '-WindowStyle', 'Hidden', '-NonInteractive', '-Command', ps_script],
            capture_output=True,
            text=True,
            timeout=300,
        )
        path = result.stdout.strip()
        return _ok({'path': path if path else None})
    except subprocess.TimeoutExpired:
        return _ok({'path': None})
    except Exception as e:
        return _err(f"Could not open file dialog: {e}")

@app.route('/api/save-file-dialog', methods=['GET'])
def save_file_dialog():
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.SaveFileDialog; "
        "$d.Filter = 'JSON Files (*.json)|*.json'; "
        "if ($d.ShowDialog() -eq 'OK') { $d.FileName } else { '' }"
    )
    try:
        result = subprocess.run(
            ['powershell', '-WindowStyle', 'Hidden', '-NonInteractive', '-Command', ps_script],
            capture_output=True,
            text=True,
            timeout=300,
        )
        path = result.stdout.strip()
        return _ok({'path': path if path else None})
    except subprocess.TimeoutExpired:
        return _ok({'path': None})
    except Exception as e:
        return _err(f"Could not open file dialog: {e}")


# ─── Settings Manager ─────────────────────────────────────────────────────────

@app.route('/api/global-settings', methods=['GET'])
def get_global_settings():
    conn = db.get_conn()
    rows = conn.execute("SELECT key, value FROM global_settings").fetchall()
    settings = {row['key']: row['value'] for row in rows}
    # Defaults
    if 'incremental_only' not in settings:
        settings['incremental_only'] = 'false'
    if 'multi_thread' not in settings:
        settings['multi_thread'] = 'false'
    return _ok({'settings': settings})

@app.route('/api/global-settings', methods=['POST'])
def save_global_settings():
    data = request.json or {}
    conn = db.get_conn()
    for k, v in data.items():
        conn.execute("INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)", (k, str(v).lower()))
    conn.commit()
    return _ok()

@app.route('/api/settings/status', methods=['GET'])
def get_settings_status():
    path = settings_manager.get_setting_path()
    if path and os.path.exists(path):
        return _ok({'configured': True, 'path': path})
    return _ok({'configured': False, 'path': path})

@app.route('/api/settings/create', methods=['POST'])
def create_settings():
    data = request.json or {}
    path = data.get('path')
    if not path:
        return _err("Missing path")
    settings_manager.clear_all_data()
    settings_manager.set_setting_path(path)
    settings_manager.dump_to_json(path)
    return _ok({'path': path})

@app.route('/api/settings/import', methods=['POST'])
def import_settings():
    data = request.json or {}
    path = data.get('path')
    if not path:
        return _err("Missing path")
    
    if not os.path.exists(path):
        return _err("File does not exist")
        
    success, msg = settings_manager.import_from_json(path)
    if success:
        settings_manager.set_setting_path(path)
        return _ok({'path': path})
    else:
        return _err(f"Failed to import settings: {msg}")

@app.route('/api/settings/export', methods=['POST'])
def export_settings():
    data = request.json or {}
    path = data.get('path')
    if not path:
        return _err("Missing path")
    settings_manager.dump_to_json(path)
    return _ok({'path': path})


