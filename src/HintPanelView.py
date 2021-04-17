import urwid


class HintPanelView:
    def __init__(self):
        self.menu_widget = urwid.Text('')

    def get_view(self, clear_key=True, properties={}):
        if clear_key:
            self.set_menu_text(properties=properties)
        return self.menu_widget

    def update(self, key_stroke=None, properties={}):
        self.set_menu_text(key_stroke, properties)

    def set_menu_text(self, key_stroke=None, properties={}):
        key_name = 'press key'
        if key_stroke != None:
            key_name = key_stroke if key_stroke != ' ' else 'space'
        self.menu_widget.set_text(
            'Refresh ration (+/-): '
            + str(properties.get('refresh_rate', '???'))
            + 'ms  |    << '
            + key_name + ' >>')
