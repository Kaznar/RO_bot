#!/usr/bin/env python3
"""Print ``FarmRouteWaypoint`` lines while you walk (memory cell changes).

Run **as Administrator** with the game client focused on your character.
Disable automated home navigation first (``home_navigation_enabled: false``
in ``config.json``), walk the path once manually; copy stdout into
``hunt/routes/segments/*.py``.

Example::

    uv run python scripts/trace_route_waypoints.py \\
        --process nexusro.exe --char JoJo --map comodo

Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process", required=True, help="Client exe name, e.g. nexusro.exe")
    parser.add_argument("--char", required=True, help="Character name (memory anchor)")
    parser.add_argument(
        "--map",
        default="comodo",
        help='Map name label for output only (sniffer not used). Default: "%(default)s"',
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=0.25,
        help="Seconds between memory reads (default %(default)s)",
    )
    args = parser.parse_args()

    from ro_bot.core.memory.player_state import PlayerReader

    reader = PlayerReader(args.process, args.char)
    if not reader.connect():
        print("Failed to connect PlayerReader.", file=sys.stderr)
        return 1

    label = args.map.strip() or "unknown_map"
    last: tuple[int, int] | None = None
    print("# Paste into segment tuple (keep order along your path):", flush=True)
    try:
        while True:
            st = reader.read()
            if st.x == 0 and st.y == 0:
                time.sleep(args.poll)
                continue
            cell = (st.x, st.y)
            if cell != last:
                last = cell
                print(
                    f'            FarmRouteWaypoint("{label}", {cell[0]}, {cell[1]}),',
                    flush=True,
                )
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\n# done", flush=True)
    finally:
        reader.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
