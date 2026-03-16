"""
network_handler.py - Handles UNC/network share connections using stored credentials.

On Windows, net use is used to map a network path with credentials.
If no credentials are needed, the path is used as-is.
"""
import subprocess
import os
import sys
import base64
import logging

# Windows process creation flag to suppress console window
_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

logger = logging.getLogger(__name__)


def decode_password(b64_str: str) -> str:
    """Decode a base64-obfuscated password."""
    try:
        return base64.b64decode(b64_str.encode()).decode('utf-8')
    except Exception:
        return ''


def encode_password(plain: str) -> str:
    """Encode a password with base64 obfuscation."""
    return base64.b64encode(plain.encode('utf-8')).decode('ascii')


def connect_network_path(path: str, username: str, password: str) -> tuple[bool, str]:
    """
    Connect to a UNC network path using net use.

    :param path:     UNC path, e.g. \\\\server\\share
    :param username: Domain\\Username or just Username
    :param password: Plain text password
    :return:         (success: bool, message: str)
    """
    if not path.startswith('\\\\'):
        return False, "Path is not a UNC network path."

    # Extract the share root (\\server\share)
    parts = path.replace('\\\\', '').split('\\')
    if len(parts) < 2:
        return False, "Invalid UNC path format."
    share_root = '\\\\' + parts[0] + '\\' + parts[1]

    cmd = ['net', 'use', share_root, password, f'/user:{username}', '/persistent:no']
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_NO_WINDOW
        )
        if result.returncode == 0:
            return True, "Connected successfully."
        else:
            err = result.stderr.strip() or result.stdout.strip()
            return False, f"net use failed: {err}"
    except subprocess.TimeoutExpired:
        return False, "Connection timed out."
    except Exception as e:
        return False, str(e)


def disconnect_network_path(path: str):
    """Disconnect a mapped network share."""
    if not path.startswith('\\\\'):
        return
    parts = path.replace('\\\\', '').split('\\')
    if len(parts) < 2:
        return
    share_root = '\\\\' + parts[0] + '\\' + parts[1]
    try:
        subprocess.run(
            ['net', 'use', share_root, '/delete', '/yes'],
            capture_output=True,
            timeout=10,
            creationflags=_NO_WINDOW
        )
    except Exception:
        pass


def validate_path_access(path: str, username: str = '', password: str = '') -> tuple[bool, str]:
    """
    Validate that a path is accessible.
    For network paths with credentials, attempts a temporary net use connection.

    :return: (accessible: bool, message: str)
    """
    if path.startswith('\\\\') and username and password:
        ok, msg = connect_network_path(path, username, password)
        if not ok:
            return False, msg

    if os.path.exists(path):
        return True, "Path is accessible."
    else:
        return False, f"Path does not exist or is inaccessible: {path}"
