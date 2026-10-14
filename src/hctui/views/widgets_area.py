"""A scrollable dashboard that preserves widgets and focus between samples."""

from __future__ import annotations

import urwid


class WidgetsAreaView:
    def __init__(self) -> None:
        self.walker = urwid.SimpleFocusListWalker([])
        self.widget = urwid.ListBox(self.walker)
        self._widgets: list[urwid.Widget] | None = None
        self._page_index = 0
        self._page_states = {}

    def select_page(self, index):
        if self._page_index == index:
            return
        self._page_states[self._page_index] = (self.walker, self.widget, self._widgets)
        self._page_index = index
        if index in self._page_states:
            self.walker, self.widget, self._widgets = self._page_states[index]
        else:
            self.walker = urwid.SimpleFocusListWalker([])
            self.widget = urwid.ListBox(self.walker)
            self._widgets = None

    def update(self, widgets: list[urwid.Widget]) -> None:
        if widgets is self._widgets:
            return
        focus = self.walker.focus if self.walker else 0
        self.walker[:] = widgets
        self._widgets = widgets
        if self.walker:
            self.walker.set_focus(min(focus, len(self.walker) - 1))
