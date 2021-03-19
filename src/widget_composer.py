import urwid
import json
from types import SimpleNamespace


def load(path):
    widget_definition = load_json(path)
    widget_interpreted = interpret_definition(widget_definition)
    return widget_interpreted


def load_json(path):
    f = open(path, "r")
    return json.loads(f.read(), object_hook=lambda d: SimpleNamespace(**d))


def interpret_definition(widget_definition):
    # Read definition
    # Read import source
    # Read content (widget)
    return create_pile(widget_definition)


def read_content(widget_def):
    switcher = {
        'box': lambda: create_box(widget_def),
        'text': lambda: create_text(widget_def),
        'columns': lambda: create_columns(widget_def),
        'pile': lambda: create_pile(widget_def)
    }
    return switcher.get(widget_def.widget_type, 'Invalid widget type -> ' + widget_def.widget_type)()


def create_box(box_widget_def):
    properties = get_properties(box_widget_def.properties)
    return urwid.LineBox(urwid.Filler(read_content(box_widget_def.content)), title=properties['title'])


def create_text(text_widget_def):
    return urwid.Text(text_widget_def.value, align='center')


def create_columns(columns_widget_def):
    widget_columns = []
    for current_widget in columns_widget_def.content:
        widget_columns.append(read_content(current_widget))

    return urwid.Columns(widget_columns)


def create_pile(pile_widget_def):
    pile_widgets = []
    for current_widget in pile_widget_def.content:
        pile_widgets.append(read_content(current_widget))
    return urwid.Pile(pile_widgets)


def get_properties(properties_str):
    return dict(x.split('=') for x in properties_str.split(';'))