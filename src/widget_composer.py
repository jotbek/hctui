import urwid
import json
import importlib
from types import SimpleNamespace
import math

external_dependencies = {}


def load(path):
    widget_definition = load_json(path)
    widget_interpreted = interpret_definition(widget_definition)
    return widget_interpreted


def load_json(path):
    f = open(path, "r")
    return json.loads(f.read(), object_hook=lambda d: SimpleNamespace(**d))


# noinspection PyTypeChecker
def interpret_definition(widget_definition):
    global external_dependencies
    # Read definition
    # Read import source and add math library for math operations
    external_dependencies = import_modules(widget_definition)
    external_dependencies['math'] = math
    external_dependencies['str'] = str

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
        'repeat_columns': lambda: create_repeat_columns(widget_def)
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
    v = int(float(properties.get('value', 77)))
    return urwid.Filler(
        urwid.ProgressBar(
            normal=properties.get('style_normal', 'progress normal'),
            complete=properties.get('style_complete', 'progress complete'),
            current=v,
            done=int(properties.get('max', 100))))


def create_repeat_columns(repeat_columns_widget_def):
    global external_dependencies
    # Read relevant properties with default values
    properties = get_properties(repeat_columns_widget_def)
    _from = int(properties.get('from', ''))
    to = int(properties.get('to', ''))
    no_columns = int(properties.get('no_columns', str(to - _from)))
    loop_in_columns = list(properties.get('loop_in_columns', str(no_columns)).split(','))

    # Generate empty list of lists which become later a input for a Pile
    widget_columns = [[] for _ in range(0, no_columns)]
    idx = 0
    for x in range(_from, to + 1):
        # change a value of a variable when resolving token (it is included in locals())
        external_dependencies[properties.get('variable', 'i')] = x
        if idx > len(loop_in_columns) - 1:
            idx = 0
        widget_columns[int(loop_in_columns[idx])].append(read_content(repeat_columns_widget_def.content))
        idx += 1

    for x in range(0, no_columns):
        widget_columns[x] = urwid.Pile(widget_columns[x])
    return urwid.Columns(widget_columns)


def get_properties(widget_def):
    properties = {}
    if not hasattr(widget_def, 'properties'):
        return properties
    properties = dict(x.split('=') for x in widget_def.properties.split(';'))
    for key, token_value in properties.items():
        properties[key] = \
            resolve_token(widget_def, token_value) if token_value.startswith('@') else token_value
    return properties


def resolve_token(widget_def, token):
    global external_dependencies
    result = eval(token[1:], {'__builtins__': None}, external_dependencies)
    return result
