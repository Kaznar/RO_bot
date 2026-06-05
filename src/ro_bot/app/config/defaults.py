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
    "xmas",
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
            "reaim_hold_dist": 3,
            "aim_settle_sec": 0.10,
            "target_settle_sec": 2.5,
            "path_stuck_min_dist": 5,
            "path_stuck_timeout_sec": 1.5,
            "path_stuck_blacklist_sec": 5.0,
            "dead_zone_wait_sec": 3.0,
            "approach_stall_timeout_sec": 2.5,
            "approach_stall_min_dist": 3,
            "approach_stall_blacklist_sec": 5.0,
            "ks_guard_min_dist": 3,
            "ks_guard_min_hp_deficit": 1,
            "ks_guard_blacklist_sec": 30.0,
            "player_closer_margin": 3,
            "player_near_mob_radius": 45,
            "player_near_bot_radius": 40,
            "player_closer_max_mob_dist": 0,
            "player_closer_max_player_mob_dist": 60,
            "player_closer_blacklist_sec": 30.0,
            "player_closer_force_tp": True,
            "player_defer_hunt_if_visible": True,
            "player_visible_grace_sec": 25.0,
            "player_visible_retp_sec": 5.0,
            "player_gid_min": 3_000_000,
            "player_gid_max": 4_000_000,
            "all_blacklisted_force_tp_sec": 5.0,
            "abandon_target_key": "",
            "engage_skill_key": "",
            "engage_skill_delay_sec": 0.05,
            "engage_skill_repeat_sec": 1.5,
        },
        "heal": {
            "item": {
                "keys": ["h"],
                "min_hp": 1000,
                "cooldown_sec": 1.0,
            },
            "skill": {
                "keys": ["q"],
                "min_hp": 500,
                "cooldown_sec": 1.0,
                "click_self": False,
                "key_interval_sec": 0.05,
                "skill_delay_sec": 0.05,
            },
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
        "sp_sit": {
            "sit_key": "space",
            "sit_when_sp_below": 10,
            "max_weight_ratio": 0.7,
            "postpone_after_interrupt_sec": 45.0,
            "min_hp_drop": 1,
        },
        "escape": {
            "key": "t",
            "cooldown_sec": 3.0,
        },
        "staff_guard": {
            "min_gid": 2000000,
            "max_gid": 2500000,
            "max_distance_cells": 20,
            "name_substrings": ["GM", "Admin", "Staff"],
        },
        "buff_healer_suppress_sec": 900,
        "buff_farm_map_only": True,
        "buff_step_gap_sec": 1.0,
        "buff_click_self": True,
        "buff_skill_delay_sec": 0.2,
        "buffs": [
            {"order": 1, "key": "f", "interval_sec": 1740.0},
            {"order": 2, "key": "c", "interval_sec": 1140.0},
        ],
        "self_buffs": [
            {"order": 1, "key": "d", "interval_sec": 240.0},
            {"order": 2, "key": "a", "interval_sec": 240.0},
        ],
    },
}
