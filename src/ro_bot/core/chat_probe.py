"""Chat input bar visibility via a bright pixel in the client area."""

from __future__ import annotations

import logging

from ro_bot.core.window import sample_client_pixel_rgb

logger = logging.getLogger(__name__)


def is_chat_input_visible(
    hwnd: int,
    probe_client: tuple[int, int],
    *,
    min_channel: int = 228,
) -> bool | None:
    """Return True when the chat bar looks open, False when closed, None on probe failure."""
    rgb = sample_client_pixel_rgb(hwnd, probe_client[0], probe_client[1])
    if rgb is None:
        logger.warning(
            "Chat probe: GetPixel failed at client=%s",
            probe_client,
        )
        return None
    visible = max(rgb) >= min_channel
    logger.debug(
        "Chat probe client=%s RGB=%s max=%d thr=%d visible=%s",
        probe_client, rgb, max(rgb), min_channel, visible,
    )
    return visible
