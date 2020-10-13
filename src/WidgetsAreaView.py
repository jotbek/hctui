import urwid
import cpu_stats

class WidgetsAreaView:
    def __init__(self):
        pass

    def get_view(self):
        return urwid.Filler(
            body=urwid.Pile(
                widget_list=[
                    urwid.Text('CPU count: ' + str(cpu_stats.cpu_count())),
                    urwid.Text('CPU total: ' + str(cpu_stats.cpu_usage_total())),
                    urwid.Text('CPU usage: ' + str(cpu_stats.cpu_usage_per_core()))]),
            valign='top')

    def update(self):
        pass