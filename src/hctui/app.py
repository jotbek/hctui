"""Command-line entry point and non-blocking refresh scheduling."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import psutil
import urwid

from . import __version__
from .expressions import DefinitionError
from .metrics import SOURCE_NAMES, MetricSampler
from .reports import ReportExporter, snapshot_report
from .themes import THEMES, palette
from .views.dialogs import DialogOverlay
from .views.main_view import MainView
from .widget_composer import WidgetComposer

RESOURCE_DIR = Path(__file__).resolve().parent
DEFAULT_WIDGET = RESOURCE_DIR / "widgets" / "main.yaml"


class Application:
    """Own all mutable application state; importing the module never starts the UI."""

    @property
    def metric_sources(self):
        health = {"alerts"} if "alerts" in self.composer.sources else set()
        return self.composer.required_sources | health

    def __init__(
        self,
        composer: WidgetComposer,
        sampler: MetricSampler,
        refresh_ms: int,
        report_dir: Path | None = None,
        theme: int = 0,
    ) -> None:
        self.composer = composer
        self.sampler = sampler
        self.refresh_ms = refresh_ms
        self.sampler.configure(composer.intervals)
        self.view = MainView(sampler.record_render)
        self.view.set_pages(composer.page_names, composer.page_index)
        self._status = ""
        self._reload_error = ""
        self._dialog = None
        self._theme = theme
        self.report_dir = report_dir or Path.cwd() / "reports"
        self._exporter = ReportExporter()
        self._export_deadline = None
        self._notice_until = 0.0
        self._report_message = ""
        context = sampler.sample(self.metric_sources)
        self.view.update(composer.update(context), refresh_ms)
        self._update_alert_badge(context)
        self.loop = urwid.MainLoop(
            self.view.widget,
            palette=palette(THEMES[theme]),
            unhandled_input=self.handle_keyboard,
            handle_mouse=False,
        )
        self.loop.screen.set_terminal_properties(colors=256)
        self._alarm = None

    def close_dialog(self):
        self._dialog = None
        self.loop.widget = self.view.widget

    def open_dialog(self, kind):
        if self._dialog is not None and self._dialog.kind == kind:
            self.close_dialog()
            return
        self._dialog = DialogOverlay(
            self.view.widget,
            kind,
            self.close_dialog,
            THEMES,
            self._theme,
            self.select_theme,
            self._report_message,
        )
        self.loop.widget = self._dialog

    def select_theme(self, index):
        self._theme = index
        self.loop.screen.register_palette(palette(THEMES[index]))
        self.loop.screen.clear()
        self.close_dialog()

    def request_export(self):
        if self._export_deadline is not None or self._exporter.busy:
            self._status = "Export already in progress"
        else:
            self._export_deadline = time.monotonic() + 10
            self.sampler.sample(SOURCE_NAMES)
            self._status = "Collecting all sources for report..."
        self._notice_until = time.monotonic() + 12

    def handle_keyboard(self, key: str) -> None:
        if key in {"q", "Q"}:
            raise urwid.ExitMainLoop()
        if key in {"f1", "f10", "t", "T"}:
            self.open_dialog({"f1": "help", "f10": "credits"}.get(key, "themes"))
            return
        if self._dialog is not None:
            if key in {"esc", "enter"}:
                self.close_dialog()
            return
        if key in {"e", "E"}:
            self.request_export()
        if self.composer.page_names:
            index = self.composer.page_index
            if key in {"tab", "right"}:
                index = (index + 1) % len(self.composer.page_names)
            elif key in {"shift tab", "left"}:
                index = (index - 1) % len(self.composer.page_names)
            elif key in set("123456789"):
                index = min(int(key) - 1, len(self.composer.page_names) - 1)
            if index != self.composer.page_index:
                self.composer.select_page(index)
                self.view.set_pages(self.composer.page_names, index)
                self.view.update(
                    self.composer.update(self.sampler.sample(self.metric_sources)),
                    self.refresh_ms,
                    self._reload_error,
                )
        if key in {"+", "-"}:
            self.refresh_ms = max(100, self.refresh_ms + (100 if key == "+" else -100))
            if self._alarm is not None:
                self.loop.remove_alarm(self._alarm)
            self._alarm = self.loop.set_alarm_in(self.refresh_ms / 1000, self.refresh)
        if key in {"r", "R"}:
            try:
                candidate = WidgetComposer(self.composer.path)
                if candidate.page_names and self.composer.page_names:
                    name = self.composer.page_names[self.composer.page_index]
                    candidate.select_page(
                        candidate.page_names.index(name) if name in candidate.page_names else 0
                    )
                self.sampler.configure(candidate.intervals)
                widgets = candidate.update(self.sampler.sample(candidate.required_sources))
                self.composer = candidate
                self._reload_error = ""
                self._status = "Definitions reloaded"
                self.view.set_pages(candidate.page_names, candidate.page_index)
                self.view.update(widgets, self.refresh_ms, self._status)
            except (DefinitionError, OSError, psutil.Error) as error:
                self.sampler.configure(self.composer.intervals)
                self._reload_error = f"Reload failed: {error}"
        self.view.hint_panel.update(
            self.refresh_ms, key=key, status=self._reload_error or self._status
        )

    def refresh(self, loop=None, user_data=None) -> None:
        started = time.monotonic()
        sample_ms = 0.0
        update_started = time.perf_counter()
        try:
            sample_started = time.perf_counter()
            context = self.sampler.sample(
                SOURCE_NAMES if self._export_deadline is not None else self.metric_sources
            )
            if self._export_deadline is not None and (
                (
                    not self.sampler.pending_sources
                    and (context["processes"].ready or "processes" in self.sampler.errors)
                )
                or time.monotonic() >= self._export_deadline
            ):
                self._exporter.submit(
                    snapshot_report(context, self.sampler.report_metadata()), self.report_dir
                )
                self._export_deadline = None
                self._status = "Writing report..."
            exported = self._exporter.poll()
            if exported is not None:
                self._status = (
                    f"Export failed: {exported.error}"
                    if exported.error
                    else f"Report saved: {exported.value}"
                )
                self._notice_until = time.monotonic() + 15
                self._report_message = self._status
                if self._dialog is None:
                    self.open_dialog("report")
            sample_ms = (time.perf_counter() - sample_started) * 1000
            update_started = time.perf_counter()
            widgets = self.composer.update(context)
            self._update_alert_badge(context)
            if started >= self._notice_until:
                self._status = ""
            unavailable = sorted(set(context) & self.sampler.errors.keys())
            probe_status = "Stale/unavailable: " + ", ".join(unavailable) if unavailable else ""
            self.view.update(
                widgets, self.refresh_ms, self._reload_error or self._status or probe_status
            )
        except (DefinitionError, OSError, psutil.Error) as error:
            self._status = f"Refresh failed: {error}"
            self.view.hint_panel.update(self.refresh_ms, status=self._status)
        elapsed = time.monotonic() - started
        interval = self.refresh_ms / 1000
        self.sampler.record_refresh(
            sample_ms, (time.perf_counter() - update_started) * 1000, int(elapsed // interval)
        )
        # Skip missed periods instead of running a burst of overdue refreshes.
        delay = max(0.01, (int(elapsed // interval) + 1) * interval - elapsed)
        self._alarm = self.loop.set_alarm_in(delay, self.refresh)

    def _update_alert_badge(self, context):
        if "alerts" in context:
            self.view.set_alerts(context["alerts"].active_count)

    def run(self) -> None:
        self._alarm = self.loop.set_alarm_in(self.refresh_ms / 1000, self.refresh)
        try:
            self.loop.run()
        finally:
            self._exporter.close()
            self.sampler.close()


def main(argv: list[str] | None = None) -> int:
    """Run the monitor or validate a dashboard without opening a terminal UI."""
    parser = argparse.ArgumentParser(description="A lightweight terminal system monitor")
    parser.add_argument("--version", action="version", version=f"hctui {__version__}")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path.cwd() / "reports",
        help="Directory for HTML snapshots exported with e (default: ./reports)",
    )
    parser.add_argument(
        "--theme",
        choices=[theme["name"] for theme in THEMES],
        default=THEMES[0]["name"],
        help="Initial color theme",
    )
    parser.add_argument(
        "--widget", type=Path, default=DEFAULT_WIDGET, help="Path to a YAML dashboard definition"
    )
    parser.add_argument(
        "--refresh-ms",
        type=int,
        default=1000,
        help="Refresh interval in milliseconds (minimum: 100)",
    )
    parser.add_argument(
        "--history-size", type=int, default=60, help="Number of graph samples to retain (1-600)"
    )
    parser.add_argument(
        "--disk-path",
        type=Path,
        default=Path(Path.home().anchor),
        help="Filesystem path to monitor (default: system root)",
    )
    parser.add_argument(
        "--check", action="store_true", help="Validate, collect one sample, render, and exit"
    )
    parser.add_argument(
        "--service", action="append", help="Service to monitor (repeatable; default: ssh, cron)"
    )
    parser.add_argument(
        "--temperature-warning",
        type=float,
        default=80,
        help="Temperature warning threshold in Celsius (20-110)",
    )
    arguments = parser.parse_args(argv)
    if arguments.refresh_ms < 100:
        parser.error("--refresh-ms must be at least 100")
    if not 1 <= arguments.history_size <= 600:
        parser.error("--history-size must be between 1 and 600")
    if not 20 <= arguments.temperature_warning <= 110:
        parser.error("--temperature-warning must be between 20 and 110")
    if not arguments.disk_path.exists():
        parser.error("--disk-path must exist")
    sampler = None
    try:
        composer = WidgetComposer(arguments.widget)
        sampler = MetricSampler(
            arguments.history_size,
            arguments.disk_path.expanduser().resolve(),
            arguments.service or ("ssh", "cron"),
            arguments.temperature_warning,
        )
        sampler.configure(composer.intervals)
        if arguments.check:
            started = time.monotonic()
            view = MainView()
            context = sampler.sample(composer.sources)
            for index in range(len(composer.page_names) or 1):
                composer.select_page(index)
                view.set_pages(composer.page_names, index)
                view.update(composer.update(context), arguments.refresh_ms)
                for size in ((40, 12), (80, 24)):
                    view.widget.render(size, focus=True)
            elapsed_ms = (time.monotonic() - started) * 1000
            print(f"Valid dashboard: {composer.path}")
            print(f"Metric sources: {', '.join(sorted(composer.sources)) or 'none'}")
            print(f"All pages rendered at 40x12 and 80x24: {elapsed_ms:.1f} ms")
        else:
            Application(
                composer,
                sampler,
                arguments.refresh_ms,
                arguments.report_dir.expanduser(),
                next(
                    index for index, theme in enumerate(THEMES) if theme["name"] == arguments.theme
                ),
            ).run()
    except (DefinitionError, OSError, psutil.Error, ValueError) as error:
        parser.exit(1, f"hctui: {error}\n")
    except KeyboardInterrupt:
        return 0
    finally:
        if sampler is not None:
            sampler.close()
    return 0
