"""Town-side inventory / restock before :class:`FarmHomeRoutePolicy`.

World ``click_cell`` (projection), optional ``click_client`` / ``drag_to_client``
(client pixels for HUD), optional repeated LMB **map drags**
(``click_cell`` → ``click_cell_drag_to``), :meth:`HidBridge.press_key`,
modifier chords, and optional mouse-button bursts while modifiers are held.
Optionally waits for ``weight/weight_max``, then ``post_steps``.

Chat / Space: put ``dismiss_chat_probe_client`` on the specific ``HomePrepStep``
that sends ``space`` — the probe runs at step start (see :class:`HomePrepStep`).
"""

from __future__ import annotations

import logging
import time

from ro_bot.core.hid.bridge import HidBridge
from ro_bot.core.hid.exceptions import RightClickUnavailable
from ro_bot.core.memory.player_state import PlayerReader
from ro_bot.core.window import sample_client_pixel_rgb
from ro_bot.hunt.aim_service import AimService
from ro_bot.hunt.config import HomePrepStep, ReturnToFarmConfig

logger = logging.getLogger("ro_bot.hunt")


class HomePrepPolicy:
    """Blocks farm-home waypoint clicks until configured steps finish."""

    def __init__(
        self,
        cfg: ReturnToFarmConfig,
        bridge: HidBridge,
        player_reader: PlayerReader,
        aim: AimService,
        *,
        game_hwnd: int | None = None,
    ) -> None:
        prep = cfg.home_prep
        if prep is None:
            raise ValueError("HomePrepPolicy requires ReturnToFarmConfig.home_prep")
        if cfg.home_route is None:
            raise ValueError("HomePrepPolicy requires ReturnToFarmConfig.home_route")
        self._rtf = cfg
        self._prep = prep
        self._bridge = bridge
        self._player_reader = player_reader
        self._aim = aim
        self._game_hwnd = game_hwnd
        self._completed = False
        self._run_started_at: float | None = None
        self._wait_until = 0.0
        self._idx = 0
        self._post_phase = False
        self._post_idx = 0
        #: Consecutive ``_apply_step`` failures (reset on success).
        self._apply_failures = 0
        self._rmb_unavailable_logged = False
        self._dismiss_chat_probe_no_hwnd_logged = False
        #: When False, standing on ``home_map`` at hunt start does not run prep;
        #: set True by :meth:`arm_restock` or by the controller on town arrival
        #: (farm/other map → ``home_map``), e.g. after butterfly wing ``h`` or
        #: a ``death_return`` warp.
        self._restock_armed: bool = False

    def arm_restock(self) -> None:
        """Allow the prep sequence to run on the next ticks while on ``home_map``."""
        if self._restock_armed:
            return
        self._restock_armed = True
        logger.info("Home prep: restock armed")

    @property
    def run_started(self) -> bool:
        """True once the first prep step has begun on a valid town map."""
        return self._run_started_at is not None

    @property
    def run_finished(self) -> bool:
        """True when prep completed, timed out, or was disabled mid-run."""
        return self._completed

    def suppress_farm_home_route_navigation(self, current_map: str) -> bool:
        prep = self._prep
        if not prep.enabled or not prep.steps:
            return False
        return self._context_ok(current_map) and not self._completed

    def shift(self, delta: float) -> None:
        if self._run_started_at is not None:
            self._run_started_at += delta
            self._wait_until += delta

    def _maybe_dismiss_chat_focus(
        self, step: HomePrepStep, tag: str, idx: int, total: int,
    ) -> None:
        xy = step.dismiss_chat_probe_client
        if xy is None:
            return
        if self._game_hwnd is None:
            if not self._dismiss_chat_probe_no_hwnd_logged:
                self._dismiss_chat_probe_no_hwnd_logged = True
                logger.warning(
                    "Home prep: %s step %d/%d chat probe skipped "
                    "(no game hwnd — dismiss_chat_probe_client ignored)",
                    tag, idx + 1, total,
                )
            return
        rgb = sample_client_pixel_rgb(self._game_hwnd, xy[0], xy[1])
        if rgb is None:
            logger.warning(
                "Home prep: %s step %d/%d chat probe: GetPixel failed at client=%s",
                tag, idx + 1, total, xy,
            )
            return
        mx = max(rgb)
        thr = step.dismiss_chat_min_channel
        if mx >= thr:
            key = step.dismiss_chat_key or "escape"
            self._bridge.press_key(key)
            time.sleep(0.07)
            logger.info(
                "Home prep: %s step %d/%d chat probe client=%s RGB=%s "
                "max=%d >= %d — pressed %r",
                tag, idx + 1, total, xy, rgb, mx, thr, key,
            )
        else:
            logger.info(
                "Home prep: %s step %d/%d chat probe client=%s RGB=%s "
                "max=%d < %d — no %r (if chat was open, lower threshold or "
                "move pixel into white input bar; GPU clients need BitBlt path)",
                tag, idx + 1, total, xy, rgb, mx, thr,
                step.dismiss_chat_key or "escape",
            )

    def _apply_step(self, step: HomePrepStep, idx: int, total: int, tag: str) -> bool:
        try:
            self._maybe_dismiss_chat_focus(step, tag, idx, total)
            if step.drag_to_client is not None:
                if step.click_client is None:
                    logger.error(
                        "Home prep: %s step %d/%d drag_to_client requires "
                        "click_client (drag start)",
                        tag, idx + 1, total,
                    )
                    return False
                st = self._player_reader.read()
                pc = (st.x, st.y)
                if pc == (0, 0):
                    return False
                self._aim.drag_client_pixels(
                    step.click_client,
                    step.drag_to_client,
                )
                logger.info(
                    "Home prep: %s step %d/%d drag_client %s → %s player=%s",
                    tag, idx + 1, total,
                    step.click_client, step.drag_to_client, pc,
                )
            elif step.click_client is not None:
                st = self._player_reader.read()
                pc = (st.x, st.y)
                if pc == (0, 0):
                    return False
                self._aim.click_client_pixel(step.click_client)
                logger.info(
                    "Home prep: %s step %d/%d click_client=%s player=%s",
                    tag, idx + 1, total, step.click_client, pc,
                )
            elif step.click_cell is not None:
                st = self._player_reader.read()
                pc = (st.x, st.y)
                if pc == (0, 0):
                    return False
                if (
                    step.click_cell_drag_to is not None
                    and step.click_cell_drag_repeat_count > 0
                ):
                    n = step.click_cell_drag_repeat_count
                    gap = max(0.0, step.click_cell_drag_repeat_interval_sec)
                    for rep in range(n):
                        st2 = self._player_reader.read()
                        pc2 = (st2.x, st2.y)
                        if pc2 == (0, 0):
                            return False
                        try:
                            self._aim.drag_map_cells(
                                pc2,
                                step.click_cell,
                                step.click_cell_drag_to,
                                settle_before_down_sec=0.09,
                                segment_pause_sec=0.014,
                            )
                        except Exception:
                            logger.exception(
                                "Home prep: %s step %d/%d map_drag rep %d/%d "
                                "failed — aborting step (no key)",
                                tag, idx + 1, total, rep + 1, n,
                            )
                            return False
                        if step.key:
                            time.sleep(0.22)
                            if step.hold_modifiers:
                                self._bridge.press_key_with_modifiers(
                                    step.hold_modifiers,
                                    step.key,
                                )
                            else:
                                self._bridge.press_key(step.key)
                            logger.debug(
                                "Home prep: %s step %d/%d key=%r after "
                                "map_drag rep %d/%d",
                                tag, idx + 1, total, step.key, rep + 1, n,
                            )
                        if rep + 1 < n:
                            time.sleep(gap)
                    logger.info(
                        "Home prep: %s step %d/%d map_drag %s → %s x%d "
                        "interval=%.2fs key=%r each rep last_player=%s",
                        tag, idx + 1, total,
                        step.click_cell, step.click_cell_drag_to, n, gap,
                        step.key or "", pc2,
                    )
                else:
                    self._aim.aim_and_click(
                        pc,
                        step.click_cell,
                        aim_settle_sec=0.08,
                    )
                    logger.info(
                        "Home prep: %s step %d/%d click_cell=%s player=%s",
                        tag, idx + 1, total, step.click_cell, pc,
                    )
            if step.modifier_hold_clicks > 0:
                if not step.hold_modifiers:
                    logger.error(
                        "Home prep: %s step %d/%d modifier_hold_clicks "
                        "requires hold_modifiers",
                        tag, idx + 1, total,
                    )
                    return False
                if step.key:
                    logger.error(
                        "Home prep: %s step %d/%d modifier_hold_clicks "
                        "cannot combine with key=",
                        tag, idx + 1, total,
                    )
                    return False
                btn = (step.modifier_hold_mouse_button or "left").lower()
                if btn not in ("left", "right"):
                    logger.error(
                        "Home prep: %s step %d/%d invalid "
                        "modifier_hold_mouse_button=%r",
                        tag, idx + 1, total, step.modifier_hold_mouse_button,
                    )
                    return False
                for m in step.hold_modifiers:
                    self._bridge.key_down(m)
                    time.sleep(0.012)
                # Give the OS/client time to see modifier before first click.
                time.sleep(0.06)
                n = step.modifier_hold_clicks
                gap = max(0.0, step.modifier_hold_click_interval_sec)
                click_fn = (
                    self._bridge.mouse_right_click
                    if btn == "right"
                    else self._bridge.mouse_click
                )
                try:
                    for i in range(n):
                        click_fn()
                        if i + 1 < n:
                            time.sleep(gap)
                            # Some HID firmware clears keyboard modifiers on mouse
                            # button up (e.g. after RU); re-assert before next click.
                            for m in step.hold_modifiers:
                                self._bridge.key_down(m)
                                time.sleep(0.008)
                finally:
                    for m in reversed(step.hold_modifiers):
                        self._bridge.key_up(m)
                        time.sleep(0.012)
                logger.info(
                    "Home prep: %s step %d/%d modifier_hold %s x%d "
                    "interval=%.2fs modifiers=%s",
                    tag, idx + 1, total, btn, n, gap, step.hold_modifiers,
                )
            if step.key:
                map_drag_key_done = (
                    step.click_cell is not None
                    and step.click_cell_drag_to is not None
                    and step.click_cell_drag_repeat_count > 0
                )
                if not map_drag_key_done:
                    if step.hold_modifiers:
                        self._bridge.press_key_with_modifiers(
                            step.hold_modifiers,
                            step.key,
                        )
                        logger.info(
                            "Home prep: %s step %d/%d modifiers=%s key=%r",
                            tag, idx + 1, total,
                            step.hold_modifiers, step.key,
                        )
                    else:
                        self._bridge.press_key(step.key)
                        logger.info(
                            "Home prep: %s step %d/%d key=%r",
                            tag, idx + 1, total, step.key,
                        )
            elif (
                not step.key
                and step.click_cell is None
                and step.click_client is None
                and step.drag_to_client is None
                and step.modifier_hold_clicks <= 0
                and step.dismiss_chat_probe_client is None
            ):
                logger.info(
                    "Home prep: %s step %d/%d (delay only) %.1fs",
                    tag, idx + 1, total, step.delay_after_sec,
                )
        except RightClickUnavailable as exc:
            if not self._rmb_unavailable_logged:
                self._rmb_unavailable_logged = True
                logger.error(
                    "Home prep: %s step %d/%d — %s",
                    tag, idx + 1, total, exc,
                )
            self._apply_failures = max(self._apply_failures, 24)
            return False
        except Exception:
            logger.exception(
                "Home prep: %s step %d/%d failed",
                tag, idx + 1, total,
            )
            return False
        return True

    def _enter_post_or_finish(self, now: float) -> None:
        prep = self._prep
        if prep.post_steps:
            self._post_phase = True
            self._post_idx = 0
            self._wait_until = now
            logger.info(
                "Home prep: starting %d post_step(s)",
                len(prep.post_steps),
            )
        else:
            logger.info("Home prep: finished")
            self._completed = True

    def tick(self, now: float, current_map: str) -> None:
        prep = self._prep
        if not prep.enabled or not prep.steps:
            self._completed = True
            return

        if not self._context_ok(current_map):
            self._reset_run()
            return

        if self._completed:
            return

        if not self._restock_armed:
            return

        if self._run_started_at is None:
            self._run_started_at = now
            self._wait_until = now
            logger.info(
                "Home prep: started (%d step(s), %d post_step(s))",
                len(prep.steps),
                len(prep.post_steps),
            )

        assert self._run_started_at is not None
        if now - self._run_started_at > prep.max_total_sec:
            logger.warning(
                "Home prep: timeout (%.1fs) — continuing farm route",
                prep.max_total_sec,
            )
            self._completed = True
            return

        if self._post_phase:
            pp = prep.post_steps
            pn = len(pp)
            if self._post_idx < pn:
                if now < self._wait_until:
                    return
                step_p = pp[self._post_idx]
                if not self._apply_step(step_p, self._post_idx, pn, "post"):
                    self._wait_until = now + 0.35
                    self._apply_failures += 1
                    if self._apply_failures >= 25:
                        logger.error(
                            "Home prep: too many step failures — aborting",
                        )
                        self._completed = True
                    return
                self._apply_failures = 0
                self._wait_until = now + max(0.0, step_p.delay_after_sec)
                self._post_idx += 1
                return
            logger.info("Home prep: finished")
            self._completed = True
            return

        n = len(prep.steps)
        if self._idx < n:
            if now < self._wait_until:
                return
            step = prep.steps[self._idx]
            if not self._apply_step(step, self._idx, n, "main"):
                self._wait_until = now + 0.35
                self._apply_failures += 1
                if self._apply_failures >= 25:
                    logger.error(
                        "Home prep: too many step failures — aborting",
                    )
                    self._completed = True
                return
            self._apply_failures = 0
            self._wait_until = now + max(0.0, step.delay_after_sec)
            self._idx += 1
            return

        if now < self._wait_until:
            return

        thr = prep.finish_when_weight_ratio_below
        if thr > 0:
            st = self._player_reader.read()
            if st.weight_max <= 0:
                logger.warning(
                    "Home prep: weight_max unavailable — finishing prep",
                )
                self._completed = True
                return
            ratio = st.weight / st.weight_max
            if ratio < thr:
                logger.info(
                    "Home prep: weight OK (%.1f%% < %.0f%%)",
                    100.0 * ratio, 100.0 * thr,
                )
                self._enter_post_or_finish(now)
                return
            return

        self._enter_post_or_finish(now)

    def _context_ok(self, current_map: str) -> bool:
        hr = self._rtf.home_route
        if hr is None or not hr.enabled:
            return False
        farm = (self._rtf.active_farm_map or "").strip()
        if not farm:
            return False
        return current_map == hr.home_map and current_map != farm

    def _reset_run(self) -> None:
        self._completed = False
        self._run_started_at = None
        self._wait_until = 0.0
        self._idx = 0
        self._post_phase = False
        self._post_idx = 0
        self._apply_failures = 0
        self._rmb_unavailable_logged = False
        self._dismiss_chat_probe_no_hwnd_logged = False
        self._restock_armed = False
