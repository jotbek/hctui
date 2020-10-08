import urwid


class WidgetsAreaView:
    def __init__(self):
        pass

    def get_view(self):
        return urwid.Filler(
            body=urwid.Pile(widget_list=[urwid.Text('a'), urwid.Text('b')]),
            valign='top')

    def update(self):
        pass