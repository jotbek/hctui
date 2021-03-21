import urwid
import MainView
import re

REFRESH_INTERVAL = 2


def palette_configuration(file_path):
    styles = []
    with open(file_path) as fp:
        for line in fp:
            line = line.strip()
            if re.match(r'\S', line) and not line.startswith('#'):
                styles.append(tuple([s.strip() for s in line.split(';')]))
    return styles


def handle_keyboard(key):
    global main_view
    if key in ('q', 'Q'):
        raise urwid.ExitMainLoop()

    if key in ('up', 'down', 'left', 'right', 'insert', 'delete', 'enter', 'esc', ' '):
        main_view.update(key_stroke=key)


def update(*args):
    global main_view
    global loop

    main_view.update()
    loop.draw_screen()
    loop.set_alarm_in(REFRESH_INTERVAL, update)


PALETTE = palette_configuration('palette.config')
main_view = MainView.MainView()
loop = urwid.MainLoop(
    widget=main_view.get_view(),
    palette=PALETTE,
    unhandled_input=handle_keyboard,
    handle_mouse=False)

loop.set_alarm_in(0, update)
loop.run()
