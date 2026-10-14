"""Monitor telemetry and alert transitions derived from shared snapshots."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import NamedTuple

import psutil

from .formatting import format_duration


@dataclass
class Telemetry:
    sample_ms: float = 0.0
    update_ms: float = 0.0
    render_ms: float = 0.0
    refreshes: int = 0
    missed: int = 0


class MonitorSnapshot(NamedTuple):
    cpu_usage: float
    rss: int
    sample_ms: float
    update_ms: float
    render_ms: float
    refreshes: int
    missed: int
    rows: tuple


class MonitorMetrics:
    def __init__(self, telemetry):
        self._telemetry = telemetry
        self._process = psutil.Process()
        self._process.cpu_percent()

    def sample(self, now):
        telemetry = self._telemetry
        cpu = self._process.cpu_percent()
        rss = self._process.memory_info().rss
        rows = (
            ("Sampling", f"{telemetry.sample_ms:.2f} ms"),
            ("Widget updates", f"{telemetry.update_ms:.2f} ms"),
            ("Rendering", f"{telemetry.render_ms:.2f} ms"),
            ("Refreshes", str(telemetry.refreshes)),
            ("Missed periods", str(telemetry.missed)),
        )
        return MonitorSnapshot(
            cpu,
            rss,
            telemetry.sample_ms,
            telemetry.update_ms,
            telemetry.render_ms,
            telemetry.refreshes,
            telemetry.missed,
            rows,
        )


class AlertSnapshot(NamedTuple):
    level: str
    summary: str
    rows: tuple
    events: tuple
    active_count: int


class AlertMetrics:
    """Use hysteresis and a ten-second CPU hold; retain only twenty transitions."""

    def __init__(self, temperature_warning=80.0):
        self._temperature_warning = temperature_warning
        self._states = {}
        self._cpu_since = None
        self._events = deque(maxlen=20)
        self._started = time.monotonic()

    def sample(self, context, now, errors=None):
        readings = []
        for source, warning in (("cpu", 90), ("memory", 90), ("disk", 90)):
            snapshot = context.get(source)
            if snapshot is not None:
                readings.append((source, snapshot.usage, warning, 98, "%"))
        temperature = context.get("temperature")
        if temperature is not None and temperature.current is not None:
            readings.append(
                (
                    "temperature",
                    temperature.current,
                    self._temperature_warning,
                    self._temperature_warning + 5,
                    " C",
                )
            )
        rows = []
        for name, value, warning, critical, unit in readings:
            old = self._states.get(name, "ok")
            if name == "cpu":
                if value >= warning:
                    self._cpu_since = now if self._cpu_since is None else self._cpu_since
                else:
                    self._cpu_since = None
                if old == "ok" and (self._cpu_since is None or now - self._cpu_since < 10):
                    continue
            level = "critical" if value >= critical else "warning" if value >= warning else "ok"
            if old == "critical" and value >= critical - 5:
                level = "critical"
            elif old in {"warning", "critical"} and value >= warning - 5 and level == "ok":
                level = "warning"
            if level != old:
                self._events.appendleft((format_duration(now - self._started), name, level))
            self._states[name] = level
            if level != "ok":
                rows.append((name, level.upper(), f"{value:.1f}{unit}"))
        services = context.get("services")
        if services and services.available:
            old = self._states.get("services", "ok")
            level = "critical" if services.failed else "ok"
            if level != old:
                self._events.appendleft((format_duration(now - self._started), "services", level))
            self._states["services"] = level
            if services.failed:
                rows.append(("services", "CRITICAL", ", ".join(services.failed)))
        elif self._states.get("services") == "critical":
            rows.append(("services", "UNKNOWN", "Monitoring unavailable"))
        if (
            temperature is not None
            and temperature.current is None
            and self._states.get("temperature", "ok") != "ok"
        ):
            rows.append(("temperature", "UNKNOWN", "Sensor unavailable"))
        for source in sorted((errors or {}).keys() & {"cpu", "memory", "disk"}):
            rows = [row for row in rows if row[0] != source]
            rows.append((source, "UNKNOWN", "Last sample unavailable"))
        level = (
            "critical" if any(row[1] == "CRITICAL" for row in rows) else "warning" if rows else "ok"
        )
        return AlertSnapshot(
            level,
            f"{len(rows)} active alerts" if rows else "No active alerts",
            tuple(rows),
            tuple(self._events),
            len(rows),
        )
