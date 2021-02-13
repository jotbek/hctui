import urwid
import MainView

REFRESH_INTERVAL = 3
PALETTE = []


def exit_on_q(key):
    global main_view
    if key in ('q', 'Q'):
        raise urwid.ExitMainLoop()

    if key in ('up', 'down', 'left', 'right', 'insert', 'delete', 'enter', 'esc'):
        main_view.update(key_stroke=key)


def update(*args):
    global main_view
    global loop

    main_view.update()
    loop.draw_screen()
    loop.set_alarm_in(REFRESH_INTERVAL, update)


main_view = MainView.MainView()
loop = urwid.MainLoop(
    widget=main_view.get_view(),
    palette=PALETTE,
    unhandled_input=exit_on_q,
    handle_mouse=False)

loop.set_alarm_in(0, update)
loop.run()
