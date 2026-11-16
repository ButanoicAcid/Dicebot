from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

MAX_AGE = timedelta(days=7)


def prune_directory(directory: Path, logger: logging.Logger) -> int:

    if not directory.exists():
        return 0

    now = datetime.now(UTC)
    removed = 0

    for path in directory.iterdir():
        try:
            if not path.is_file():
                continue

            modified = datetime.fromtimestamp(
                path.stat().st_mtime,
                tz=UTC,
            )

            if now - modified < MAX_AGE:
                continue

            path.unlink(missing_ok=True)
            removed += 1
        except Exception as e:
            logger.exception(f"Error while removing file (path {path}): {e}")

    return removed
