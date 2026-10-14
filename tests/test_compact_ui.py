"""Regression checks for compact pages, responsive layouts, and persistent bindings."""

from unittest.mock import Mock

import pytest
import urwid

from hctui.app import DEFAULT_WIDGET
from hctui.metrics import MetricSampler
from hctui.views.compact_widgets import ResponsiveColumns, SparklineWidget, TableWidget
from hctui.views.main_view import MainView
from hctui.widget_composer import WidgetComposer


@pytest.mark.parametrize("size", [(32, 10), (40, 12), (80, 24), (120, 40)])
def test_every_page_renders_scrolls_and_preserves_widgets(size):
    composer = WidgetComposer(DEFAULT_WIDGET)
    view = MainView()
    with MetricSampler() as sampler:
        context = sampler.sample(composer.sources)
        identities = []
        for index in range(len(composer.page_names)):
            composer.select_page(index)
            view.set_pages(composer.page_names, index)
            widgets = composer.update(context)
            identities.append(widgets)
            view.update(widgets, 1000)
            for key in [None, "page down", "page up"]:
                if key:
                    view.widget.keypress(size, key)
                canvas = view.widget.render(size, focus=True)
                assert (canvas.cols(), canvas.rows()) == size
        for index, widgets in enumerate(identities):
            composer.select_page(index)
            assert composer.update(context) is widgets


def test_overview_fits_40x12_without_hiding_summary():
    composer = WidgetComposer(DEFAULT_WIDGET)
    view = MainView()
    view.set_pages(composer.page_names)
    with MetricSampler() as sampler:
        view.update(composer.update(sampler.sample(composer.required_sources)), 1000)
        text = "\n".join(line.decode() for line in view.widget.render((40, 12)).text)
        for label in ["Overview", "CPU", "RAM", "Temp", "Load", "DL", "UL", "Disk", "Free", "Tab"]:
            assert label in text


def test_responsive_columns_stack_only_when_narrow():
    widget = ResponsiveColumns([urwid.Text("first"), urwid.Text("second")], min_width=60)
    assert widget.rows((80,)) == 1
    assert widget.rows((40,)) == 2
    assert widget.rows((80,)) == 1


def test_table_keeps_important_columns_and_clips_cells():
    widget = TableWidget()
    widget.update(
        {
            "headers": ["PID", "Name", "CPU%", "RAM"],
            "rows": [(123, "long-process-name" * 4, 80, "1.0 MiB")],
            "widths": [6, 0, 6, 10],
            "compact_columns": [1, 2, 3],
        }
    )
    wide = "\n".join(row.decode() for row in widget.render((80,)).text)
    narrow = "\n".join(row.decode() for row in widget.render((40,)).text)
    assert "PID" in wide and "PID" not in narrow
    assert "CPU%" in narrow and "1.0 MiB" in narrow and "…" in narrow
    assert "\x1b" not in narrow


def test_sparkline_preserves_peak_when_downsampling_and_uses_one_row():
    widget = SparklineWidget()
    widget.update({"value": [0] * 50 + [100] + [0] * 50, "max": 100})
    assert widget.rows((20,)) == 1
    text = widget.render((20,)).text[0].decode()
    assert "█" in text
    assert urwid.calc_width(text, 0, len(text)) == 20


def test_binding_does_not_evaluate_again_when_snapshot_identity_is_unchanged(tmp_path, monkeypatch):
    path = tmp_path / "test.yaml"
    path.write_text(
        "schema_version: 2\nname: test\nsources: [memory]\nwidgets:\n"
        "- type: text\n  properties:\n    value: '@str(memory.usage)'\n"
    )
    composer = WidgetComposer(path)
    with MetricSampler() as sampler:
        context = sampler.sample(frozenset({"memory"}))
        widgets = composer.update(context)
        evaluate = Mock(side_effect=AssertionError("Unchanged snapshots must not be evaluated"))
        monkeypatch.setattr("hctui.widget_composer.evaluate", evaluate)
        for _ in range(100):
            assert composer.update(context) is widgets
        evaluate.assert_not_called()
