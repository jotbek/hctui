import urwid
import widget_composer


definition_path = '../widgets_source/widget_hctui.json'
#definition_path = '../widgets_source/test_cpu_widget.json'
#definition_path = '../widgets_source/net_widget.json'


class WidgetsAreaView:
    def get_view(self):
        return widget_composer.load(definition_path)
