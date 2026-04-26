"""JSON config loading for RO_bot.

Exposes :func:`load_config` and :class:`ConfigError`. The loader
reads a JSON file, validates it, and returns a hydrated
:class:`Profile` (with nested :class:`Server`). On first run, a
default config is written to the target path.
"""

from ro_bot.app.config.loader import ConfigError, load_config

__all__ = ["ConfigError", "load_config"]
