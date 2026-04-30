"""Non-profile hunt constants (poll rates, log cadences).

These don't vary per profile or server — they're pure implementation
tuning for the tick loop. Anything tunable by a hunter (thresholds,
keys, mob lists) lives in :class:`HuntConfig` and comes from the
app-layer JSON config.
"""

from __future__ import annotations

# Main tick rate while no target is engaged.
IDLE_POLL_SEC: float = 0.2

# Tick rate while engaged — faster so re-aim reacts quickly to mob walks.
ENGAGED_POLL_SEC: float = 0.05

# Throttle for the "no candidates visible" log line.
NO_CANDIDATE_LOG_INTERVAL_SEC: float = 5.0

# HP-snapshot INFO cadence (diagnostic line showing what the heal
# policy currently sees).
HP_SNAPSHOT_INTERVAL_SEC: float = 5.0
