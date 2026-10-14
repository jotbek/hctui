"""Width-aware page navigation and render timing."""

import time

import urwid

from .compact_widgets import PreparedText


class NavigationWidget(PreparedText):
    def __init__(self):
        super().__init__()
        self.names = ()
        self.index = 0
        self.alerts = 0

    def set_alerts(self, count):
        if count != self.alerts:
            self.alerts = count
            self.changed()

    def update(self, names, index):
        if names != self.names or index != self.index:
            self.names, self.index = names, index
            self.changed()

    def prepare(self, width):
        if self._prepared_width == width:
            return
        full = " ".join(f"{index + 1}:{name}" for index, name in enumerate(self.names))
        badge = f" !{self.alerts}" if self.alerts else ""
        full += badge
        if len(full) > width:
            text = (
                f"[{self.index + 1}/{len(self.names)}] {self.names[self.index]}{badge}  Tab: next"
            )
        else:
            text = [
                ("tab_active" if index == self.index else "tab_normal", f"{index + 1}:{name} ")
                for index, name in enumerate(self.names)
            ]
            if badge:
                text.append(("status_warning", badge))
        self._w.set_text(text)
        self._prepared_width = width


class MeasuredView(urwid.WidgetWrap):
    def __init__(self, widget, record):
        super().__init__(widget)
        self._record = record

    def render(self, size, focus=False):
        started = time.perf_counter()
        canvas = self._w.render(size, focus)
        self._record((time.perf_counter() - started) * 1000)
        return canvas
