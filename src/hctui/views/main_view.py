"""The persistent application frame."""

from __future__ import annotations

import urwid

from .. import __version__
from .hint_panel import HintPanelView
from .layout import FlowStack
from .navigation import MeasuredView, NavigationWidget
from .widgets_area import WidgetsAreaView


class MainView:
    def __init__(self, record_render=None) -> None:
        self.widgets_area = WidgetsAreaView()
        self.hint_panel = HintPanelView()
        footer = FlowStack(
            [
                urwid.AttrMap(urwid.Divider("─"), "border"),
                urwid.AttrMap(self.hint_panel.widget, "footer"),
            ]
        )
        self._frame = urwid.Frame(body=self.widgets_area.widget, footer=footer)
        self._navigation = NavigationWidget()
        self.widget = urwid.AttrMap(
            urwid.LineBox(
                urwid.AttrMap(self._frame, "body"),
                title=f"hctui {__version__}",
            ),
            "border",
        )
        if record_render is not None:
            self.widget = MeasuredView(self.widget, record_render)

    def set_pages(self, names, index=0):
        self.widgets_area.select_page(index)
        self._frame.body = self.widgets_area.widget
        self.hint_panel.compact = bool(names)
        if names:
            self._navigation.update(names, index)
            self._frame.header = FlowStack(
                [self._navigation, urwid.AttrMap(urwid.Divider("─"), "border")]
            )
        else:
            self._frame.header = None

    def set_alerts(self, count):
        self._navigation.set_alerts(count)

    def update(self, widgets: list[urwid.Widget], refresh_ms: int, status: str = "") -> None:
        self.widgets_area.update(widgets)
        self.hint_panel.update(refresh_ms, status=status)
