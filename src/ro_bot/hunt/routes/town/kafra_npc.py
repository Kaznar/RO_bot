"""Town Kafra NPC — world ``click_cell`` only; storage/warp key flow per town."""

from __future__ import annotations

from dataclasses import dataclass

from ro_bot.hunt.config import HomePrepStep


@dataclass
class Kafra:
    """Kafra worker. Client HUD (tabs, storage grid) lives in :mod:`storage_hud`."""

    npc_cell: tuple[int, int]
    default_click_delay_sec: float = 1.43
    storage_key_delay_sec: float = 1.0

    def npc_click(
        self,
        *,
        delay_after_sec: float | None = None,
    ) -> HomePrepStep:
        return HomePrepStep(
            click_cell=self.npc_cell,
            key="",
            delay_after_sec=(
                delay_after_sec
                if delay_after_sec is not None
                else self.default_click_delay_sec
            ),
        )

    def npc_click_repeat(
        self,
        times: int,
        *,
        delay_after_each_sec: float,
    ) -> tuple[HomePrepStep, ...]:
        return tuple(
            self.npc_click(delay_after_sec=delay_after_each_sec)
            for _ in range(max(1, times))
        )

    def open_storage_menu_steps(self) -> tuple[HomePrepStep, ...]:
        """Talk → Service → Storage (same key rhythm as historic Comodo)."""
        return (
            self.npc_click(),
            HomePrepStep(key="enter", delay_after_sec=self.storage_key_delay_sec),
            HomePrepStep(key="down", delay_after_sec=self.storage_key_delay_sec),
            HomePrepStep(key="enter", delay_after_sec=self.storage_key_delay_sec),
            HomePrepStep(key="enter", delay_after_sec=self.storage_key_delay_sec),
        )

    def warp_from_npc_steps(
        self,
        menu_keys: tuple[tuple[str, float], ...],
        *,
        lead_clicks: int = 1,
        click_delay_sec: float | None = None,
    ) -> tuple[HomePrepStep, ...]:
        """Optional repeated LMB on NPC, then teleport menu keys (down/enter…)."""
        delay = (
            click_delay_sec
            if click_delay_sec is not None
            else self.default_click_delay_sec
        )
        burst = self.npc_click_repeat(
            lead_clicks,
            delay_after_each_sec=delay,
        )
        keys = tuple(
            HomePrepStep(key=k, delay_after_sec=d) for k, d in menu_keys
        )
        return burst + keys
