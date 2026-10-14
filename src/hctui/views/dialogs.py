"""Small, scrollable dialogs that adapt to terminal dimensions."""

from __future__ import annotations

import urwid

HELP = (
    (
        "Controls",
        "F1: help    F10: credits    Esc/Enter: close dialog\n"
        "e: export all current measurements to an HTML report\n"
        "t: choose one of ten color themes\n"
        "Tab/Right: next page    Shift-Tab/Left: previous page\n"
        "1-9: select page    Up/Down, Page Up/Down: scroll\n"
        "+/-: increase/decrease refresh interval by 100 ms\n"
        "r: reload YAML definitions    q: quit",
    ),
    (
        "Pages",
        "Overview: compact health summary, CPU, RAM, network, disk and load.\n"
        "CPU: logical CPU usage, temperature and load history.\n"
        "Memory: RAM and swap capacity and usage.\n"
        "Network: traffic, local IPv4 addresses and Wi-Fi details.\n"
        "Storage: filesystem capacity, inodes and system disk I/O.\n"
        "Processes: top CPU and memory consumers.\n"
        "System: host details, monitor overhead and service status.\n"
        "Alerts: active warnings and recent state changes.",
    ),
    (
        "Measurements",
        "Sources have independent sampling intervals. Hidden pages do not "
        "run expensive probes; health checks stay active. Slow probes run in the background.\n"
        "Process CPU: 100% means one logical CPU; multithreaded processes may exceed 100%.\n"
        "N/A means the hardware, command or measurement is unavailable.\n"
        "Histories retain samples, rather than a fixed number of seconds.\n"
        "Export briefly collects every source, including hidden pages. The report includes "
        "histories, sampling ages and probe errors. It contains host and network details.",
    ),
)


class DialogOverlay(urwid.Widget):
    """Retain the underlying live dashboard and resize only when needed."""

    _sizing = frozenset({urwid.Sizing.BOX})

    def __init__(self, background, kind, close, themes=(), selected=0, choose=None, message=""):
        super().__init__()
        self.background = background
        self.kind = kind
        self.close = close
        self.themes = themes
        self.selected = selected
        self.choose = choose
        self.message = message
        self._size = None
        self._overlay = None

    def selectable(self):
        return True

    def _build(self, size):
        columns, rows = size
        width = max(4, min(70, columns - 2))
        height = max(4, min({"help": 24, "themes": 16}.get(self.kind, 10), rows - 2))
        if self.kind == "help":
            widgets = []
            for title, description in HELP:
                widgets.extend(
                    [urwid.Text(("table_header", title)), urwid.Text(description), urwid.Divider()]
                )
        elif self.kind == "report":
            widgets = [
                urwid.Text(self.message),
                urwid.Divider(),
                urwid.Text(
                    "Open the HTML file in a browser. It includes every source "
                    "and the complete JSON snapshot."
                ),
            ]
        elif self.kind == "themes":
            widgets = [
                urwid.AttrMap(
                    urwid.Button(
                        theme["name"], on_press=lambda button, index=index: self.choose(index)
                    ),
                    "body",
                    "tab_active",
                )
                for index, theme in enumerate(self.themes)
            ]
        else:
            widgets = [
                urwid.Divider(),
                urwid.Text(("table_header", "jotbek"), align="center"),
                urwid.Divider(),
                urwid.Text("made this!", align="center"),
            ]
        body = urwid.ListBox(urwid.SimpleFocusListWalker(widgets))
        if self.kind == "themes":
            body.set_focus(self.selected)
        dialog = urwid.LineBox(
            urwid.AttrMap(
                urwid.Frame(
                    body,
                    footer=urwid.Text(
                        "Enter apply | Esc close"
                        if self.kind == "themes"
                        else "Esc/Enter close | Up/Down scroll",
                        wrap="clip",
                    ),
                ),
                "body",
            ),
            title={"help": "Help", "themes": "Themes", "report": "Report"}.get(
                self.kind, "Credits"
            ),
        )
        self._overlay = urwid.Overlay(
            urwid.AttrMap(dialog, "border"), self.background, "center", width, "middle", height
        )
        self._size = size

    def render(self, size, focus=False):
        if self._size != size:
            self._build(size)
        return self._overlay.render(size, focus)

    def keypress(self, size, key):
        if key == "esc" or (key == "enter" and self.kind != "themes"):
            self.close()
            return None
        if self._size != size:
            self._build(size)
        return self._overlay.keypress(size, key)
