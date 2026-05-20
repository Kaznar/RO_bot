"""Town healer / buffer NPC — world ``click_cell`` only."""

from __future__ import annotations

from dataclasses import dataclass

from ro_bot.hunt.config import HomePrepStep


@dataclass
class Healer:
    npc_cell: tuple[int, int]

    def heal_dialog_steps(
        self,
        *,
        delays_sec: tuple[float, ...] = (1.0, 1.0, 2.0),
    ) -> tuple[HomePrepStep, ...]:
        """``delays_sec``: pause after click, then after each ``enter``."""
        if len(delays_sec) < 2:
            raise ValueError("heal_dialog_steps needs delay after click + at least one key")
        first, *rest = delays_sec
        return (
            HomePrepStep(
                click_cell=self.npc_cell,
                key="enter",
                delay_after_sec=first,
            ),
            *(
                HomePrepStep(key="enter", delay_after_sec=d)
                for d in rest
            ),
        )
