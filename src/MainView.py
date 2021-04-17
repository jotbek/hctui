import urwid
import HintPanelView
import WidgetsAreaView

HCTUI_VERSION = '0.0.5'


class MainView:
    def __init__(self):
        self.widgets_area_view = WidgetsAreaView.WidgetsAreaView()
        self.bottom_menu_view = HintPanelView.HintPanelView()

    def get_view(self, properties={}):
        return urwid.LineBox(
            original_widget=urwid.Frame(
                body=self.widgets_area_view.get_view(),
                footer=self.bottom_menu_view.get_view(properties=properties)),
            title='hctui v.' + HCTUI_VERSION)

    def update(self, key_stroke=None, properties={}):
        self.bottom_menu_view.update(key_stroke=key_stroke, properties=properties)
