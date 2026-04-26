"""Hydrated server model.

Value class carrying everything hunt needs to know about a given
server + client build: the process / window identifiers, the camera
projection constants and the HUD dead zones.
"""

from __future__ import annotations

from dataclasses import dataclass

from ro_bot.core.projection.camera import CameraProjection
from ro_bot.hunt.dead_zones.zone import DeadZone


@dataclass(frozen=True)
class Server:
    """Everything hunt needs to know about a server+client build."""
    id: int
    name: str
    process_name: str
    window_title: str
    projection: CameraProjection
    dead_zones: tuple[DeadZone, ...]
