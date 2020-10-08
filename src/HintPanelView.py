import urwid

FIRST_MENU_TEXT = 'F1: show/hide menu  |  F2: edit/view  |  Q: Exit'
LAST_MENU_TEXT = 'Arrows: Move  |  Enter: Select  |  Ins: Insert  |  Del: Delete'


class HintPanelView:
    def __init__(self):
        self.menu_widget = urwid.Pile(
            [urwid.Text(FIRST_MENU_TEXT), urwid.Text(LAST_MENU_TEXT)])

    def get_view(self):
        return self.menu_widget

    def update(self):
        pass
