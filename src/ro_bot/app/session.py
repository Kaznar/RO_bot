"""Bot session — wires a :class:`Profile` to live core + hunt objects.

Responsibilities:

  * build every core object (HID bridge, sniffer, memory reader,
    entity tracker, aim service) using parameters from the profile +
    server,
  * derive the hunt :class:`HuntConfig` from the profile,
  * expose ``start()`` / ``stop()`` and a fully-assembled
    :class:`HuntController`.

Takes the two layers' models and gives the runner a single object to
drive. No config-file reading, no argparse — those live in
:mod:`runner` and :mod:`cli`.
"""

from __future__ import annotations

import dataclasses
import logging
from contextlib import ExitStack

from ro_bot.app.models.profile import Profile
from ro_bot.core.hid.arduino import ArduinoHidBridge
from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.memory.player_state import PlayerReader
from ro_bot.core.network.sniffer import PacketSniffer
from ro_bot.core.tracking.entity_tracker import EntityTracker
from ro_bot.core.window import (
    MouseAcceleration,
    WindowRect,
    get_client_rect,
    wait_for_game_window,
)
from ro_bot.hunt.aim_service import AimService
from ro_bot.hunt.config import HuntConfig
from ro_bot.hunt.controller import HuntController
from ro_bot.hunt.policies.home_prep import HomePrepPolicy
from ro_bot.hunt.routes import augment_return_to_farm_from_registry
from ro_bot.hunt.dead_zones.filter import DeadZoneFilter

logger = logging.getLogger(__name__)


class BotSession:
    """All the state a single ``ro-bot hunt`` invocation needs.

    Lifecycle::

        session = BotSession(profile)
        session.start()
        try:
            run_hunt_loop(session.controller, ...)
        finally:
            session.stop()
    """

    def __init__(
        self,
        profile: Profile,
        *,
        hunt_all: bool = False,
        selected_mobs: list[str] | None = None,
    ) -> None:
        self._profile = profile
        self._hunt_all = hunt_all
        self._selected_mobs = (
            frozenset(selected_mobs) if selected_mobs else None
        )
        self._stack = ExitStack()
        if self._hunt_all and self._selected_mobs is not None:
            raise ValueError("hunt_all and selected_mobs cannot be combined")

        # Populated by start(); None between __init__ and start().
        self._bridge: HidBridge | None = None
        self._sniffer: PacketSniffer | None = None
        self._player_reader: PlayerReader | None = None
        self._tracker: EntityTracker | None = None
        self._controller: HuntController | None = None
        self._rect: WindowRect | None = None
        self._hwnd: int | None = None

    @property
    def controller(self) -> HuntController:
        if self._controller is None:
            raise RuntimeError("BotSession not started")
        return self._controller

    @property
    def rect(self) -> WindowRect:
        if self._rect is None:
            raise RuntimeError("BotSession not started")
        return self._rect

    @property
    def sniffer(self) -> PacketSniffer:
        if self._sniffer is None:
            raise RuntimeError("BotSession not started")
        return self._sniffer

    @property
    def player_reader(self) -> PlayerReader:
        if self._player_reader is None:
            raise RuntimeError("BotSession not started")
        return self._player_reader

    @property
    def hunt_config(self) -> HuntConfig:
        """Effective :class:`HuntConfig` (same as :class:`HuntController` uses)."""
        return self._build_hunt_config()

    def make_home_prep_policy(
        self,
        *,
        force_enabled: bool = False,
    ) -> HomePrepPolicy | None:
        """Same prep policy wiring as :class:`HuntController` (standalone ``home-prep``)."""
        if self._bridge is None or self._rect is None or self._player_reader is None:
            raise RuntimeError("BotSession not started")
        cfg = self._build_hunt_config()
        aim = AimService(
            bridge=self._bridge,
            projection=self._profile.server.projection,
            rect=self._rect,
            aim_settle_sec=cfg.engagement.aim_settle_sec,
            aim_offsets=cfg.aim_offsets,
        )
        return HuntController.make_home_prep_policy(
            cfg, self._bridge, self._player_reader, aim,
            force_enabled=force_enabled,
            game_hwnd=self._hwnd,
        )

    # ── Lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """Bring all components up. Raises on any init failure."""
        logger.info(
            "Starting session for char '%s' on server '%s'",
            self._profile.char_name, self._profile.server.name,
        )

        self._rect = self._resolve_window()
        self._stack.callback(self._clear_window)

        self._bridge = self._start_bridge(self._rect)
        self._sniffer = self._start_sniffer()
        self._player_reader = self._start_memory()

        assert self._player_reader is not None
        # Filter scanner queue to whitelisted mobs only. Non-allowed
        # entities (Plants, NPCs, mobs of other classes) would otherwise
        # consume scanner time (~1.3 s each, single-threaded) and starve
        # us of allowed-mob positions for 5–8 s after a teleport burst.
        # ``frozenset`` is captured by reference; the closure is called
        # on the sniffer thread.
        if self._hunt_all:
            should_track = None
        else:
            allowed = (
                self._selected_mobs
                if self._selected_mobs is not None
                else self._profile.allowed_mobs
            )
            should_track = lambda _gid, name: name in allowed
        self._tracker = EntityTracker(
            self._player_reader.process,
            self._sniffer,
            should_track=should_track,
        )
        self._tracker.start()
        self._stack.callback(self._tracker.stop)

        self._controller = self._build_controller(
            self._rect, self._bridge, self._sniffer,
            self._player_reader, self._tracker,
        )

    def stop(self) -> None:
        """Tear everything down in reverse order. Idempotent."""
        self._stack.close()
        self._controller = None
        self._tracker = None
        self._player_reader = None
        self._sniffer = None
        self._bridge = None
        self._rect = None

    # ── Build steps ─────────────────────────────────────────────────

    def _resolve_window(self) -> WindowRect:
        self._hwnd = wait_for_game_window(
            self._profile.server.window_title, timeout=120.0,
        )
        rect = get_client_rect(self._hwnd)

        mouse_accel = MouseAcceleration()
        mouse_accel.disable()
        self._stack.callback(mouse_accel.restore)
        return rect

    def _clear_window(self) -> None:
        # Placeholder for future window-specific cleanup.
        self._rect = None
        self._hwnd = None

    def _start_bridge(self, rect: WindowRect) -> HidBridge:
        bridge = ArduinoHidBridge()
        bridge.connect()
        self._stack.callback(bridge.disconnect)
        # Screen dims: use the virtual screen covered by the client area.
        bridge.set_screen_size(rect.width, rect.height)
        return bridge

    def _start_sniffer(self) -> PacketSniffer:
        sniffer = PacketSniffer(
            process_name=self._profile.server.process_name,
        )
        sniffer.set_char_name(self._profile.char_name)
        if not sniffer.connect():
            raise RuntimeError("Sniffer failed to connect")
        self._stack.callback(sniffer.disconnect)
        return sniffer

    def _start_memory(self) -> PlayerReader:
        reader = PlayerReader(
            process_name=self._profile.server.process_name,
            char_name=self._profile.char_name,
        )
        if not reader.connect():
            raise RuntimeError("PlayerReader failed to connect")
        self._stack.callback(reader.disconnect)
        return reader

    def _build_controller(
        self,
        rect: WindowRect,
        bridge: HidBridge,
        sniffer: PacketSniffer,
        player_reader: PlayerReader,
        tracker: EntityTracker,
    ) -> HuntController:
        cfg = self._build_hunt_config()
        aim = AimService(
            bridge=bridge,
            projection=self._profile.server.projection,
            rect=rect,
            aim_settle_sec=cfg.engagement.aim_settle_sec,
            aim_offsets=cfg.aim_offsets,
        )
        dead_zone_filter = DeadZoneFilter(
            zones=cfg.dead_zones,
            projection=self._profile.server.projection,
            rect=rect,
        )
        return HuntController(
            cfg=cfg,
            bridge=bridge,
            sniffer=sniffer,
            tracker=tracker,
            player_reader=player_reader,
            aim=aim,
            dead_zone_filter=dead_zone_filter,
            game_hwnd=self._hwnd,
        )

    def _build_hunt_config(self) -> HuntConfig:
        p = self._profile
        cfg = HuntConfig(
            char_name=p.char_name,
            allowed_names=(
                self._selected_mobs
                if self._selected_mobs is not None
                else p.allowed_mobs
            ),
            dangerous_names=p.dangerous_mobs,
            manual_control_maps=p.manual_control_maps,
            dead_zones=p.server.dead_zones,
            aim_offsets=p.aim_offsets,
            engagement=p.engagement,
            heal=p.heal,
            idle_action=p.idle_action,
            overweight=p.overweight,
            escape=p.escape,
            return_to_farm=augment_return_to_farm_from_registry(
                p.return_to_farm,
            ),
            buffs=p.buffs,
        )
        if self._hunt_all:
            return dataclasses.replace(
                cfg,
                target_all_mobs=True,
                ignore_map_restrictions=True,
                return_to_farm=None,
            )
        return cfg
