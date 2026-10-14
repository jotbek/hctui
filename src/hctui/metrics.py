"""Cached metric snapshots, independent cadences, and bounded background probes."""

from __future__ import annotations

import os
import time
from collections import deque
from pathlib import Path
from typing import NamedTuple, Protocol

import psutil

from .health import AlertMetrics, MonitorMetrics, MonitorSnapshot, Telemetry
from .sampling import BackgroundSampler, CommandRunner
from .system_metrics import (
    EMPTY,
    FilesystemMetrics,
    LoadMetrics,
    ProcessMetrics,
    ServiceMetrics,
    SystemMetrics,
    TemperatureMetrics,
    WifiMetrics,
    validate_services,
)

CORE_SOURCES = frozenset({"cpu", "memory", "network", "disk"})
SOURCE_NAMES = CORE_SOURCES | frozenset(
    {
        "load",
        "temperature",
        "system",
        "processes",
        "filesystems",
        "services",
        "wifi",
        "monitor",
        "alerts",
    }
)
INTERVALS = {
    "cpu": 1.0,
    "memory": 2.0,
    "network": 1.0,
    "disk": 5.0,
    "load": 2.0,
    "temperature": 5.0,
    "system": 30.0,
    "processes": 5.0,
    "filesystems": 10.0,
    "services": 10.0,
    "wifi": 10.0,
    "monitor": 5.0,
}
BACKGROUND_SOURCES = frozenset(
    {"temperature", "system", "processes", "filesystems", "services", "wifi"}
)


class CpuSnapshot(NamedTuple):
    usage: float
    per_core: tuple[float, ...]
    physical_count: int | None
    frequency_mhz: float | None
    history: tuple[float, ...]

    @property
    def rows(self):
        return tuple(
            (str(index), f"{value:.1f}%") for index, value in enumerate(self.per_core[:128])
        )


class MemorySnapshot(NamedTuple):
    total: int
    used: int
    available: int
    usage: float
    swap_total: int
    swap_used: int
    swap_usage: float


class NetworkSnapshot(NamedTuple):
    interface: str
    download_rate: float
    upload_rate: float
    download_history: tuple[float, ...]
    upload_history: tuple[float, ...]
    history_max: float


class DiskSnapshot(NamedTuple):
    path: str
    total: int
    used: int
    free: int
    usage: float
    read_rate: float
    write_rate: float


class MetricProvider(Protocol):
    def sample(self, now: float) -> object:
        """Collect one non-blocking metric snapshot."""


class CounterRates:
    """Calculate rates from successive counters using monotonic timestamps."""

    def __init__(self) -> None:
        self._previous: tuple[str, float, tuple[int, int]] | None = None

    @property
    def identity(self) -> str | None:
        return self._previous[0] if self._previous is not None else None

    def update(self, identity: str, now: float, counters: tuple[int, int]) -> tuple[float, float]:
        previous = self._previous
        self._previous = (identity, now, counters)
        if previous is None or previous[0] != identity or now <= previous[1]:
            return 0.0, 0.0
        elapsed = now - previous[1]
        return (
            max(0, counters[0] - previous[2][0]) / elapsed,
            max(0, counters[1] - previous[2][1]) / elapsed,
        )


class CpuMetrics:
    """Measure all logical CPUs once per refresh; cache slower metadata reads."""

    def __init__(self, history_size: int) -> None:
        self._history = deque([0.0] * history_size, maxlen=history_size)
        self._physical_count = psutil.cpu_count(logical=False)
        self._frequency: float | None = None
        self._next_frequency_read = 0.0
        self._primed = False

    def sample(self, now: float) -> CpuSnapshot:
        per_core = tuple(psutil.cpu_percent(interval=None, percpu=True))
        usage = psutil.cpu_percent(interval=None)
        if not self._primed:
            per_core = (0.0,) * (len(per_core) or os.cpu_count() or 1)
            usage = 0.0
            self._primed = True
        if not per_core:
            per_core = (usage,)
        if now >= self._next_frequency_read:
            try:
                frequency = psutil.cpu_freq()
                self._frequency = frequency.current if frequency is not None else None
            except (OSError, NotImplementedError, psutil.Error):
                self._frequency = None
            self._next_frequency_read = now + 5.0
        self._history.append(usage)
        return CpuSnapshot(
            usage, per_core, self._physical_count, self._frequency, tuple(self._history)
        )


class MemoryMetrics:
    """Read RAM and swap once per refresh."""

    def sample(self, now: float) -> MemorySnapshot:
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return MemorySnapshot(
            memory.total,
            memory.total - memory.available,
            memory.available,
            memory.percent,
            swap.total,
            swap.used,
            swap.percent,
        )


class NetworkMetrics:
    """Monitor the default IPv4 interface, or all interfaces if none is found."""

    def __init__(self, history_size: int, route_path: Path = Path("/proc/net/route")) -> None:
        self._route_path = route_path
        self._interface: str | None = None
        self._next_route_read = 0.0
        self._rates = CounterRates()
        self._download = deque([0.0] * history_size, maxlen=history_size)
        self._upload = deque([0.0] * history_size, maxlen=history_size)

    def _read_interface(self) -> str | None:
        try:
            lines = self._route_path.read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            return None
        routes = []
        for line in lines:
            fields = line.split()
            if len(fields) < 8 or fields[1] != "00000000":
                continue
            try:
                if int(fields[3], 16) & 1:
                    routes.append((int(fields[6]), fields[0]))
            except ValueError:
                continue
        return min(routes)[1] if routes else None

    def sample(self, now: float) -> NetworkSnapshot:
        counters = psutil.net_io_counters(pernic=True, nowrap=False)
        if now >= self._next_route_read or (
            self._interface is not None and self._interface not in counters
        ):
            self._interface = self._read_interface()
            self._next_route_read = now + 10.0
        if self._interface in counters:
            current = counters[self._interface]
            label = identity = self._interface
            totals = (current.bytes_recv, current.bytes_sent)
        else:
            label = "All interfaces"
            identity = "all:" + ",".join(sorted(counters))
            totals = (
                sum(counter.bytes_recv for counter in counters.values()),
                sum(counter.bytes_sent for counter in counters.values()),
            )
        if self._rates.identity is not None and self._rates.identity != identity:
            self._download.clear()
            self._upload.clear()
            self._download.extend([0.0] * self._download.maxlen)
            self._upload.extend([0.0] * self._upload.maxlen)
        download, upload = self._rates.update(identity, now, totals)
        self._download.append(download)
        self._upload.append(upload)
        download_history, upload_history = tuple(self._download), tuple(self._upload)
        return NetworkSnapshot(
            label,
            download,
            upload,
            download_history,
            upload_history,
            max(1.0, max(download_history), max(upload_history)),
        )


class DiskMetrics:
    """Read filesystem capacity and system-wide disk I/O counters."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._rates = CounterRates()

    def sample(self, now: float) -> DiskSnapshot:
        usage = psutil.disk_usage(str(self._path))
        try:
            counters = psutil.disk_io_counters(nowrap=False)
        except (OSError, NotImplementedError):
            counters = None
        totals = (counters.read_bytes, counters.write_bytes) if counters is not None else (0, 0)
        identity = "system-disk-io" if counters is not None else "unavailable"
        read_rate, write_rate = self._rates.update(identity, now, totals)
        return DiskSnapshot(
            str(self._path),
            usage.total,
            usage.used,
            usage.free,
            usage.percent,
            read_rate,
            write_rate,
        )


class MetricSampler:
    """Own independent providers and collect only sources used by the dashboard."""

    def __init__(
        self,
        history_size: int = 60,
        disk_path: Path | None = None,
        services=("ssh.service", "cron.service"),
        temperature_warning=80.0,
    ) -> None:
        if not 1 <= history_size <= 600:
            raise ValueError("History size must be between 1 and 600")
        self._history_size = history_size
        self._disk_path = disk_path or Path(Path.home().anchor)
        self._providers: dict[str, MetricProvider] = {}
        self._intervals = INTERVALS.copy()
        self._next_due = {}
        self._result_seen = {}
        self._collected_at = {}
        self.errors = {}
        self.telemetry = Telemetry()
        self._worker = BackgroundSampler()
        self._runner = CommandRunner()
        self._alerts = AlertMetrics(temperature_warning)
        services = validate_services(services)
        self._cache = {
            **EMPTY,
            "cpu": CpuSnapshot(0, (0,), None, None, ()),
            "memory": MemorySnapshot(0, 0, 0, 0, 0, 0, 0),
            "network": NetworkSnapshot("N/A", 0, 0, (), (), 1),
            "disk": DiskSnapshot(str(self._disk_path), 0, 0, 0, 0, 0, 0),
            "monitor": MonitorSnapshot(0, 0, 0, 0, 0, 0, 0, ()),
        }
        self._factories = {
            "cpu": lambda: CpuMetrics(self._history_size),
            "memory": MemoryMetrics,
            "network": lambda: NetworkMetrics(self._history_size),
            "disk": lambda: DiskMetrics(self._disk_path),
            "load": lambda: LoadMetrics(self._history_size),
            "temperature": lambda: TemperatureMetrics(self._history_size),
            "system": SystemMetrics,
            "processes": lambda: ProcessMetrics(self._worker.closed),
            "filesystems": lambda: FilesystemMetrics(self._disk_path),
            "services": lambda: ServiceMetrics(services, self._runner),
            "wifi": lambda: WifiMetrics(self._runner),
            "monitor": lambda: MonitorMetrics(self.telemetry),
        }

    def configure(self, intervals):
        configured = {**INTERVALS, **intervals}
        for name, interval in configured.items():
            if interval != self._intervals[name]:
                self._next_due[name] = 0
        self._intervals = configured

    def sample(self, sources: frozenset[str] = CORE_SOURCES, *, force=False) -> dict[str, object]:
        unknown = sources - SOURCE_NAMES
        if unknown:
            raise ValueError(f"Unknown metric sources: {', '.join(sorted(unknown))}")
        now = time.monotonic()
        if "alerts" in sources:
            sources = sources | {"cpu", "memory", "disk", "temperature", "services"}
        result = {}
        for name in sorted(sources - {"alerts"}):
            if name not in self._providers:
                self._providers[name] = self._factories[name]()
            if name in BACKGROUND_SOURCES:
                completed = self._worker.result(name)
                if completed and completed.timestamp > self._result_seen.get(name, -1):
                    self._result_seen[name] = completed.timestamp
                    self._next_due[name] = completed.timestamp + max(1, self._intervals[name])
                    if completed.error:
                        self.errors[name] = completed.error
                    else:
                        self._collected_at[name] = completed.timestamp
                        if completed.value != self._cache[name]:
                            self._cache[name] = completed.value
                        self.errors.pop(name, None)
                if now >= self._next_due.get(name, 0):
                    self._worker.submit(name, self._providers[name])
            elif force or now >= self._next_due.get(name, 0):
                try:
                    snapshot = self._providers[name].sample(now)
                    self._collected_at[name] = now
                    if snapshot != self._cache[name]:
                        self._cache[name] = snapshot
                    self.errors.pop(name, None)
                except (OSError, psutil.Error, NotImplementedError) as error:
                    self.errors[name] = str(error)
                self._next_due[name] = now + self._intervals[name]
            result[name] = self._cache[name]
        if "alerts" in sources:
            snapshot = self._alerts.sample(result, now, self.errors)
            if snapshot != self._cache.get("alerts"):
                self._cache["alerts"] = snapshot
            result["alerts"] = self._cache["alerts"]
            self._collected_at["alerts"] = now
        return result

    @property
    def pending_sources(self):
        return self._worker.pending_sources

    def report_metadata(self):
        now = time.monotonic()
        return {
            name: {
                "age_seconds": round(now - self._collected_at[name], 3)
                if name in self._collected_at
                else None,
                "interval_seconds": self._intervals.get(name),
                "status": "error"
                if name in self.errors
                else "ready"
                if name in self._collected_at
                else "not collected",
                "pending": name in self.pending_sources,
                "error": self.errors.get(name, ""),
            }
            for name in sorted(SOURCE_NAMES)
        }

    def record_refresh(self, sample_ms, update_ms, missed):
        self.telemetry.sample_ms = sample_ms
        self.telemetry.update_ms = update_ms
        self.telemetry.refreshes += 1
        self.telemetry.missed += missed

    def record_render(self, milliseconds):
        self.telemetry.render_ms = milliseconds

    def close(self):
        self._runner.close()
        self._worker.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
