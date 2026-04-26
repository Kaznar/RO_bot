"""Enable ``python -m ro_bot ...`` invocation."""

from __future__ import annotations

import sys

from ro_bot.cli import main

if __name__ == "__main__":
    sys.exit(main())
