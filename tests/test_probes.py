"""Exercise optional probes, cached cadences, cancellation, and alert transitions."""

import threading
import time
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hctui.health import AlertMetrics
from hctui.metrics import MemorySnapshot, MetricSampler
from hctui.system_metrics import (
    FilesystemMetrics,
    LoadMetrics,
    ProcessMetrics,
    ServiceMetrics,
    ServiceSnapshot,
    SystemSnapshot,
    TemperatureMetrics,
    TemperatureSnapshot,
    WifiMetrics,
    validate_services,
)


def test_foreground_cadence_reuses_snapshot_and_does_not_collect_hidden_sources(monkeypatch):
    now = [10.0]
    calls = []
    monkeypatch.setattr("hctui.metrics.time.monotonic", lambda: now[0])
    sampler = MetricSampler()

    class Memory:
        def sample(self, timestamp):
            calls.append(timestamp)
            return MemorySnapshot(100, 50, 50, 50, 0, 0, 0)

    sampler._factories["memory"] = Memory
    try:
        first = sampler.sample(frozenset({"memory"}))["memory"]
        for _ in range(100):
            assert sampler.sample(frozenset({"memory"}))["memory"] is first
        assert calls == [10.0]
        assert sampler.sample(frozenset()) == {}
        now[0] = 12.1
        assert sampler.sample(frozenset({"memory"}))["memory"] is first
        assert calls == [10.0, 12.1]
        assert set(sampler._providers) == {"memory"}
    finally:
        sampler.close()


def test_slow_probe_never_blocks_ui_or_accumulates_jobs():
    entered, release = threading.Event(), threading.Event()
    calls = []
    snapshot = SystemSnapshot("test", 10, (), ())

    class Slow:
        def sample(self, now):
            calls.append(1)
            entered.set()
            release.wait(2)
            return snapshot

    with MetricSampler() as sampler:
        sampler._factories["system"] = Slow
        started = time.perf_counter()
        sampler.sample(frozenset({"system"}))
        assert time.perf_counter() - started < 0.5
        assert entered.wait(2)
        for _ in range(100):
            sampler.sample(frozenset({"system"}))
        assert sampler._worker.pending_count == 1
        assert len(calls) == 1
        release.set()
        deadline = time.monotonic() + 2
        while sampler._worker.result("system") is None and time.monotonic() < deadline:
            time.sleep(0.005)
        assert sampler.sample(frozenset({"system"}))["system"] is snapshot
        assert sampler._worker.pending_count == 0
        assert len(calls) == 1


def test_optional_probe_error_keeps_last_snapshot():
    provider = Mock()
    provider.sample.side_effect = OSError("unavailable")
    with MetricSampler() as sampler:
        sampler._factories["system"] = lambda: provider
        before = sampler.sample(frozenset({"system"}))["system"]
        deadline = time.monotonic() + 2
        while sampler._worker.result("system") is None and time.monotonic() < deadline:
            time.sleep(0.005)
        assert sampler.sample(frozenset({"system"}))["system"] is before
        assert "unavailable" in sampler.errors["system"]


def test_load_normalizes_against_logical_cpu_count_and_bounds_history(monkeypatch):
    monkeypatch.setattr("hctui.system_metrics.psutil.cpu_count", lambda: 4)
    monkeypatch.setattr("hctui.system_metrics.os.getloadavg", lambda: (2, 1, 0.5))
    provider = LoadMetrics(3)
    for index in range(20):
        snapshot = provider.sample(index)
    assert snapshot.normalized == 50
    assert snapshot.history == (50, 50, 50)


def test_temperature_prefers_cpu_to_hot_storage_sensor_and_bounds_history(monkeypatch):
    monkeypatch.setattr(
        "hctui.system_metrics.psutil.sensors_temperatures",
        lambda: {
            "nvme": [SimpleNamespace(current=99, label="disk")],
            "coretemp": [SimpleNamespace(current=65, label="package")],
        },
    )
    provider = TemperatureMetrics(2)
    for index in range(20):
        snapshot = provider.sample(index)
    assert snapshot.current == 65
    assert snapshot.label == "CPU/SoC"
    assert snapshot.history == (65, 65)


def test_no_temperature_sensor_is_unknown_instead_of_zero(monkeypatch):
    monkeypatch.setattr("hctui.system_metrics.psutil.sensors_temperatures", lambda: {})
    monkeypatch.setattr(Path, "read_text", Mock(side_effect=FileNotFoundError()))
    snapshot = TemperatureMetrics(2).sample(1)
    assert snapshot.current is None
    assert snapshot.history == ()


def test_process_cpu_deltas_pid_reuse_and_state_cap(monkeypatch):
    data = {1: [10.0, 20.0, 1000], 2: [20.0, 30.0, 2000]}
    monkeypatch.setattr("hctui.system_metrics.psutil.pids", lambda: list(data))

    class Process:
        def __init__(self, pid):
            self.pid = pid

        def oneshot(self):
            return nullcontext()

        def create_time(self):
            return data[self.pid][0]

        def cpu_times(self):
            return (data[self.pid][1], 0, 0, 0)

        def memory_info(self):
            return SimpleNamespace(rss=data[self.pid][2])

        def name(self):
            return "process-" + str(self.pid)

    monkeypatch.setattr("hctui.system_metrics.psutil.Process", Process)
    provider = ProcessMetrics(threading.Event())
    assert not provider.sample(10).ready
    data[1][1] += 1
    snapshot = provider.sample(12)
    assert snapshot.cpu_rows[0][:3] == ("1", "process-1", "50.0")
    data[1] = [999.0, 5000.0, 1000]
    assert all(row[2] == "0.0" for row in provider.sample(14).cpu_rows)
    provider.MAX_PROCESSES = 1
    provider.sample(16)
    assert len(provider._previous) == 1


def test_filesystems_skip_remote_mounts_and_handle_missing_inodes(monkeypatch):
    monkeypatch.setattr(
        "hctui.system_metrics.psutil.disk_partitions",
        lambda all=False: [
            SimpleNamespace(device="a", fstype="ext4", mountpoint="/"),
            SimpleNamespace(device="a", fstype="ext4", mountpoint="/bind"),
            SimpleNamespace(device="remote", fstype="nfs", mountpoint="/remote"),
        ],
    )
    paths = []

    def disk_usage(path):
        paths.append(path)
        return SimpleNamespace(percent=40.0, free=1024)

    monkeypatch.setattr("hctui.system_metrics.psutil.disk_usage", disk_usage)
    monkeypatch.setattr("hctui.system_metrics.os.statvfs", lambda path: SimpleNamespace(f_files=0))
    snapshot = FilesystemMetrics(Path("/")).sample(1)
    assert paths == ["/"]
    assert snapshot.rows == (("/", "40%", "1.0 KiB", "N/A"),)


def test_services_use_one_read_only_query_and_distinguish_missing_and_failed(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda path: True)
    monkeypatch.setattr("hctui.system_metrics.shutil.which", lambda command: "/bin/systemctl")
    runner = Mock()
    runner.run.return_value = (
        "Id=ssh.service\nLoadState=loaded\nActiveState=failed\nSubState=failed\n\n"
        "Id=other.service\nLoadState=not-found\nActiveState=inactive\nSubState=dead\n"
    )
    snapshot = ServiceMetrics(("ssh.service", "other.service"), runner).sample(1)
    assert snapshot.failed == ("ssh.service",)
    assert snapshot.rows[1][1] == "missing"
    args = runner.run.call_args.args[0]
    assert args[1] == "show"
    assert len(runner.run.call_args_list) == 1


@pytest.mark.parametrize("name", ["--help", "ssh;shutdown", "$(command)", "ssh/name"])
def test_service_names_cannot_inject_command_arguments(name):
    with pytest.raises(ValueError):
        validate_services([name])


def test_wifi_reads_explicit_signal_units_from_iw(monkeypatch):
    monkeypatch.setattr(
        Path, "read_text", lambda path: "header\nheader\nwlan0: 0000 70. -45. -256.\n"
    )
    monkeypatch.setattr("hctui.system_metrics.shutil.which", lambda command: "/bin/iw")
    runner = Mock()
    runner.run.return_value = "Connected to 00:00:00:00:00:00\n\tSSID: Test AP\n\tsignal: -45 dBm\n"
    snapshot = WifiMetrics(runner).sample(1)
    assert snapshot.ssid == "Test AP"
    assert snapshot.signal == "-45 dBm"
    assert snapshot.quality == "70"
    assert snapshot.state == "ok"


def test_alert_hysteresis_cpu_hold_service_recovery_and_event_limit():
    engine = AlertMetrics()
    context = {"cpu": SimpleNamespace(usage=99), "memory": SimpleNamespace(usage=95)}
    assert engine.sample(context, 10).rows == (("memory", "WARNING", "95.0%"),)
    assert engine.sample(context, 19).active_count == 1
    assert engine.sample(context, 20).active_count == 2
    context["cpu"].usage = 0
    context["memory"].usage = 87
    assert engine.sample(context, 21).level == "warning"
    context["memory"].usage = 84
    assert engine.sample(context, 22).level == "ok"
    context["services"] = ServiceSnapshot((), ("ssh.service",), "", True)
    assert engine.sample(context, 23).level == "critical"
    context["services"] = ServiceSnapshot((), (), "", True)
    assert engine.sample(context, 24).level == "ok"
    for index in range(100):
        context["memory"].usage = 99 if index % 2 else 0
        snapshot = engine.sample(context, 25 + index)
    assert len(snapshot.events) == 20


def test_missing_sensor_does_not_silently_clear_previous_temperature_alert():
    engine = AlertMetrics()
    context = {"temperature": TemperatureSnapshot(90, "CPU", (), ())}
    assert engine.sample(context, 1).level == "critical"
    context["temperature"] = TemperatureSnapshot(None, "N/A", (), ())
    assert engine.sample(context, 2).rows == (("temperature", "UNKNOWN", "Sensor unavailable"),)
