"""Optional system, temperature, process, filesystem, service, and Wi-Fi probes."""

from __future__ import annotations

import heapq
import os
import platform
import re
import shutil
import socket
import time
from collections import deque
from pathlib import Path
from typing import NamedTuple

import psutil

from .formatting import format_bytes, format_duration


class LoadSnapshot(NamedTuple):
    one: float
    five: float
    fifteen: float
    normalized: float
    history: tuple
    available: bool = True


class TemperatureSnapshot(NamedTuple):
    current: float | None
    label: str
    rows: tuple
    history: tuple


class SystemSnapshot(NamedTuple):
    hostname: str
    uptime: float
    rows: tuple
    addresses: tuple


class ProcessSnapshot(NamedTuple):
    cpu_rows: tuple
    memory_rows: tuple
    count: int
    scanned: int
    ready: bool


class FilesystemSnapshot(NamedTuple):
    rows: tuple
    count: int
    skipped: int


class ServiceSnapshot(NamedTuple):
    rows: tuple
    failed: tuple
    message: str
    available: bool


class WifiSnapshot(NamedTuple):
    interface: str
    ssid: str
    signal: str
    quality: str
    state: str
    message: str


EMPTY = {
    "load": LoadSnapshot(0, 0, 0, 0, (), False),
    "temperature": TemperatureSnapshot(None, "Loading sensors", (), ()),
    "system": SystemSnapshot("Loading", 0, (), ()),
    "processes": ProcessSnapshot((), (), 0, 0, False),
    "filesystems": FilesystemSnapshot((), 0, 0),
    "services": ServiceSnapshot((), (), "Loading service status", False),
    "wifi": WifiSnapshot("N/A", "N/A", "N/A", "N/A", "unknown", "Loading Wi-Fi status"),
}


class LoadMetrics:
    def __init__(self, history_size):
        self._history = deque(maxlen=history_size)
        self._count = psutil.cpu_count() or 1

    def sample(self, now):
        try:
            one, five, fifteen = os.getloadavg()
        except (AttributeError, OSError):
            return EMPTY["load"]
        normalized = one / self._count * 100
        self._history.append(normalized)
        return LoadSnapshot(one, five, fifteen, normalized, tuple(self._history))


class TemperatureMetrics:
    def __init__(self, history_size):
        self._history = deque(maxlen=history_size)

    def sample(self, now):
        rows, cpu_values, values = [], [], []
        try:
            sensors = psutil.sensors_temperatures()
        except (AttributeError, OSError, NotImplementedError):
            sensors = {}
        for group, entries in sensors.items():
            for sensor in entries:
                if len(rows) >= 16:
                    break
                value = sensor.current
                if value is None or not -30 <= value <= 150:
                    continue
                label = f"{group} {sensor.label}".strip()[:80]
                rows.append((label, f"{value:.1f} C"))
                values.append(value)
                if any(
                    token in group.lower() for token in ("cpu", "core", "k10", "soc", "thermal")
                ):
                    cpu_values.append(value)
        if not values:
            try:
                value = float(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
                if -30 <= value <= 150:
                    rows.append(("SoC", f"{value:.1f} C"))
                    cpu_values.append(value)
                    values.append(value)
            except (OSError, ValueError):
                pass
        current = max(cpu_values or values) if values else None
        if current is not None:
            self._history.append(current)
        label = "CPU/SoC" if cpu_values else "Max sensor" if values else "No sensors available"
        return TemperatureSnapshot(current, label, tuple(rows), tuple(self._history))


class SystemMetrics:
    def __init__(self):
        self._metadata = None

    def sample(self, now):
        if self._metadata is None:
            model = "N/A"
            try:
                model = Path("/proc/device-tree/model").read_text().strip("\x00\n")
            except OSError:
                pass
            os_name = platform.system()
            try:
                for line in Path("/etc/os-release").read_text().splitlines():
                    if line.startswith("PRETTY_NAME="):
                        os_name = line.partition("=")[2].strip('"')
            except OSError:
                pass
            self._metadata = (
                ("Host", socket.gethostname()),
                ("Model", model),
                ("OS", os_name),
                ("Kernel", platform.release()),
                ("Architecture", platform.machine()),
            )
        try:
            uptime = float(Path("/proc/uptime").read_text().split()[0])
        except (OSError, ValueError, IndexError):
            uptime = max(0, time.time() - psutil.boot_time())
        addresses = []
        for interface, entries in psutil.net_if_addrs().items():
            if interface == "lo":
                continue
            for entry in entries:
                if entry.family == socket.AF_INET and len(addresses) < 8:
                    addresses.append((interface, entry.address))
        return SystemSnapshot(
            self._metadata[0][1],
            uptime,
            (self._metadata[0], ("Uptime", format_duration(uptime)), *self._metadata[1:]),
            tuple(addresses),
        )


class ProcessMetrics:
    MAX_PROCESSES = 4096
    TOP_COUNT = 5

    def __init__(self, stop_event):
        self._previous = {}
        self._stop = stop_event

    def sample(self, now):
        pids = psutil.pids()
        previous, cpu_top, memory_top = {}, [], []
        ready = bool(self._previous)
        scanned = 0
        for pid in pids[: self.MAX_PROCESSES]:
            if self._stop.is_set():
                break
            try:
                process = psutil.Process(pid)
                with process.oneshot():
                    identity = (pid, process.create_time())
                    cpu_time = sum(process.cpu_times()[:2])
                    rss = process.memory_info().rss
                    name = process.name()[:80]
                old = self._previous.get(identity)
                usage = (
                    max(0, cpu_time - old[1]) / (now - old[0]) * 100 if old and now > old[0] else 0
                )
                previous[identity] = (now, cpu_time)
                scanned += 1
                item = (pid, name, usage, rss)
                heapq.heappush(cpu_top, (usage, pid, item))
                heapq.heappush(memory_top, (rss, pid, item))
                if len(cpu_top) > self.TOP_COUNT:
                    heapq.heappop(cpu_top)
                if len(memory_top) > self.TOP_COUNT:
                    heapq.heappop(memory_top)
            except (psutil.Error, OSError):
                continue
        self._previous = previous

        def rows(heap):
            return tuple(
                (str(pid), name, f"{usage:.1f}", format_bytes(rss))
                for _, _, (pid, name, usage, rss) in sorted(heap, reverse=True)
            )

        return ProcessSnapshot(rows(cpu_top), rows(memory_top), len(pids), scanned, ready)


class FilesystemMetrics:
    LOCAL_TYPES = {
        "ext2",
        "ext3",
        "ext4",
        "btrfs",
        "xfs",
        "vfat",
        "exfat",
        "f2fs",
        "ntfs",
        "ntfs3",
        "zfs",
        "overlay",
        "fuseblk",
    }

    def __init__(self, disk_path):
        self._path = str(disk_path)

    def sample(self, now):
        paths, devices = [self._path], set()
        for partition in psutil.disk_partitions(all=False):
            if len(paths) >= 16:
                break
            if partition.fstype not in self.LOCAL_TYPES or partition.device in devices:
                continue
            devices.add(partition.device)
            if partition.mountpoint not in paths:
                paths.append(partition.mountpoint)
        rows, skipped = [], 0
        for path in paths:
            try:
                disk = psutil.disk_usage(path)
                stats = os.statvfs(path)
                inodes = (
                    f"{100 * (1 - stats.f_favail / stats.f_files):.0f}%" if stats.f_files else "N/A"
                )
                rows.append((path, f"{disk.percent:.0f}%", format_bytes(disk.free), inodes))
            except (OSError, psutil.Error):
                skipped += 1
        return FilesystemSnapshot(tuple(rows), len(rows), skipped)


class ServiceMetrics:
    def __init__(self, names, runner):
        self._names = tuple(names)
        self._runner = runner
        self._command = None

    def sample(self, now):
        if not Path("/run/systemd/system").exists():
            return ServiceSnapshot((), (), "systemd is unavailable", False)
        self._command = self._command or shutil.which("systemctl")
        if not self._command:
            return ServiceSnapshot((), (), "systemctl is unavailable", False)
        output = self._runner.run(
            [
                self._command,
                "show",
                "--no-pager",
                "--property=Id,LoadState,ActiveState,SubState",
                *self._names,
            ],
            accept_status=True,
        )
        statuses = {}
        for block in output.strip().split("\n\n"):
            fields = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
            name = fields.get("Id")
            if name:
                state = (
                    "missing"
                    if fields.get("LoadState") == "not-found"
                    else fields.get("ActiveState", "unknown")
                )
                statuses[name] = (state, fields.get("SubState", "unknown"))
        rows = tuple(
            (name.removesuffix(".service"), *statuses.get(name, ("unknown", "unknown")))
            for name in self._names
        )
        failed = tuple(name for name in self._names if statuses.get(name, ("",))[0] == "failed")
        return ServiceSnapshot(rows, failed, "Read-only service monitoring", True)


class WifiMetrics:
    def __init__(self, runner):
        self._runner = runner

    def sample(self, now):
        try:
            lines = Path("/proc/net/wireless").read_text().splitlines()[2:]
        except OSError:
            lines = []
        interface, quality, signal = "N/A", "N/A", "N/A"
        for line in lines:
            fields = line.split()
            if len(fields) >= 4:
                interface = fields[0].rstrip(":")
                quality = fields[2].rstrip(".")
                break
        if interface == "N/A":
            try:
                for path in sorted(Path("/sys/class/net").iterdir())[:64]:
                    if (path / "wireless").exists() or (path / "phy80211").exists():
                        interface = path.name
                        break
            except OSError:
                pass
            if interface == "N/A":
                return WifiSnapshot(
                    interface, "N/A", signal, quality, "unknown", "No wireless interface"
                )
        command = shutil.which("iw")
        if command:
            output = self._runner.run([command, "dev", interface, "link"])
            if "Not connected" in output:
                return WifiSnapshot(interface, "N/A", signal, quality, "warning", "Not connected")
            if "Connected to" not in output:
                return WifiSnapshot(
                    interface, "N/A", signal, quality, "unknown", "Link status unavailable"
                )
            ssid = re.search(r"^\s*SSID: (.+)$", output, re.MULTILINE)
            strength = re.search(r"^\s*signal: (.+)$", output, re.MULTILINE)
            return WifiSnapshot(
                interface,
                ssid[1] if ssid else "N/A",
                strength[1] if strength else signal,
                quality,
                "ok",
                "Connected",
            )
        return WifiSnapshot(
            interface, "N/A", signal, quality, "unknown", "Install iw for SSID and signal"
        )


def validate_services(names):
    result = []
    for name in names:
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@-]{0,120}", name):
            raise ValueError(f"Invalid service name: {name!r}")
        name = name if name.endswith(".service") else name + ".service"
        if name not in result:
            result.append(name)
    if len(result) > 32:
        raise ValueError("At most 32 services can be monitored")
    return tuple(result)
