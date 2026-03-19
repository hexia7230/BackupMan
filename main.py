"""
main.py - Backupman entry point.

Starts Flask in a background thread, then launches a native pywebview window.
The app runs silently (no console) and the window title bar acts as the chrome.
"""
import sys
import os
import threading
import time
import urllib.request
import logging

# ─── Logging setup ───────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'backupman.log'), encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# ─── Bootstrap ───────────────────────────────────────────────────────────────
from backend.db import init_db
from backend import scheduler as sched_module
from backend.api import app as flask_app

HOST = '127.0.0.1'
PORT = 7845
APP_URL = f'http://{HOST}:{PORT}/'


def _start_flask():
    """Run Flask server in a daemon thread."""
    flask_app.run(
        host=HOST,
        port=PORT,
        threaded=True,
        use_reloader=False,
        debug=False,
    )


def _wait_for_flask(timeout: float = 10.0) -> bool:
    """Busy-poll until Flask responds or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(APP_URL, timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    logger.info('Starting Backupman...')

    # 1. Database
    init_db()
    logger.info('Database initialized.')

    # 2. Settings Manager Initial Load
    from backend import settings_manager
    settings_manager.load_startup()
    logger.info('Settings startup load checked.')

    # 3. Scheduler
    sched_module.start()
    logger.info('Scheduler started.')

    # 4. Settings Manager Sync
    settings_manager.start_sync_thread()
    logger.info('Settings sync thread started.')

    # 5. Flask in background thread
    flask_thread = threading.Thread(target=_start_flask, name='flask', daemon=True)
    flask_thread.start()
    logger.info(f'Serving on {APP_URL}')

    # 4. Wait for Flask to be ready
    if not _wait_for_flask():
        logger.error('Flask did not start in time.')
        sys.exit(1)

    # 5. Launch native webview window (blocks until window is closed)
    try:
        import webview  # pywebview
        window = webview.create_window(
            title='Backupman',
            url=APP_URL,
            width=1400,
            height=900,
            min_size=(900, 600),
            resizable=True,
            text_select=True,
        )
        logger.info('Opening native window...')
        webview.start(debug=False)
    except ImportError:
        # Fallback: open in browser if pywebview not available
        logger.warning('pywebview not found, falling back to browser.')
        import webbrowser
        webbrowser.open(APP_URL)
        # Keep the Flask thread alive until user terminates
        try:
            flask_thread.join()
        except KeyboardInterrupt:
            pass

    # 6. Clean shutdown
    logger.info('Window closed. Shutting down scheduler.')
    sched_module.stop()
    logger.info('Backupman stopped.')


if __name__ == '__main__':
    main()
