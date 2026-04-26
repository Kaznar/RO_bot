"""UAC relaunch helper.

The game client runs elevated, so reading its process memory requires
the bot to be elevated too. On first launch we detect that we're not
admin and relaunch the same command through ShellExecuteW with the
'runas' verb (UAC consent dialog).
"""

from __future__ import annotations

import ctypes
import os
import sys


def ensure_admin() -> None:
    """Relaunch the current interpreter with elevation if not already.

    No-op if already admin. Otherwise spawns an elevated `cmd.exe`
    sub-shell and exits the current (non-elevated) process.
    """
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except OSError:
        is_admin = False
    if is_admin:
        return

    # Relaunch through cmd so the user sees the console (stdout of the
    # elevated process would otherwise be invisible). `/k` keeps the
    # window open after the bot exits for post-mortem inspection.
    script_dir = os.path.abspath(os.getcwd())
    extra = " ".join(f'"{a}"' for a in sys.argv[1:])
    cmd = f'/k cd /d "{script_dir}" && "{sys.executable}" -m ro_bot {extra}'
    ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", cmd, None, 1)
    sys.exit(0)
