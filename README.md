
# Backupman

Backupman is a simple yet powerful desktop backup management tool designed for flexible and automated data protection. It runs as a native Windows application, combining a Python backend (Flask + APScheduler) with a modern web-based frontend.


---

## Features

### 1. Flexible Source Management
- Supports both **files and folders**
- Works with **local paths and network paths (UNC)** (e.g. `\\Server\Backup`)
- Securely stores **credentials for network access**
- Automatically connects to network shares during backup

---

### 2. Multi-Destination Backup
- Backup to **multiple locations in one job**
- Example targets:
  - External drives
  - NAS
  - Local disks
- Uses **parallel processing (up to 4 destinations)** for faster execution

---

### 3. Advanced Naming Engine
- Custom filename templates:
  - Date / time
  - Source name
  - Sequence numbers
- Control file extensions:
  - Keep original
  - Convert to `.zip`, `.bak`, etc.
- Includes **preview function** before execution

---

### 4. Scheduling & Automation
- Flexible schedules:
  - Daily / Weekly / Monthly
- Runs in the background using **APScheduler**
- Tracks **missed runs** (e.g. PC was off)
- Allows retry of missed backups

---

### 5. Compression & Cleanup
- Optional **ZIP compression** to save disk space
- Automatic cleanup:
  - Keep only latest N backups (e.g. last 5)
  - Delete older files automatically

---

### 6. Dashboard & History
- Real-time backup progress tracking (%)
- Displays current operation step
- Detailed logs:
  - Success / failure
  - Errors
  - Bytes copied
- Statistics overview:
  - Total runs
  - Success rate
  - Error count

---

### 7. Portable Configuration
- All settings stored in a **single JSON file**
- Includes:
  - Schedules
  - Destinations
  - Credentials
  - History
- Easily migrate to another PC by importing config

---


## Project Structure

```

Backupman/
│
├── main.py                 # Application entry point (Flask app)
├── backup_engine.py       # Core backup logic
├── settings_manager.py    # Configuration handling (JSON)
├── requirements.txt       # Dependencies
└── ...

````

---

## Requirements

Install dependencies:

```bash
pip install -r requirements.txt
````

---

## Install

>>> 1. To build→　Build.bat
    2. Find→　dist/Backupman.exe
---

## Notes

* Designed primarily for **Windows environments**
* Supports **network-based backups (NAS / servers)**
* Can be packaged as an **.exe for desktop use**

