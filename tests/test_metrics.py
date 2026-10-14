"""Regression tests for non-blocking sampling, counter deltas, and bounded histories."""

from types import SimpleNamespace

import pytest

from hctui.metrics import (
    CounterRates,
    CpuMetrics,
    DiskMetrics,
    MemoryMetrics,
    MetricSampler,
    NetworkMetrics,
)


def test_counter_rates_use_elapsed_time_and_reset_baselines():
    rates = CounterRates()
    assert rates.update("eth0", 10.0, (1000, 2000)) == (0.0, 0.0)
    assert rates.update("eth0", 12.0, (1400, 2600)) == (200.0, 300.0)
    assert rates.update("eth0", 13.0, (100, 3000)) == (0.0, 400.0)
    assert rates.update("wlan0", 14.0, (9000, 9000)) == (0.0, 0.0)
    assert rates.update("wlan0", 14.0, (10000, 10000)) == (0.0, 0.0)


def test_cpu_samples_all_logical_cores_once_and_limits_history(monkeypatch):
    monkeypatch.setattr("hctui.metrics.psutil.cpu_count", lambda logical=False: 2)
    calls = []

    def cpu_percent(interval=None, percpu=False):
        assert interval is None
        calls.append(percpu)
        return [10.0, 20.0, 30.0, 40.0] if percpu else 25.0

    frequency_calls = []
    monkeypatch.setattr("hctui.metrics.psutil.cpu_percent", cpu_percent)
    monkeypatch.setattr("hctui.metrics.psutil.cpu_freq", lambda: frequency_calls.append(1))
    provider = CpuMetrics(3)
    assert provider.sample(10.0).usage == 0
    snapshot = provider.sample(11.0)
    assert snapshot.per_core == (10, 20, 30, 40)
    assert snapshot.physical_count == 2
    assert snapshot.frequency_mhz is None
    assert calls == [True, False, True, False]
    assert frequency_calls == [1]
    for index in range(20):
        snapshot = provider.sample(12.0 + index)
    assert len(snapshot.history) == 3


def test_memory_handles_no_swap(monkeypatch):
    monkeypatch.setattr(
        "hctui.metrics.psutil.virtual_memory",
        lambda: SimpleNamespace(
            total=1000,
            available=400,
            percent=60.0,
        ),
    )
    monkeypatch.setattr(
        "hctui.metrics.psutil.swap_memory",
        lambda: SimpleNamespace(
            total=0,
            used=0,
            percent=0.0,
        ),
    )
    memory = MemoryMetrics().sample(10.0)
    assert memory.used == 600
    assert memory.available == 400
    assert memory.swap_total == memory.swap_usage == 0


def write_route(path, interface="eth0"):
    path.write_text(
        "Iface Destination Gateway Flags RefCnt Use Metric Mask\n"
        f"{interface} 00000000 0100000A 0003 0 0 100 00000000\n"
        "docker0 00000000 0100000A 0003 0 0 200 00000000\n"
        "down0 00000000 0100000A 0000 0 0 0 00000000\n",
        encoding="ascii",
    )


def test_network_samples_selected_interface_once_and_keeps_both_histories(tmp_path, monkeypatch):
    route = tmp_path / "route"
    write_route(route)
    counters = {
        "eth0": SimpleNamespace(bytes_recv=1000, bytes_sent=2000),
        "docker0": SimpleNamespace(bytes_recv=100000, bytes_sent=100000),
    }
    calls = []

    def read_counters(pernic, nowrap):
        assert pernic and not nowrap
        calls.append(1)
        return counters

    monkeypatch.setattr("hctui.metrics.psutil.net_io_counters", read_counters)
    provider = NetworkMetrics(3, route)
    first = provider.sample(10.0)
    assert first.interface == "eth0"
    assert first.download_rate == first.upload_rate == 0.0
    counters["eth0"] = SimpleNamespace(bytes_recv=1400, bytes_sent=2600)
    second = provider.sample(12.0)
    assert second.download_rate == 200.0
    assert second.upload_rate == 300.0
    assert second.history_max == 300.0
    assert len(calls) == 2
    for index in range(10):
        snapshot = provider.sample(13.0 + index)
    assert len(snapshot.download_history) == len(snapshot.upload_history) == 3
    write_route(route, "wlan0")
    counters["wlan0"] = SimpleNamespace(bytes_recv=500000, bytes_sent=500000)
    changed = provider.sample(40.0)
    assert changed.interface == "wlan0"
    assert changed.download_rate == changed.upload_rate == 0.0
    assert changed.download_history == changed.upload_history == (0.0, 0.0, 0.0)


def test_network_without_routes_or_interfaces(tmp_path, monkeypatch):
    monkeypatch.setattr("hctui.metrics.psutil.net_io_counters", lambda **kwargs: {})
    network = NetworkMetrics(2, tmp_path / "missing").sample(1.0)
    assert network.interface == "All interfaces"
    assert network.download_rate == network.upload_rate == 0
    assert network.history_max == 1


def test_aggregate_network_resets_when_interface_set_changes(tmp_path, monkeypatch):
    counters = {"eth0": SimpleNamespace(bytes_recv=100, bytes_sent=100)}
    monkeypatch.setattr("hctui.metrics.psutil.net_io_counters", lambda **kwargs: counters)
    provider = NetworkMetrics(2, tmp_path / "missing")
    provider.sample(1.0)
    counters["wlan0"] = SimpleNamespace(bytes_recv=10000, bytes_sent=10000)
    changed = provider.sample(2.0)
    assert changed.interface == "All interfaces"
    assert changed.download_rate == changed.upload_rate == 0


def test_disk_counter_recovery_does_not_report_a_bandwidth_spike(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "hctui.metrics.psutil.disk_usage",
        lambda path: SimpleNamespace(
            total=1000,
            used=600,
            free=400,
            percent=60.0,
        ),
    )
    reads = iter(
        [
            None,
            SimpleNamespace(read_bytes=1000000, write_bytes=2000000),
            SimpleNamespace(read_bytes=1000200, write_bytes=2000400),
        ]
    )
    monkeypatch.setattr("hctui.metrics.psutil.disk_io_counters", lambda **kwargs: next(reads))
    provider = DiskMetrics(tmp_path)
    provider.sample(1.0)
    recovered = provider.sample(2.0)
    assert recovered.read_rate == recovered.write_rate == 0
    current = provider.sample(4.0)
    assert current.read_rate == 100
    assert current.write_rate == 200


def test_disk_handles_unavailable_io_counters(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "hctui.metrics.psutil.disk_usage",
        lambda path: SimpleNamespace(
            total=1000,
            used=600,
            free=400,
            percent=60.0,
        ),
    )
    monkeypatch.setattr("hctui.metrics.psutil.disk_io_counters", lambda **kwargs: None)
    disk = DiskMetrics(tmp_path).sample(1.0)
    assert disk.used == 600
    assert disk.read_rate == disk.write_rate == 0


def test_sampler_only_creates_requested_providers(monkeypatch):
    calls = []

    class FakeMemory:
        def sample(self, now):
            calls.append(now)
            return "memory"

    def unexpected(*args, **kwargs):
        pytest.fail("Unused providers must not be initialized")

    monkeypatch.setattr("hctui.metrics.MemoryMetrics", FakeMemory)
    for name in ("CpuMetrics", "NetworkMetrics", "DiskMetrics"):
        monkeypatch.setattr(f"hctui.metrics.{name}", unexpected)
    sampler = MetricSampler()
    assert sampler.sample(frozenset({"memory"})) == {"memory": "memory"}
    assert sampler.sample(frozenset()) == {}
    assert len(calls) == 1
    assert set(sampler._providers) == {"memory"}
    assert sampler.sample(frozenset({"memory"})) == {"memory": "memory"}
    assert len(calls) == 1
    sampler.close()


@pytest.mark.parametrize("size", [0, -1, 601])
def test_history_size_is_bounded(size):
    with pytest.raises(ValueError, match="History size"):
        MetricSampler(history_size=size)
