"""HID-layer errors surfaced to hunt policies."""


class RightClickUnavailable(RuntimeError):
    """The serial bridge cannot emit a right mouse button (firmware gap)."""


class HidTransportError(RuntimeError):
    """USB-serial to the HID bridge is gone (disconnect, driver fault, …)."""
