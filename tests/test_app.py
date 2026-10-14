"""Exercise refresh scheduling, keyboard handling, reload recovery, and CLI errors."""

from unittest.mock import Mock

import pytest
import urwid

from hctui.app import Application, main
from hctui.widget_composer import WidgetComposer


@pytest.fixture
def application(tmp_path, monkeypatch):
    path = tmp_path / "main.yaml"
    path.write_text(
        "schema_version: 2\nname: test\nwidgets:\n"
        "  - type: text\n    properties:\n      value: original\n",
        encoding="utf-8",
    )
    loop = Mock()
    loop.set_alarm_in.return_value = "alarm"
    monkeypatch.setattr("hctui.app.urwid.MainLoop", Mock(return_value=loop))
    sampler = Mock()
    sampler.sample.return_value = {}
    sampler.errors = {}
    return Application(WidgetComposer(path), sampler, 100)


def test_keyboard_limits_and_reschedules_interval(application):
    application.handle_keyboard("+")
    assert application.refresh_ms == 200
    application.loop.set_alarm_in.assert_called_with(0.2, application.refresh)
    application.handle_keyboard("-")
    application.loop.remove_alarm.assert_called_with("alarm")
    application.handle_keyboard("-")
    assert application.refresh_ms == 100
    assert "Key: -" in application.view.hint_panel.widget.text
    with pytest.raises(urwid.ExitMainLoop):
        application.handle_keyboard("q")


def test_refresh_accounts_for_work_and_skips_missed_periods(application, monkeypatch):
    timestamps = iter([10.0, 10.02, 20.0, 20.35])
    monkeypatch.setattr("hctui.app.time.monotonic", lambda: next(timestamps))
    widgets = application.view.widgets_area._widgets
    application.refresh()
    assert application.loop.set_alarm_in.call_args.args[0] == pytest.approx(0.08)
    assert application.view.widgets_area._widgets is widgets
    application.refresh()
    assert application.loop.set_alarm_in.call_args.args[0] == pytest.approx(0.05)


def test_reload_failure_keeps_working_widgets_and_recovers(application):
    path = application.composer.path
    composer = application.composer
    widgets = application.view.widgets_area._widgets
    path.write_text("widgets: [broken\n", encoding="utf-8")
    application.handle_keyboard("r")
    assert application.composer is composer
    assert application.view.widgets_area._widgets is widgets
    assert "Reload failed" in application.view.hint_panel.widget.text
    application.refresh()
    assert application.view.widgets_area._widgets is widgets
    assert "Reload failed" in application.view.hint_panel.widget.text
    path.write_text(
        "schema_version: 2\nname: test\nwidgets:\n"
        "  - type: text\n    properties:\n      value: changed\n",
        encoding="utf-8",
    )
    application.handle_keyboard("r")
    assert application.composer is not composer
    assert application.view.widgets_area._widgets[0].text == "changed"
    assert "Definitions reloaded" in application.view.hint_panel.widget.text


@pytest.mark.parametrize(
    "arguments",
    [
        ["--refresh-ms", "0"],
        ["--history-size", "0"],
        ["--history-size", "601"],
    ],
)
def test_cli_rejects_invalid_limits(arguments):
    with pytest.raises(SystemExit) as caught:
        main(arguments)
    assert caught.value.code == 2


def test_cli_reports_missing_definition(tmp_path, capsys):
    with pytest.raises(SystemExit) as caught:
        main(["--widget", str(tmp_path / "missing.yaml"), "--check"])
    assert caught.value.code == 1
    assert "missing.yaml" in capsys.readouterr().err
