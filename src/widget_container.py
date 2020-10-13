import urwid
import CpuStatsWidgetView


def get_widgets(name):
    return {
        'cpu': get_cpu_widget(),
        'ram': get_ram_widget(),
        'net': get_net_widget(),
        'disk': get_disk_widget(),
    }[name]


def get_cpu_widget():
    return CpuStatsWidgetView.CpuStatsWidgetView().get_view()


def get_ram_widget():
    return urwid.LineBox(urwid.Text('-- RAM WIDGET --'))


def get_net_widget():
    return urwid.LineBox(urwid.Text('-- NET WIDGET --'))


def get_disk_widget():
    return urwid.LineBox(urwid.Text('-- DISK WIDGET --'))
