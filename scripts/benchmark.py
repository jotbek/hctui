"""Measure refresh latency and retained allocations without machine-specific assertions."""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import time
import tracemalloc
from pathlib import Path

import psutil

from hctui.app import DEFAULT_WIDGET
from hctui.metrics import MetricSampler
from hctui.views.main_view import MainView
from hctui.widget_composer import WidgetComposer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--widget", type=Path, default=DEFAULT_WIDGET)
    parser.add_argument("--width", type=int, default=80)
    parser.add_argument("--height", type=int, default=24)
    parser.add_argument("--page", type=int, default=1, help="Page number (1-9)")
    parser.add_argument(
        "--force", action="store_true", help="Force foreground sampling every iteration"
    )
    arguments = parser.parse_args()
    if arguments.iterations < 10 or arguments.width < 20 or arguments.height < 10:
        parser.error("Use at least 10 iterations and a 20x10 terminal")
    started = time.perf_counter()
    composer = WidgetComposer(arguments.widget)
    if not 1 <= arguments.page <= (len(composer.page_names) or 1):
        parser.error("Invalid page number")
    composer.select_page(arguments.page - 1)
    sampler = MetricSampler()
    sampler.configure(composer.intervals)
    view = MainView(sampler.record_render)
    view.set_pages(composer.page_names, composer.page_index)
    widgets = composer.update(sampler.sample(composer.required_sources))
    view.update(widgets, 1000)
    view.widget.render((arguments.width, arguments.height), focus=True)
    initial_ms = (time.perf_counter() - started) * 1000

    def refresh():
        updated = composer.update(sampler.sample(composer.required_sources, force=arguments.force))
        if updated is not widgets:
            raise RuntimeError("Widget tree changed during benchmark")
        view.update(updated, 1000)
        view.widget.render((arguments.width, arguments.height), focus=True)

    for _ in range(20):
        refresh()
    durations = []
    for _ in range(arguments.iterations):
        started = time.perf_counter()
        refresh()
        durations.append((time.perf_counter() - started) * 1000)
    gc.collect()
    tracemalloc.start()
    for _ in range(20):
        refresh()
    gc.collect()
    retained_before = tracemalloc.get_traced_memory()[0]
    for _ in range(arguments.iterations):
        refresh()
    gc.collect()
    retained_after, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ordered = sorted(durations)
    print(
        json.dumps(
            {
                "iterations": arguments.iterations,
                "terminal": [arguments.width, arguments.height],
                "page": arguments.page,
                "forced_foreground_sampling": arguments.force,
                "initial_load_sample_render_ms": round(initial_ms, 3),
                "refresh_median_ms": round(statistics.median(durations), 3),
                "refresh_p95_ms": round(ordered[int(0.95 * (len(ordered) - 1))], 3),
                "refresh_max_ms": round(max(durations), 3),
                "retained_allocation_change_bytes": retained_after - retained_before,
                "peak_traced_allocations_bytes": peak,
                "rss_bytes": psutil.Process().memory_info().rss,
                "definition_files": len(composer._definitions),
                "dynamic_bindings": len(composer._bindings),
                "widget_tree_reused": True,
            },
            indent=2,
        )
    )
    sampler.close()


if __name__ == "__main__":
    main()
