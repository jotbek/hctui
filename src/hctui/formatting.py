"""Formatting helpers shared by widget expressions."""

from __future__ import annotations

import math


def format_bytes(value: float) -> str:
    """Format a non-negative byte count using binary units."""
    value = float(value)
    if not math.isfinite(value):
        return "N/A"
    value = max(0.0, value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"):
        if value < 1024 or unit == "YiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("Unreachable unit")


def format_rate(value: float) -> str:
    """Format a transfer rate in bytes per second."""
    return f"{format_bytes(value)}/s"


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return (
        f"{days}d {hours:02}:{minutes:02}:{seconds:02}"
        if days
        else f"{hours:02}:{minutes:02}:{seconds:02}"
    )


def format_temperature(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1f} C"
