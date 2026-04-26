-- RO_bot configuration schema (v1).
--
-- One-to-many fan-out from `server` (process_name / window_title /
-- projection / dead zones) to `profile` (char_name / mobs / maps /
-- buffs / heal / idle / escape / engagement). Two profiles on the
-- same server share one server row.
--
-- Designed to be edited in DB Browser for SQLite; every table is
-- normalized (no JSON blobs) so you can see / search / update
-- individual fields with standard row-level SQL.

PRAGMA foreign_keys = ON;

-- ── Server (per private server + client build) ───────────────────────

CREATE TABLE server (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    process_name  TEXT NOT NULL,
    window_title  TEXT NOT NULL
);

CREATE TABLE server_projection (
    server_id        INTEGER PRIMARY KEY REFERENCES server(id) ON DELETE CASCADE,
    px_per_cell_x    REAL NOT NULL,
    px_per_cell_y    REAL NOT NULL,
    camera_offset_x  REAL NOT NULL DEFAULT 0,
    camera_offset_y  REAL NOT NULL DEFAULT 0
);

CREATE TABLE server_dead_zone (
    id         INTEGER PRIMARY KEY,
    server_id  INTEGER NOT NULL REFERENCES server(id) ON DELETE CASCADE,
    anchor     TEXT NOT NULL CHECK (anchor IN ('TL', 'TR', 'BL', 'BR')),
    inset_x    INTEGER NOT NULL,
    inset_y    INTEGER NOT NULL,
    width      INTEGER NOT NULL,
    height     INTEGER NOT NULL
);

-- ── Profile (per character / hunting strategy) ───────────────────────

CREATE TABLE profile (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    server_id    INTEGER NOT NULL REFERENCES server(id),
    char_name    TEXT NOT NULL,
    primary_map  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE profile_engagement (
    profile_id                INTEGER PRIMARY KEY REFERENCES profile(id) ON DELETE CASCADE,
    kill_timeout_sec          REAL NOT NULL DEFAULT 15.0,
    blacklist_sec             REAL NOT NULL DEFAULT 30.0,
    reaim_click_cooldown_sec  REAL NOT NULL DEFAULT 0.3,
    aim_settle_sec            REAL NOT NULL DEFAULT 0.10,
    target_settle_sec         REAL NOT NULL DEFAULT 2.5
);

CREATE TABLE profile_heal (
    profile_id     INTEGER PRIMARY KEY REFERENCES profile(id) ON DELETE CASCADE,
    key            TEXT NOT NULL,
    threshold_pct  REAL NOT NULL DEFAULT 0.30,
    cooldown_sec   REAL NOT NULL DEFAULT 1.0
);

CREATE TABLE profile_idle_action (
    profile_id      INTEGER PRIMARY KEY REFERENCES profile(id) ON DELETE CASCADE,
    key             TEXT NOT NULL,
    after_sec       REAL NOT NULL DEFAULT 10.0,
    after_kill_sec  REAL NOT NULL DEFAULT 2.0
);

CREATE TABLE profile_escape (
    profile_id    INTEGER PRIMARY KEY REFERENCES profile(id) ON DELETE CASCADE,
    key           TEXT NOT NULL,
    cooldown_sec  REAL NOT NULL DEFAULT 3.0
);

CREATE TABLE profile_mob (
    id          INTEGER PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    mob_name    TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('allowed', 'dangerous')),
    UNIQUE (profile_id, mob_name, role)
);

CREATE TABLE profile_map (
    id          INTEGER PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    map_name    TEXT NOT NULL,
    UNIQUE (profile_id, map_name)
);

CREATE TABLE profile_buff (
    id            INTEGER PRIMARY KEY,
    profile_id    INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    order_index   INTEGER NOT NULL,
    key           TEXT NOT NULL,
    interval_sec  REAL NOT NULL,
    UNIQUE (profile_id, key)
);
