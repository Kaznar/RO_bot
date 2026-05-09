"""HID-layer errors surfaced to hunt policies."""


class RightClickUnavailable(RuntimeError):
    """The serial bridge cannot emit a right mouse button (firmware gap)."""
