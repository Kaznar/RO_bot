"""Default config content written on first run.

Editing ``DEFAULTS`` is equivalent to editing what a fresh install
ships with — the loader writes this to ``config.json`` the first
time the bot can't find one. Every value must be serializable by
``json.dump`` (no tuples, no frozensets).
"""

from __future__ import annotations

from typing import Any

# Exact ``PacketSniffer`` map ids — full automation suspended on these
# maps (manual player control).
DEFAULT_MANUAL_CONTROL_MAPS: list[str] = [
    "alberta",
    "payon",
    "morocc",
    "prontera",
    "izlude",
    "geffen",
    "aldebaran",
    "yuno",
    "umbala",
    "comodo",
    "niflheim",
    "einbroch",
    "lighthalzen",
    "hugel",
]

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
        "manual_control_maps": list(DEFAULT_MANUAL_CONTROL_MAPS),
        "mobs": {
            "allowed": ["Muka", "Porcellio", "Metaling",
                        "Alligator", "Myst Case"],
            "dangerous": ["Hunter Fly", "Dragon Fly", "Garm Baby",
                          "Knight of Windstorm"],
        },
        "aim_offsets": [],
        "engagement": {
            "kill_timeout_sec": 15.0,
            "blacklist_sec": 30.0,
            "reaim_click_cooldown_sec": 0.3,
            "aim_settle_sec": 0.10,
            "target_settle_sec": 2.5,
            "path_stuck_min_dist": 5,
            "path_stuck_timeout_sec": 1.5,
            "path_stuck_blacklist_sec": 5.0,
            "dead_zone_wait_sec": 3.0,
            "approach_stall_timeout_sec": 2.5,
            "approach_stall_min_dist": 3,
            "approach_stall_blacklist_sec": 5.0,
            "ks_guard_min_dist": 0,
            "ks_guard_min_hp_deficit": 1,
            "ks_guard_blacklist_sec": 8.0,
            "abandon_target_key": "",
        },
        "heal": {
            "key": "q",
            "cooldown_sec": 1.0,
            "min_hp": 500,
            "save_recovery_check_sec": 5.0,
            "save_recovery_key": "h",
        },
        "idle_action": {
            "key": "t",
            "after_sec": 10.0,
            "after_kill_sec": 2.0,
        },
        "overweight": {
            "ratio": 0.9,
            "key": "h",
            "press_interval_sec": 4.0,
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
