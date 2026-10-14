"""Dialogs, palette registration and complete asynchronous report snapshots."""

import html
import json
import time
from unittest.mock import Mock

import pytest
from urwid.display.raw import Screen

from hctui.app import DEFAULT_WIDGET, Application
from hctui.metrics import SOURCE_NAMES, MetricSampler
from hctui.reports import ReportExporter, snapshot_report
from hctui.themes import THEMES, palette
from hctui.views.dialogs import DialogOverlay
from hctui.views.main_view import MainView
from hctui.widget_composer import WidgetComposer


@pytest.mark.parametrize("size", [(32, 10), (40, 12), (80, 24), (120, 40)])
@pytest.mark.parametrize("kind", ["help", "credits", "themes", "report"])
def test_dialogs_resize_scroll_and_close(size, kind):
    view = MainView()
    close = Mock()
    choose = Mock()
    dialog = DialogOverlay(view.widget, kind, close, THEMES, choose=choose)
    for key in [None, "page down", "page up", "down", "up"]:
        if key:
            dialog.keypress(size, key)
        canvas = dialog.render(size, True)
        assert (canvas.cols(), canvas.rows()) == size
        text = [row.decode() for row in canvas.text]
        assert text[0][0] == "┌" and text[0][-1] == "┐"
        assert text[-1][0] == "└" and text[-1][-1] == "┘"
    dialog.keypress(size, "esc")
    close.assert_called_once()
    if kind == "themes":
        dialog.keypress(size, "enter")
        choose.assert_called_once()
    if kind == "credits":
        text = "\n".join(row.decode() for row in dialog.render(size).text)
        assert "jotbek" in text and "made this!" in text


def test_every_theme_is_complete_and_registered():
    assert len(THEMES) == len({theme["name"] for theme in THEMES}) == 10
    screen = Screen()
    for theme in THEMES:
        screen.register_palette(palette(theme))
        assert "body" in screen._palette and "border" in screen._palette
        for color in theme.values():
            if color.startswith("#"):
                assert len(color) == 7 and int(color[1:], 16) >= 0


def test_modal_does_not_stop_refresh_or_navigate_hidden_page(monkeypatch):
    monkeypatch.setattr("hctui.app.urwid.MainLoop", Mock(return_value=Mock()))
    with MetricSampler() as sampler:
        app = Application(WidgetComposer(DEFAULT_WIDGET), sampler, 1000)
        try:
            app.handle_keyboard("f1")
            dialog = app.loop.widget
            app.refresh()
            app.handle_keyboard("tab")
            assert app.loop.widget is dialog and app.composer.page_index == 0
            app.handle_keyboard("f10")
            assert app._dialog.kind == "credits"
            app.handle_keyboard("t")
            assert app._dialog.kind == "themes"
            app.select_theme(4)
            assert app._theme == 4 and app.loop.widget is app.view.widget
        finally:
            app._exporter.close()


def wait_for_report(exporter):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = exporter.poll()
        if result:
            return result
        time.sleep(0.01)
    pytest.fail("Export did not finish")


def test_report_keeps_all_sources_histories_metadata_and_escapes_html(tmp_path):
    with MetricSampler() as sampler:
        context = sampler.sample(SOURCE_NAMES)
        context["system"] = context["system"]._replace(hostname="<script>bad</script>")
        payload = snapshot_report(context, sampler.report_metadata())
    exporter = ReportExporter()
    try:
        assert exporter._worker._thread is None
        assert exporter.submit(payload, tmp_path)
        assert not exporter.submit(payload, tmp_path)
        result = wait_for_report(exporter)
        assert not result.error and not exporter.busy
        from pathlib import Path

        report = Path(result.value).read_text(encoding="utf-8")
        assert "<script>bad</script>" not in report
        serialized = html.unescape(report.split("<pre>")[1].split("</pre>")[0])
        recovered = json.loads(serialized)
        assert set(recovered["measurements"]) == set(SOURCE_NAMES)
        assert recovered["measurements"]["cpu"]["history"] == list(context["cpu"].history)
        assert "age_seconds" in recovered["sampling"]["cpu"]
        assert exporter.submit(payload, tmp_path)
        second = wait_for_report(exporter)
        assert second.value != result.value
        assert len(list(tmp_path.glob("*.html"))) == 2
        assert not list(tmp_path.glob(".hctui-*"))
    finally:
        exporter.close()


def test_export_failure_is_reported_and_does_not_kill_worker(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("existing")
    exporter = ReportExporter()
    payload = snapshot_report({}, {})
    try:
        exporter.submit(payload, blocked)
        assert wait_for_report(exporter).error
        exporter.submit(payload, tmp_path)
        assert not wait_for_report(exporter).error
    finally:
        exporter.close()


def test_e_exports_hidden_sources_without_blocking_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr("hctui.app.urwid.MainLoop", Mock(return_value=Mock()))
    with MetricSampler() as sampler:
        app = Application(WidgetComposer(DEFAULT_WIDGET), sampler, 100, tmp_path)
        try:
            app.handle_keyboard("e")
            app.handle_keyboard("e")
            assert "already" in app._status
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and "Report saved:" not in app._status:
                app.refresh()
                time.sleep(0.05)
            assert "Report saved:" in app._status
            assert len(list(tmp_path.glob("*.html"))) == 1
            assert app.composer.page_index == 0
            assert app._dialog.kind == "report"
        finally:
            app._exporter.close()


def test_actual_canvas_frame_has_no_gaps_at_corners():
    view = MainView()
    for size in [(40, 12), (80, 24)]:
        text = [row.decode() for row in view.widget.render(size).text]
        assert text[0][0] == "┌" and text[0][-1] == "┐"
        assert text[-1][0] == "└" and text[-1][-1] == "┘"
        assert all(row[0] == row[-1] == "│" for row in text[1:-1])


def test_conditional_widget_rebuilds_only_when_visibility_changes(tmp_path):
    from hctui.system_metrics import TemperatureSnapshot

    path = tmp_path / "conditional.yaml"
    path.write_text(
        "schema_version: 2\nname: test\nsources: [temperature]\nwidgets:\n"
        "- type: conditional\n  properties:\n"
        "    visible: '@temperature.current is not None'\n  children:\n"
        "  - type: text\n    properties:\n      value: Sensor available\n"
    )
    composer = WidgetComposer(path)
    hidden = composer.update({"temperature": TemperatureSnapshot(None, "N/A", (), ())})
    visible = composer.update({"temperature": TemperatureSnapshot(60, "SoC", (), ())})
    assert visible is not hidden and visible[0].text == "Sensor available"
    assert composer.update({"temperature": TemperatureSnapshot(65, "SoC", (), ())}) is visible
    assert composer.update({"temperature": TemperatureSnapshot(None, "N/A", (), ())}) is not visible
