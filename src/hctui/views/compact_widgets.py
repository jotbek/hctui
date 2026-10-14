"""Bounded flow widgets with width-sensitive columns and one-line histories."""

from __future__ import annotations

import unicodedata

import urwid
from urwid import calc_width

from .layout import FlowColumns, FlowStack


def clean_cell(value):
    text = "N/A" if value is None else str(value)
    return "".join(char for char in text[:512] if not unicodedata.category(char).startswith("C"))


def fit_cell(text, width, right=False):
    if width <= 0:
        return ""
    if calc_width(text, 0, len(text)) > width:
        visible, used = [], 0
        for char in text:
            char_width = calc_width(char, 0, len(char))
            if used + char_width > width - 1:
                break
            visible.append(char)
            used += char_width
        text = "".join(visible) + "…"
    padding = " " * max(0, width - calc_width(text, 0, len(text)))
    return padding + text if right else text + padding


class PreparedText(urwid.WidgetWrap):
    _sizing = frozenset({urwid.FLOW})

    def __init__(self):
        super().__init__(urwid.Text("", wrap="clip"))
        self._prepared_width = None

    def sizing(self):
        return self._sizing

    def changed(self):
        self._prepared_width = None
        self._invalidate()

    def rows(self, size, focus=False):
        self.prepare(size[0])
        return self._w.rows(size, focus)

    def render(self, size, focus=False):
        self.prepare(size[0])
        return self._w.render(size, focus)


class TableWidget(PreparedText):
    def __init__(self):
        super().__init__()
        self._properties = {}

    def update(self, properties):
        self._properties = properties
        self.changed()

    def prepare(self, width):
        if self._prepared_width == width:
            return
        properties = self._properties
        headers = properties.get("headers", [])
        rows = properties.get("rows", [])
        indices = list(range(len(headers)))
        if width < properties.get("compact_width", 60):
            indices = properties.get("compact_columns", indices)
        indices = indices[: max(1, width // 2)]
        if not indices:
            self._w.set_text(properties.get("empty", "No data"))
            self._prepared_width = width
            return
        requested = properties.get("widths") or [0] * len(headers)
        available = max(0, width - len(indices) + 1)
        widths = [1] * len(indices)
        remaining = max(0, available - len(indices))
        for position, index in enumerate(indices):
            if requested[index]:
                extra = min(remaining, requested[index] - 1)
                widths[position] += extra
                remaining -= extra
        flexible = [position for position, index in enumerate(indices) if not requested[index]]
        flexible = flexible or [len(indices) - 1]
        for number, position in enumerate(flexible):
            extra = remaining // (len(flexible) - number)
            widths[position] += extra
            remaining -= extra

        def format_row(row):
            return " ".join(
                fit_cell(clean_cell(row[index]), widths[position])
                for position, index in enumerate(indices)
            )

        text = [("table_header", format_row(headers))]
        limit = properties.get("max_rows", 8)
        if rows:
            for row in rows[:limit]:
                text.append("\n" + format_row(row))
            if len(rows) > limit:
                text.append(f"\n… {len(rows) - limit} more rows")
        else:
            text.append("\n" + properties.get("empty", "No data"))
        self._w.set_text(text)
        self._prepared_width = width


class SparklineWidget(PreparedText):
    def __init__(self):
        super().__init__()
        self._properties = {}

    def update(self, properties):
        self._properties = properties
        self.changed()

    def prepare(self, width):
        if width == self._prepared_width:
            return
        properties = self._properties
        label = clean_cell(properties.get("label", ""))
        prefix = label + " " if label else ""
        count = max(1, width - calc_width(prefix, 0, len(prefix)))
        values = properties.get("value", ())
        blocks = ".:-=+*#%@" if properties.get("ascii", False) else "▁▂▃▄▅▆▇█"
        maximum = properties.get("max", max(1, max(values, default=0)))
        if not values:
            result = prefix + "No samples"
        else:
            if len(values) > count:
                values = [
                    max(values[index * len(values) // count : (index + 1) * len(values) // count])
                    for index in range(count)
                ]
            result = prefix + "".join(
                blocks[min(len(blocks) - 1, max(0, int(value / maximum * (len(blocks) - 1))))]
                for value in values
            )
        self._w.set_text(result)
        self._prepared_width = width


class StatusWidget(urwid.WidgetWrap):
    def __init__(self):
        self._text = urwid.Text("", wrap="clip")
        super().__init__(urwid.AttrMap(self._text, "status_unknown"))

    def update(self, properties):
        state = properties.get("state", "unknown")
        tags = {"ok": "OK", "warning": "WARN", "critical": "FAIL", "unknown": "N/A"}
        self._text.set_text(f"[{tags[state]}] {clean_cell(properties.get('value', ''))}")
        self._w.set_attr_map({None: "status_" + state})


class ResponsiveColumns(urwid.WidgetWrap):
    _sizing = frozenset({urwid.FLOW})

    def __init__(self, children, min_width=80, spacing=1):
        self._wide = FlowColumns(children, dividechars=spacing)
        self._narrow = FlowStack(children)
        self._min_width = min_width
        super().__init__(self._wide)

    def sizing(self):
        return self._sizing

    def _select(self, width):
        selected = self._wide if width >= self._min_width else self._narrow
        if selected is not self._w:
            self._w = selected
            self._invalidate()

    def rows(self, size, focus=False):
        self._select(size[0])
        return self._w.rows(size, focus)

    def render(self, size, focus=False):
        self._select(size[0])
        return self._w.render(size, focus)
