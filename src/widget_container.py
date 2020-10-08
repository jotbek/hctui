import urwid


def get_widgets(name):
    return {
        'text1': urwid.Text('Example text 1'),
        'text2': urwid.Text('Example text 2'),
        'text3': urwid.Text('Example text 3'),
        'text4': urwid.Text('Example text 4'),
        'text5': urwid.Text('Example text 5'),
        'text6': urwid.Text('Example text 6'),
    }[name]