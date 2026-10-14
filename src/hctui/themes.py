"""Named palettes with high-color values and basic-terminal fallbacks."""

from __future__ import annotations

import json
from pathlib import Path

THEMES = tuple(json.loads(Path(__file__).with_name("themes.json").read_text(encoding="utf-8")))


def palette(theme):
    def entry(name, foreground, background="background", fallback="light gray"):
        return (name, fallback, "black", "", theme[foreground], theme[background])

    return [
        entry("body", "foreground"),
        entry("border", "border", fallback="dark cyan"),
        entry("footer", "muted"),
        entry("tab_normal", "muted"),
        entry("tab_active", "accent", "selected", "light cyan"),
        entry("table_header", "accent", fallback="light cyan"),
        entry("status_ok", "positive", fallback="light green"),
        entry("status_warning", "warning", fallback="yellow"),
        entry("status_critical", "negative", fallback="light red"),
        entry("status_unknown", "muted", fallback="dark gray"),
        entry("progress_normal", "foreground", "selected"),
        entry("progress_complete", "background", "positive", "white"),
        entry("graph_background", "muted", "selected"),
        entry("graph_complete", "selected", "positive"),
        entry("graph_smooth", "positive", "selected", "light green"),
    ]
