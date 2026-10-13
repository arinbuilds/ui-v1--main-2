"""Wait until PostgreSQL accepts connections (container entrypoint helper)."""
from __future__ import annotations

import sys
import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import engine

MAX_ATTEMPTS = 60


def main() -> int:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"[riskguard] database ready (attempt {attempt})")
            return 0
        except SQLAlchemyError as exc:
            print(f"[riskguard] waiting for database... ({attempt}/{MAX_ATTEMPTS}) {exc.__class__.__name__}")
            time.sleep(2)
    print("[riskguard] database did not become ready in time", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
