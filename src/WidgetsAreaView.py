import urwid
import cpu_stats
import widget_container


def wrap_it_up(widget, use_line_box=True):
    if not use_line_box:
        return widget
    return urwid.LineBox(widget)


class WidgetsAreaView:
    def __init__(self):
        pass

    def get_view(self):
        return urwid.Filler(
            body=urwid.Pile(
                widget_list=[
                    wrap_it_up(widget_container.get_cpu_widget()),
                    wrap_it_up(widget_container.get_ram_widget()),
                    wrap_it_up(widget_container.get_net_widget()),
                    wrap_it_up(widget_container.get_disk_widget())]),
            valign='top')

    def update(self):
        pass