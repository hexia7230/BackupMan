import json
import os
import sys
import threading
import time
import uuid

from . import db

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_FILE = os.path.join(BASE_DIR, 'data', 'app_config.json')

def get_setting_path():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                path = config.get('setting_file_path')
                if path and os.path.exists(path):
                    return path
                return None
        except:
            pass
    return None

def set_setting_path(path):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({'setting_file_path': path}, f)

def get_stats_data():
    conn = db.get_conn()
    total_schedules = conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
    enabled_schedules = conn.execute("SELECT COUNT(*) FROM schedules WHERE enabled=1").fetchone()[0]
    total_runs = conn.execute("SELECT COUNT(*) FROM run_history").fetchone()[0]
    success_runs = conn.execute("SELECT COUNT(*) FROM run_history WHERE status='success'").fetchone()[0]
    error_runs = conn.execute("SELECT COUNT(*) FROM run_history WHERE status='error'").fetchone()[0]
    running_now = conn.execute("SELECT COUNT(*) FROM run_history WHERE status='running'").fetchone()[0]
    missed_unrecovered = conn.execute("SELECT COUNT(*) FROM missed_runs WHERE recovered=0").fetchone()[0]
    return {
        "Total Schedules": total_schedules,
        "Enabled": enabled_schedules,
        "Total Runs": total_runs,
        "Successful": success_runs,
        "Errors": error_runs,
        "Running Now": running_now,
        "Missed / Pending": missed_unrecovered,
    }

def dump_to_json(path=None):
    if path is None:
        path = get_setting_path()
    if not path:
        return
    
    conn = db.get_conn()
    data = {}
    
    # 1. Schedules & Destinations
    rows = conn.execute("SELECT * FROM schedules ORDER BY created_at ASC").fetchall()
    schedules = []
    for row in rows:
        s = dict(row)
        s['schedule_config'] = json.loads(s.get('schedule_config') or '{}')
        dests = conn.execute("SELECT * FROM destinations WHERE schedule_id=? ORDER BY sort_order", (s['id'],)).fetchall()
        s['destinations'] = [dict(d) for d in dests]
        schedules.append(s)
    data["Schedules"] = schedules

    # 2. Credentials
    creds = conn.execute("SELECT * FROM credentials").fetchall()
    data["Credentials"] = [dict(r) for r in creds]

    # 3. History
    hist = conn.execute("SELECT * FROM run_history").fetchall()
    data["RunHistory"] = [dict(r) for r in hist]
    
    # 4. Run Destinations
    run_dests = conn.execute("SELECT * FROM run_destinations").fetchall()
    data["RunDestinations"] = [dict(r) for r in run_dests]

    # 5. Missed Runs
    missed = conn.execute("SELECT * FROM missed_runs").fetchall()
    data["MissedRuns"] = [dict(r) for r in missed]
        
    stats = get_stats_data()
    data.update(stats)
    
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Failed to write setting file: {e}")

def clear_all_data():
    conn = db.get_conn()
    conn.execute("DELETE FROM run_destinations")
    conn.execute("DELETE FROM run_history")
    conn.execute("DELETE FROM missed_runs")
    conn.execute("DELETE FROM destinations")
    conn.execute("DELETE FROM schedules")
    conn.execute("DELETE FROM credentials")
    conn.commit()

def import_from_json(path):
    if not os.path.exists(path):
        return False, "File does not exist"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        conn = db.get_conn()
        
        # Clear all tables (order matters because of foreign keys)
        conn.execute("DELETE FROM run_destinations")
        conn.execute("DELETE FROM run_history")
        conn.execute("DELETE FROM missed_runs")
        conn.execute("DELETE FROM destinations")
        conn.execute("DELETE FROM schedules")
        conn.execute("DELETE FROM credentials")
        
        # 0. Credentials (must be inserted first due to foreign key constraints in Schedules)
        for c in data.get("Credentials", []):
            if 'id' not in c: continue
            conn.execute("""
                INSERT INTO credentials (id, label, server, username, password_b64, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (c['id'], c.get('label', ''), c.get('server', ''), c.get('username', ''), c.get('password_b64', ''), c.get('created_at', '')))
            
        # 1. Schedules
        for s in data.get("Schedules", []):
            if 'id' not in s: 
                s['id'] = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO schedules (id, name, enabled, source_path, source_type, source_cred_id, 
                                       schedule_type, schedule_config, delete_old, created_at, updated_at, last_run, next_run, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (s['id'], s.get('name', 'Imported'), s.get('enabled', 1), s.get('source_path', ''), s.get('source_type', 'local'), s.get('source_cred_id'),
                  s.get('schedule_type', 'daily'), json.dumps(s.get('schedule_config', {})), s.get('delete_old', 0), s.get('created_at', ''), s.get('updated_at', ''), s.get('last_run'), s.get('next_run'), s.get('status', 'idle')))
            
            for d in s.get('destinations', []):
                if 'id' not in d:
                    d['id'] = str(uuid.uuid4())
                conn.execute("""
                    INSERT INTO destinations (id, schedule_id, dest_path, dest_type, dest_cred_id, name_template, ext, sort_order, compress_zip)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (d['id'], s['id'], d.get('dest_path', ''), d.get('dest_type', 'local'), d.get('dest_cred_id'), d.get('name_template', ''), d.get('ext', 'bak'), d.get('sort_order', 0), int(d.get('compress_zip', 0))))
        
        # 3. History
        for h in data.get("RunHistory", []):
            if 'id' not in h: continue
            conn.execute("""
                INSERT INTO run_history (id, schedule_id, started_at, finished_at, status, bytes_copied, error_msg, triggered_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (h['id'], h['schedule_id'], h['started_at'], h.get('finished_at'), h.get('status', 'running'), h.get('bytes_copied'), h.get('error_msg'), h.get('triggered_by', 'scheduler')))

        # 4. Run Destinations
        for rd in data.get("RunDestinations", []):
            if 'id' not in rd: continue
            conn.execute("""
                INSERT INTO run_destinations (id, run_id, dest_id, dest_path, output_name, status, bytes_copied, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (rd['id'], rd['run_id'], rd['dest_id'], rd['dest_path'], rd.get('output_name'), rd.get('status', 'pending'), rd.get('bytes_copied'), rd.get('error_msg')))

        # 5. Missed Runs
        for m in data.get("MissedRuns", []):
            if 'id' not in m: continue
            conn.execute("""
                INSERT INTO missed_runs (id, schedule_id, scheduled_at, recovered, recovered_at)
                VALUES (?, ?, ?, ?, ?)
            """, (m['id'], m['schedule_id'], m['scheduled_at'], m.get('recovered', 0), m.get('recovered_at')))
                
        conn.commit()
        
        from . import scheduler
        # We need to refresh running jobs: remove all and re-add
        try:
            scheduler._scheduler.remove_all_jobs()
            enabled_schedules = conn.execute("SELECT id FROM schedules WHERE enabled=1").fetchall()
            for r in enabled_schedules:
                scheduler.add_or_update_job(r['id'])
        except Exception as e:
            print(f"Warning: could not rebuild APScheduler jobs: {e}")
        return True, ""
    except Exception as e:
        print(f"Failed to import setting file: {e}")
        return False, str(e)

def load_startup():
    path = get_setting_path()
    if path and os.path.exists(path):
        success, msg = import_from_json(path)
        if not success:
            print(f"Failed to load settings on startup: {msg}")

def bg_sync():
    last_hash = ""
    while True:
        try:
            path = get_setting_path()
            if path:
                conn = db.get_conn()
                stats = get_stats_data()
                sc_count = conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
                sc_max_updated = conn.execute("SELECT MAX(updated_at) FROM schedules").fetchone()[0]
                current_hash = f"{stats}_{sc_count}_{sc_max_updated}"
                
                if current_hash != last_hash:
                    dump_to_json(path)
                    last_hash = current_hash
        except:
            pass
        time.sleep(2)

def start_sync_thread():
    t = threading.Thread(target=bg_sync, daemon=True)
    t.start()
