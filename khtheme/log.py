"""Structured JSON logging shared by the build and install tools.

Every record is one JSON object per line on stderr so that stdout stays free
for machine-readable results (paths, summaries).
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import sys
import time
import traceback
import uuid

LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}

# One id per process invocation ties all records of a build/install run together.
RUN_ID = uuid.uuid4().hex[:12]


def _threshold() -> int:
    raw = os.environ.get("KH_LOG_LEVEL", "info").lower()
    if raw not in LEVELS:
        sys.stderr.write(
            json.dumps(
                {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "level": "warn",
                    "context": "log",
                    "message": "invalid KH_LOG_LEVEL, falling back to info",
                    "value": raw,
                    "run_id": RUN_ID,
                }
            )
            + "\n"
        )
        return LEVELS["info"]
    return LEVELS[raw]


_THRESHOLD = _threshold()


def log(level: str, context: str, message: str, error: BaseException | None = None, **fields) -> None:
    if LEVELS[level] < _THRESHOLD:
        return
    record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "level": level,
        "context": context,
        "message": message,
        "run_id": RUN_ID,
    }
    if error is not None:
        record["error"] = f"{type(error).__name__}: {error}"
        record["stack"] = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    record.update(fields)
    sys.stderr.write(json.dumps(record, default=str) + "\n")


def debug(context: str, message: str, **fields) -> None:
    log("debug", context, message, **fields)


def info(context: str, message: str, **fields) -> None:
    log("info", context, message, **fields)


def warn(context: str, message: str, error: BaseException | None = None, **fields) -> None:
    log("warn", context, message, error=error, **fields)


def error(context: str, message: str, error: BaseException | None = None, **fields) -> None:
    log("error", context, message, error=error, **fields)


@contextlib.contextmanager
def timed(context: str, message: str, **fields):
    """Log start/finish (with duration) of a step; log and re-raise on failure."""
    start = time.monotonic()
    debug(context, f"{message}: started", **fields)
    try:
        yield
    except Exception as exc:
        error(
            context,
            f"{message}: failed",
            error=exc,
            duration_ms=round((time.monotonic() - start) * 1000, 1),
            **fields,
        )
        raise
    info(context, f"{message}: done", duration_ms=round((time.monotonic() - start) * 1000, 1), **fields)
