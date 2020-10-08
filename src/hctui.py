import urwid
import MainView

POLL_INTERVAL_SEC = 5
PALETTE = []


def exit_on_q(key):
    if key in ('q', 'Q'):
        raise urwid.ExitMainLoop()


def update(*args):
    global mainView
    global loop

    mainView.update()
    loop.draw_screen()
    loop.set_alarm_in(POLL_INTERVAL_SEC, update)


mainView = MainView.MainView()
loop = urwid.MainLoop(
    widget=mainView.get_view(),
    palette=PALETTE,
    unhandled_input=exit_on_q,
    handle_mouse=True)
loop.set_alarm_in(0, update)
loop.run()
