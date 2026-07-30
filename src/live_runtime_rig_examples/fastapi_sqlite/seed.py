"""Optional explicit setup command for the toy database."""

from __future__ import annotations

import argparse
from pathlib import Path

from .database import initialize_database


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("var/work_orders.db"))
    args = parser.parse_args()
    initialize_database(args.database.resolve())
    print(f"Toy database ready: {args.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
