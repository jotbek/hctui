import urwid

FIRST_MENU_TEXT = 'F1: show/hide menu  |  F2: edit/view  |  Q: Exit'
LAST_MENU_TEXT = 'Arrows: Move  |  Enter: Select  |  Ins: Insert  |  Del: Delete'


class HintPanelView:
    def __init__(self):
        self.first_menu_widget = urwid.Text(FIRST_MENU_TEXT)
        self.last_menu_widget = urwid.Text('')
        self.menu_widget = urwid.Pile(
            [self.first_menu_widget, self.last_menu_widget])

    def get_view(self):
        return self.menu_widget

    def update(self, key_stroke=None):
        if key_stroke == None:
            self.last_menu_widget.set_text(LAST_MENU_TEXT)
        else:
            self.last_menu_widget.set_text(LAST_MENU_TEXT + '  |  << key pressed: ' + key_stroke + ' >>')

