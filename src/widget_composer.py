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
    return urwid.Filler(urwid.Text('DUMMY WIDGET'))
