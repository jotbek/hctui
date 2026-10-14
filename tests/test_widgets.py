"""Regression tests for load-once definitions and updates of persistent widgets."""

import ast
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import urwid
import yaml
from jsonschema import Draft202012Validator

from hctui.app import DEFAULT_WIDGET, RESOURCE_DIR
from hctui.expressions import DefinitionError, compile_expression, resolve
from hctui.metrics import CpuSnapshot, MetricSampler
from hctui.views.main_view import MainView
from hctui.widget_composer import UniqueKeyLoader, WidgetComposer


def write_definition(tmp_path, widgets, sources=None, name="test.yaml"):
    path = tmp_path / name
    document = {"schema_version": 2, "name": "test", "sources": sources or [], "widgets": widgets}
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def cpu_context(count=4, usage=20.0):
    return {"cpu": CpuSnapshot(usage, (usage,) * count, 2, None, (0, usage))}


def test_updates_reuse_widgets_without_io_parsing_or_compilation(tmp_path, monkeypatch):
    path = write_definition(
        tmp_path,
        [
            {"type": "text", "properties": {"value": "@f'CPU = {cpu.usage}%; cached'"}},
            {"type": "progress", "properties": {"value": "@cpu.usage"}},
        ],
        ["cpu"],
    )
    composer = WidgetComposer(path)
    widgets = composer.update(cpu_context())
    first = widgets[0]
    first.set_text = Mock(wraps=first.set_text)
    compile_expression.cache_clear()

    def unexpected(*args, **kwargs):
        pytest.fail("Steady updates must not read, parse, compile, or construct widgets")

    monkeypatch.setattr(Path, "open", unexpected)
    monkeypatch.setattr(Path, "stat", unexpected)
    monkeypatch.setattr(ast, "parse", unexpected)
    monkeypatch.setattr(yaml, "load", unexpected)
    monkeypatch.setattr("hctui.widget_composer.urwid.Text", unexpected)
    for _ in range(10):
        assert composer.update(cpu_context()) is widgets
    first.set_text.assert_not_called()
    assert composer.update(cpu_context(usage=30)) is widgets
    assert widgets[0] is first
    assert first.text == "CPU = 30%; cached"
    first.set_text.assert_called_once()
    assert widgets[1].current == 30


def test_repeat_uses_exclusive_stop_and_rebuilds_only_on_structure_change(tmp_path):
    path = write_definition(
        tmp_path,
        [
            {
                "type": "repeat",
                "properties": {"stop": "@len(cpu.per_core)", "columns": 2, "variable": "core"},
                "template": {"type": "text", "properties": {"value": "@str(core)"}},
            }
        ],
        ["cpu"],
    )
    composer = WidgetComposer(path)
    widgets = composer.update(cpu_context(4))
    assert len(widgets[0].contents) == 2
    assert composer.update(cpu_context(4, 30)) is widgets
    changed = composer.update(cpu_context(1))
    assert changed is not widgets
    assert changed[0].contents[0][0].contents[0][0].text == "0"
    changed[0].render((40,))


def test_includes_are_relative_to_definition_and_cycles_are_reported(tmp_path, monkeypatch):
    child = write_definition(
        tmp_path, [{"type": "text", "properties": {"value": "hello"}}], name="child.yaml"
    )
    parent = write_definition(tmp_path, [{"type": "include", "properties": {"path": child.name}}])
    monkeypatch.chdir(tmp_path.parent)
    assert WidgetComposer(parent).update({})[0].text == "hello"
    write_definition(
        tmp_path, [{"type": "include", "properties": {"path": parent.name}}], name="child.yaml"
    )
    with pytest.raises(DefinitionError, match="Circular include"):
        WidgetComposer(parent)


def test_invalid_property_does_not_partially_update_widgets(tmp_path):
    path = write_definition(
        tmp_path,
        [
            {"type": "text", "properties": {"value": "@str(cpu.usage)"}},
            {"type": "graph", "properties": {"value": "@cpu.history", "max": "@cpu.usage"}},
        ],
        ["cpu"],
    )
    composer = WidgetComposer(path)
    widgets = composer.update(cpu_context())
    with pytest.raises(DefinitionError, match=r"properties.max"):
        composer.update(cpu_context(usage=0))
    assert widgets[0].text == "20.0"
    assert composer.update(cpu_context(usage=30)) is widgets
    assert widgets[0].text == "30"


@pytest.mark.parametrize(
    "node, message",
    [
        ({"type": "unknown"}, "widget type"),
        ({"type": []}, "widget type"),
        ({"type": "text", "properties": "value=x"}, "mapping"),
        ({"type": "text", "properties": {"algin": "left"}}, "Unknown text property"),
        ({"type": "box", "children": []}, "non-empty"),
        ({"type": "repeat", "properties": {"stop": 3}}, "template"),
        ({"type": "progress", "properties": {"max": 0}}, "positive"),
        ({"type": "text", "properties": {"value": "@missing.usage"}}, "Unknown names"),
        ({"type": "graph", "properties": {"height": True}}, "Invalid value"),
        ({"type": "graph", "properties": {"max": float("nan")}}, "finite"),
        (
            {
                "type": "repeat",
                "properties": {"variable": "for", "stop": 1},
                "template": {"type": "text"},
            },
            "Loop variable",
        ),
    ],
)
def test_validation_reports_specific_definition_errors(tmp_path, node, message):
    path = write_definition(tmp_path, [node])
    with pytest.raises(DefinitionError, match=message) as caught:
        WidgetComposer(path)
    assert str(path) in str(caught.value)


@pytest.mark.parametrize(
    "expression",
    [
        "@cpu.__class__",
        "@__import__('os')",
        "@cpu.history.clear()",
        "@[x for x in cpu.history]",
        "@(lambda: 1)()",
        "@(x := 1)",
    ],
)
def test_expressions_reject_private_access_and_arbitrary_calls(expression):
    with pytest.raises(DefinitionError):
        resolve(expression, cpu_context())


def test_safe_yaml_rejects_duplicate_keys_and_python_tags(tmp_path):
    path = tmp_path / "test.yaml"
    for source in ["schema_version: 2\nschema_version: 2\n", "!!python/object:os.system {}"]:
        path.write_text(source, encoding="utf-8")
        with pytest.raises(DefinitionError):
            WidgetComposer(path)


def test_editor_schema_validates_every_shipped_definition():
    schema = json.loads((RESOURCE_DIR / "widget_schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for path in (RESOURCE_DIR / "widgets").glob("*.yaml"):
        validator.validate(yaml.load(path.read_text(), Loader=UniqueKeyLoader))


@pytest.mark.parametrize("size", [(40, 12), (80, 24), (160, 60)])
@pytest.mark.parametrize("core_count", [1, 4, 12])
def test_dashboard_renders_and_scrolls_in_small_terminals(size, core_count):
    composer = WidgetComposer(DEFAULT_WIDGET)
    view = MainView()
    with MetricSampler() as sampler:
        context = sampler.sample(composer.sources)
    context.update(cpu_context(core_count, 30.0))
    view.update(composer.update(context), 1000)
    canvas = view.widget.render(size, focus=True)
    assert (canvas.cols(), canvas.rows()) == size
    for key in ["down", "page down", "end", "up", "page up", "home"]:
        view.widget.keypress(size, key)
        canvas = view.widget.render(size, focus=True)
        assert (canvas.cols(), canvas.rows()) == size


def test_yaml_loads_without_the_optional_c_extension(tmp_path, monkeypatch):
    class PythonLoader(yaml.SafeLoader):
        construct_mapping = UniqueKeyLoader.construct_mapping

    monkeypatch.setattr("hctui.widget_composer.UniqueKeyLoader", PythonLoader)
    path = write_definition(tmp_path, [{"type": "text", "properties": {"value": "Python YAML"}}])
    assert WidgetComposer(path).update({})[0].text == "Python YAML"


@pytest.mark.parametrize("size", [(40, 12), (80, 24), (120, 30)])
@pytest.mark.parametrize("status", ["", "Reload failed: " + "invalid property " * 3])
def test_footer_is_separated_from_clipped_widgets(size, status):
    view = MainView()
    panel = urwid.LineBox(urwid.Text("\n".join(["WIDGET CONTENT"] * 100)))
    view.update([panel], 1000, status)
    for key in [None, "page down", "page up"]:
        if key:
            view.widget.keypress(size, key)
        rows = [row.decode("utf-8") for row in view.widget.render(size, focus=True).text]
        menu_row = next(index for index, row in enumerate(rows) if "Refresh interval:" in row)
        assert rows[menu_row - 1][1:-1] == "─" * (size[0] - 2)
        assert "WIDGET CONTENT" in rows[menu_row - 2]
        assert rows[-1].startswith("└") and rows[-1].endswith("┘")
