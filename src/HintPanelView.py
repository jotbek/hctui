import urwid

MENU_TEXT = 'Space: Stop/Start auto refresh  |  Q: Exit'


class HintPanelView:
    def __init__(self):
        self.menu_widget = urwid.Text(MENU_TEXT)

    def get_view(self, clear_key=True):
        if clear_key:
            self.set_menu_text()
        return self.menu_widget

    def update(self, key_stroke=None):
        self.set_menu_text(key_stroke)

    def set_menu_text(self, key_stroke=None):
        key_name = 'press key'
        if key_stroke != None:
            key_name = key_stroke if key_stroke != ' ' else 'space'
        self.menu_widget.set_text(MENU_TEXT + '  |    << ' + key_name + ' >>')