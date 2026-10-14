"""Flow-only containers for the dashboard's flow-only widget language."""

import urwid


class FlowColumns(urwid.Columns):
    """Avoid recursively checking child sizing capabilities on every render."""

    _sizing = frozenset({urwid.FLOW})

    def sizing(self):
        return self._sizing


class FlowStack(urwid.Pile):
    """A vertical flow layout with a constant sizing contract."""

    _sizing = frozenset({urwid.FLOW})

    def sizing(self):
        return self._sizing
