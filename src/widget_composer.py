import urwid
import json
import importlib
import re
from types import SimpleNamespace

dynamic_modules = {}


def load(path):
    widget_definition = load_json(path)
    widget_interpreted = interpret_definition(widget_definition)
    return widget_interpreted


def load_json(path):
    f = open(path, "r")
    return json.loads(f.read(), object_hook=lambda d: SimpleNamespace(**d))


def interpret_definition(widget_definition):
    global dynamic_modules
    # Read definition
    # Read import source
    dynamic_modules = import_modules(widget_definition)

    # Read content (widget)
    return create_pile(widget_definition)


def import_modules(widget_def):
    modules = {}
    if not hasattr(widget_def, 'import_source'):
        return modules
    for current_module in widget_def.import_source:
        modules[current_module.name] = importlib.import_module(current_module.name, current_module)
    return modules


def read_content(widget_def):
    switcher = {
        'box': lambda: create_box(widget_def),
        'text': lambda: create_text(widget_def),
        'columns': lambda: create_columns(widget_def),
        'pile': lambda: create_pile(widget_def),
        'progress': lambda: create_progress(widget_def),
        'divider': lambda: create_divider(widget_def),

        # TODO
        'repeat_column': lambda: create_divider(widget_def)
    }
    return switcher.get(widget_def.widget_type, 'Invalid widget type -> ' + widget_def.widget_type)()


def create_box(box_widget_def):
    properties = get_properties(box_widget_def)
    return urwid.LineBox(read_content(box_widget_def.content), title=properties.get('title', ''))


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


def create_divider(divider_widget_def):
    properties = get_properties(divider_widget_def)
    return urwid.Filler(urwid.Divider(properties.get('char', '=')))


def create_text(text_widget_def):
    properties = get_properties(text_widget_def)
    return urwid.Filler(urwid.Text(properties.get('value', ''), align=properties.get('align', 'center')))


def create_progress(progress_widget_def):
    properties = get_properties(progress_widget_def)
    return urwid.Filler(
        urwid.ProgressBar(
            normal=properties.get('style_normal', 'progress normal'),
            complete=properties.get('style_complete', 'progress complete'),
            current=int(float(properties.get('value', 77))),
            done=int(properties.get('max', 100))))


def get_properties(widget_def):
    properties = {}
    if not hasattr(widget_def, 'properties'):
        return properties
    properties = dict(x.split('=') for x in widget_def.properties.split(';'))
    for key, token_value in properties.items():
        properties[key] = resolve_token(widget_def, token_value)
    return properties


def resolve_token(widget_def, token):
    for module_name, module in dynamic_modules.items():
        current_module = '@' + module_name + '.'
        while token.find(current_module) != -1:
            method_name = token.split(current_module, 1)[1].split(';', 1)[0]
            replacement_value = str(getattr(module, re.sub('[()]', '', method_name))())
            token = re.sub(current_module + method_name + r'\(\)', replacement_value, token)
    return token
