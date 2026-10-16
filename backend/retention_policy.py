"""Validated retention windows shared by storage, reports, and maintenance."""
from __future__ import annotations

import os


def _integer(name: str, default: int, minimum: int, maximum: int,
             environ: dict[str, str]) -> int:
    raw = environ.get(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def settings(environ: dict[str, str] | None = None) -> dict[str, int]:
    source = os.environ if environ is None else environ
    return {
        "observation_days": _integer("AI26_OBSERVATION_RETENTION_DAYS", 7, 7, 365, source),
        "traffic_days": _integer("AI26_TRAFFIC_RETENTION_DAYS", 90, 7, 365, source),
        "report_hours": _integer("AI26_REPORT_RETENTION_HOURS", 24, 1, 720, source),
    }
