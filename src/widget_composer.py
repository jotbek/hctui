import urwid
import json
import importlib
import uuid
from types import SimpleNamespace
import math

external_dependencies = {}
widget_definition_cache = {}
widget_caching = True
session_id = None
modules = {}


def load(path):
    global widget_definition_cache

    if path not in widget_definition_cache or widget_definition_cache[path][1]:
        widget_definition_cache[path] = (load_json(path), widget_caching)

    widget_interpreted = interpret_definition(widget_definition_cache[path][0], widget_definition_cache[path][1])
    return widget_interpreted


def load_json(path):
    f = open(path, "r")
    return json.loads(f.read(), object_hook=lambda d: SimpleNamespace(**d))


# noinspection PyTypeChecker
def interpret_definition(widget_definition, use_cache=False):
    global external_dependencies
    # Read definition
    # Read import source and add math library for math operations
    external_dependencies = import_modules(widget_definition, use_cache)
    external_dependencies['math'] = math
    external_dependencies['str'] = str

    # Read content (widget)
    return urwid.Filler(create_pile(widget_definition), 'top')


def import_modules(widget_def, use_cached_modules=False):
    global modules

    if not hasattr(widget_def, 'import_source'):
        return {}

    # Reload when force reload or no modules loaded (first load dict modules empty)
    if not use_cached_modules or not modules:
        for current_module in widget_def.import_source:
            modules[current_module.name] = importlib.import_module(current_module.name, current_module)

    for current_module in widget_def.import_source:
        if current_module.enable_cache:
            eval(
                current_module.name + '.init_cache_session(\'' + str(uuid.uuid4()) + '\')',
                {'__builtins__': None},
                modules)

    return modules


def read_content(widget_def):
    switcher = {
        'box': lambda: create_box(widget_def),
        'text': lambda: create_text(widget_def),
        'columns': lambda: create_columns(widget_def),
        'pile': lambda: create_pile(widget_def),
        'progress': lambda: create_progress(widget_def),
        'divider': lambda: create_divider(widget_def),
        'repeat_columns': lambda: create_repeat_columns(widget_def),
        'graph': lambda: create_graph(widget_def)
    }
    return switcher.get(widget_def.widget_type, 'Invalid widget type -> ' + widget_def.widget_type)()


def create_graph(graph_widget_def):
    properties = get_properties(graph_widget_def)
    graph = urwid.BarGraph(
        ['bg background', 'bg 1', 'bg 2'],
        satt={(1, 0): 'bg 1 smooth', (2, 0): 'bg 2 smooth'})
    graph_data = properties.get('value', [0] * 20)
    graph.set_data(list(zip(graph_data, [0] * len(graph_data))), 100.0)
    return urwid.BoxAdapter(graph, int(properties.get('height', 2)))


def create_box(box_widget_def):
    properties = get_properties(box_widget_def)
    return urwid.LineBox(
        original_widget=read_content(box_widget_def.content),
        title=properties.get('title', ''))


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


def create_listbox(listbox_widget_def):
    listbox_widgets = []
    for current_widget in listbox_widget_def.content:
        listbox_widgets.append(read_content(current_widget))
    return urwid.ListBox()


def create_divider(divider_widget_def):
    properties = get_properties(divider_widget_def)
    return urwid.Filler(urwid.Divider(properties.get('char', '=')))


def create_text(text_widget_def):
    properties = get_properties(text_widget_def)
    return urwid.Text(properties.get('value', ''), align=properties.get('align', 'center'))


def create_progress(progress_widget_def):
    properties = get_properties(progress_widget_def)
    return urwid.ProgressBar(
            normal=properties.get('style_normal', 'progress normal'),
            complete=properties.get('style_complete', 'progress complete'),
            current=int(float(properties.get('value', '99'))),
            done=int(properties.get('max', 100)))


def create_repeat_columns(repeat_columns_widget_def):
    global external_dependencies
    # Read relevant properties with default values
    properties = get_properties(repeat_columns_widget_def)
    _from = int(properties.get('from', '0'))
    to = int(properties.get('to', ''))
    no_columns = int(properties.get('no_columns', str(to - _from)))
    loop_in_columns = list(
        properties.get(
            'loop_in_columns',
            ','.join(str(x) for x in range(no_columns)))
        .split(','))

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
