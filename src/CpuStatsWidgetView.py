import urwid
import CpuStatsWidgetViewModel


class CpuStatsWidgetView:
    def __init__(self):
        self.view_model = CpuStatsWidgetViewModel.CpuStatsWidgetViewModel()
        self.update()

    def get_view(self):
        return urwid.Text('Here CPU stats')

    def update(self):
        self.view_model.update()
