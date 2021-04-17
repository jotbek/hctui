import urwid
import MainView
import re

REFRESH_INTERVAL_MS = 1000


def palette_configuration(file_path):
    styles = []
    with open(file_path) as fp:
        for line in fp:
            line = line.strip()
            if not line.startswith('#') and re.match(r'\S', line):
                styles.append(tuple([s.strip() for s in line.split(';')]))
    return styles


def handle_keyboard(key):
    global main_view
    global REFRESH_INTERVAL_MS
    if key in ('q', 'Q'):
        raise urwid.ExitMainLoop()

    if key == '+':
        REFRESH_INTERVAL_MS += 100

    if key == '-':
        REFRESH_INTERVAL_MS -= 100 if REFRESH_INTERVAL_MS > 100 else 0

    if key in ('up', 'down', 'left', 'right', 'insert', 'delete', 'enter', 'esc', '+', '-', ' '):
        main_view.update(key_stroke=key, properties={'refresh_rate': REFRESH_INTERVAL_MS})


def update(*args):
    global main_view
    global loop
    global REFRESH_INTERVAL_MS

    loop.widget = main_view.get_view(properties={'refresh_rate': REFRESH_INTERVAL_MS})
    loop.set_alarm_in(REFRESH_INTERVAL_MS / 1000, update)


PALETTE = palette_configuration('palette.config')
main_view = MainView.MainView()
loop = urwid.MainLoop(
    widget=None,
    palette=PALETTE,
    unhandled_input=handle_keyboard,
    handle_mouse=False)

loop.set_alarm_in(0, update)
loop.run()
