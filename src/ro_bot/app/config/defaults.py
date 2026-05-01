"""Default config content written on first run.

Editing ``DEFAULTS`` is equivalent to editing what a fresh install
ships with — the loader writes this to ``config.json`` the first
time the bot can't find one. Every value must be serializable by
``json.dump`` (no tuples, no frozensets).
"""

from __future__ import annotations

from typing import Any

DEFAULTS: dict[str, Any] = {
    "server": {
        "name": "nexusro",
        "process_name": "nexusro.exe",
        "window_title": "NexusRO",
        "projection": {
            "px_per_cell_x": 42.0,
            "px_per_cell_y": 39.0,
            "camera_offset_x": 0.0,
            "camera_offset_y": 0.0,
        },
        "dead_zones": [
            # Tuned for 1600x900 NexusRO HUD (matches prototype).
            {"anchor": "TL", "inset_x": 0, "inset_y": 0,
             "width": 220, "height": 70},
            {"anchor": "TR", "inset_x": 130, "inset_y": 0,
             "width": 150, "height": 60},
            {"anchor": "TR", "inset_x": 0, "inset_y": 120,
             "width": 42, "height": 39},
            {"anchor": "BL", "inset_x": 566, "inset_y": 91,
             "width": 42, "height": 39},
        ],
    },
    "profile": {
        "char_name": "JoJo",
        "allowed_maps": ["ein_fild09", "cmd_fild01", "xmas_dun02"],
        "mobs": {
            "allowed": ["Muka", "Porcellio", "Metaling",
                        "Alligator", "Myst Case"],
            "dangerous": ["Hunter Fly", "Dragon Fly", "Garm Baby",
                          "Knight of Windstorm"],
        },
        "engagement": {
            "kill_timeout_sec": 15.0,
            "blacklist_sec": 30.0,
            "reaim_click_cooldown_sec": 0.3,
            "aim_settle_sec": 0.10,
            "target_settle_sec": 2.5,
            "stuck_timeout_threshold": 3,
            "stuck_blacklist_sec": 300.0,
        },
        "heal": {
            "key": "q",
            "cooldown_sec": 1.0,
            "min_hp": 500,
        },
        "idle_action": {
            "key": "t",
            "after_sec": 10.0,
            "after_kill_sec": 2.0,
        },
        "escape": {
            "key": "t",
            "cooldown_sec": 3.0,
        },
        "buffs": [
            {"order": 1, "key": "f", "interval_sec": 1800.0},
            {"order": 2, "key": "c", "interval_sec": 1200.0},
        ],
    },
}
