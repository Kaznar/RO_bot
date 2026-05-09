"""Abstract HID bridge protocol.

Defines the minimal surface used by the hunt state machine: relative
mouse moves, a left click, and a single-key tap. Concrete backends
(e.g. Arduino Pro Micro over serial) implement this. Keeping the
protocol narrow makes it easy to swap backends or mock the HID layer
during offline development.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HidBridge(Protocol):
    """Bare minimum of HID operations the hunt loop needs."""

    def connect(self) -> None:
        """Open the underlying transport. Must be called before any
        move/click/press. Raises on failure.
        """

    def disconnect(self) -> None:
        """Close the transport. Idempotent."""

    def set_screen_size(self, screen_w: int, screen_h: int) -> None:
        """Inform the firmware of total screen dimensions (needed by
        some backends to bound relative moves)."""

    def move_mouse(self, dx: int, dy: int) -> None:
        """Emit a relative mouse move (dx, dy) in pixels."""

    def mouse_click(self) -> None:
        """Left button down + up at the current cursor position."""

    def mouse_left_down(self) -> None:
        """Left button down (for drags)."""
        ...

    def mouse_left_up(self) -> None:
        """Left button up (for drags)."""
        ...

    def mouse_right_down(self) -> None:
        """Right button down (for drags / context menu)."""
        ...

    def mouse_right_up(self) -> None:
        """Right button up."""
        ...

    def mouse_right_click(self) -> None:
        """Right button down + up at the current cursor position."""
        ...

    def press_key(self, key: str) -> None:
        """Tap a single key ('a'..'z', '0'..'9', or a named key like
        'space'/'enter')."""

    def press_key_with_modifiers(
        self,
        modifiers: tuple[str, ...],
        key: str,
    ) -> None:
        """Chord: hold ``modifiers``, tap ``key``, release (e.g. Alt+E)."""
        ...

    def key_down(self, key: str) -> None:
        """HID key down (pair with :meth:`key_up` for chords / held modifiers)."""
        ...

    def key_up(self, key: str) -> None:
        """HID key up."""
        ...
