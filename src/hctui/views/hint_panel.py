"""Keyboard help and application status."""

import urwid


class HintPanelView:
    """Keep footer state without resetting the last key on every refresh."""

    def __init__(self) -> None:
        self.widget = urwid.Text("")
        self.last_key = "none"
        self.compact = False

    def update(self, refresh_ms: int, key: str = "", status: str = "") -> None:
        if key:
            self.last_key = "space" if key == " " else key
        text = (
            f"Refresh interval: {refresh_ms} ms | +/- interval | r reload | q quit"
            f" | Key: {self.last_key}"
        )
        if status:
            text += f"\n{status}"
        if self.compact:
            text = "F1 Help | e Export | t Themes | q"
            if status:
                text += "\n" + status.replace("\n", " ")[:240]
            self.widget.set_wrap_mode("clip")
        if self.widget.text != text:
            self.widget.set_text(text)
