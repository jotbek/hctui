import urwid


class MainView:
    def __init__(self):
        None

    def update(self):
        None

    def getView(self):
        return urwid.LineBox(
            original_widget=urwid.Filler(
                body=urwid.Pile(widget_list=[urwid.Text('a'), urwid.Text('b')]),
                valign='top'),
            title='hctui v.0.0.1')