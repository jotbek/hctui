"""Load YAML once, validate it, and update an existing Urwid widget tree."""

from __future__ import annotations

import ast
import keyword
import math
from dataclasses import dataclass, field
from pathlib import Path
from types import CodeType
from typing import Any, Callable

import urwid
import yaml

from .expressions import HELPERS, DefinitionError, compile_expression, evaluate
from .metrics import SOURCE_NAMES
from .views.compact_widgets import ResponsiveColumns, SparklineWidget, StatusWidget, TableWidget
from .views.layout import FlowColumns, FlowStack

try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader

MAX_DEFINITION_BYTES = 256 * 1024
MAX_DEFINITIONS = 32
MAX_WIDGETS = 2048
MAX_DEPTH = 32

# Property types are checked both at load time and after expression evaluation.
PROPERTY_TYPES = {
    "box": {"title": str},
    "text": {"value": str, "align": str},
    "columns": {"spacing": int},
    "stack": {},
    "progress": {"value": (int, float), "max": (int, float), "normal": str, "complete": str},
    "divider": {"char": str, "top": int, "bottom": int},
    "repeat": {
        "variable": str,
        "start": int,
        "stop": int,
        "columns": int,
        "column_order": list,
        "spacing": int,
    },
    "graph": {"value": (list, tuple), "max": (int, float), "height": int},
    "include": {"path": str},
    "table": {
        "headers": list,
        "rows": (list, tuple),
        "widths": list,
        "compact_columns": list,
        "compact_width": int,
        "max_rows": int,
        "empty": str,
    },
    "status": {"value": str, "state": str},
    "sparkline": {"value": (list, tuple), "max": (int, float), "label": str, "ascii": bool},
    "responsive": {"min_width": int, "spacing": int},
    "conditional": {"visible": bool},
}
CONTAINERS = frozenset({"box", "columns", "stack", "responsive", "conditional"})
STRUCTURAL_PROPERTIES = {
    "repeat": {"start", "stop", "columns", "column_order", "spacing", "variable"},
    "columns": {"spacing"},
    "divider": {"char", "top", "bottom"},
    "graph": {"height"},
    "responsive": {"min_width", "spacing"},
    "conditional": {"visible"},
}


class UniqueKeyLoader(SafeLoader):
    """Safe YAML loader that reports duplicate keys instead of discarding values."""

    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise yaml.constructor.ConstructorError(
                    None,
                    None,
                    "Mapping keys must be strings",
                    key_node.start_mark,
                )
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    None,
                    None,
                    f"Duplicate key: {key}",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


@dataclass
class Binding:
    """A prepared update caching only the latest source references and resolved values."""

    kind: str
    properties: dict[str, Any]
    variables: dict[str, object]
    location: str
    apply: Callable[[dict[str, Any]], None]
    previous: dict[str, Any]
    compiled: dict[str, CodeType] = field(init=False)
    literals: dict[str, Any] = field(init=False)
    dependencies: tuple = field(init=False)
    _references: tuple | None = field(init=False, default=None)
    _resolved: dict | None = field(init=False, default=None)

    def __post_init__(self):
        self.compiled = {}
        self.literals = {}
        for key, value in self.properties.items():
            if isinstance(value, str) and value.startswith("@"):
                self.compiled[key] = compile_expression(value[1:])
            else:
                self.literals[key] = value
        self.dependencies = tuple(
            sorted(
                set().union(*(set(code.co_names) & SOURCE_NAMES for code in self.compiled.values()))
            )
        )

    @property
    def is_dynamic(self) -> bool:
        return bool(self.dependencies)

    def values(self, context: dict[str, object]) -> dict[str, Any]:
        references = tuple(context.get(name) for name in self.dependencies)
        if self._resolved is not None and all(
            current is previous for current, previous in zip(references, self._references)
        ):
            return self._resolved
        scope = {**context, **self.variables} if self.variables else context
        values = self.literals.copy()
        for key, code in self.compiled.items():
            try:
                values[key] = evaluate(code, self.properties[key], scope)
                validate_property(self.kind, key, values[key])
            except DefinitionError as error:
                raise DefinitionError(f"{self.location}.properties.{key}: {error}") from error
        if self.kind == "table":
            headers = values.get("headers", [])
            rows = values.get("rows", ())
            widths = values.get("widths", [])
            columns = values.get("compact_columns", list(range(len(headers))))
            if (
                not headers
                or widths
                and len(widths) != len(headers)
                or any(index >= len(headers) for index in columns)
                or any(len(row) != len(headers) for row in rows)
            ):
                raise DefinitionError(f"{self.location}: Table columns and rows must match headers")
        self._references, self._resolved = references, values
        return values


def validate_property(kind: str, key: str, value: Any) -> None:
    """Validate literal and resolved property values without an extra runtime dependency."""
    expected = PROPERTY_TYPES[kind][key]
    if (isinstance(value, bool) and expected is not bool) or not isinstance(value, expected):
        raise DefinitionError(f"Invalid value {value!r}")
    if isinstance(value, (int, float)) and not math.isfinite(value):
        raise DefinitionError("Number must be finite")
    if key in {"spacing", "top", "bottom", "start", "stop"} and value < 0:
        raise DefinitionError("Value must be non-negative")
    if key in {"height", "columns"} and not 1 <= value <= 256:
        raise DefinitionError("Value must be between 1 and 256")
    if key == "max" and value <= 0:
        raise DefinitionError("Maximum must be positive")
    if key == "align" and value not in {"left", "center", "right"}:
        raise DefinitionError("Alignment must be left, center, or right")
    if key == "char" and len(value) > 1:
        raise DefinitionError("Divider character must contain at most one character")
    if key == "variable" and (
        not value.isidentifier()
        or not value.isascii()
        or keyword.iskeyword(value)
        or value.startswith("_")
        or value in HELPERS
        or value in SOURCE_NAMES
    ):
        raise DefinitionError(
            "Loop variable must be a public name distinct from sources and helpers"
        )
    if kind in {"graph", "sparkline"} and key == "value":
        if len(value) > 600 or any(
            isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item)
            for item in value
        ):
            raise DefinitionError("Graph data must contain at most 600 finite numbers")
    if key == "column_order" and (
        not value
        or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in value)
    ):
        raise DefinitionError("Column order must be a non-empty list of non-negative integers")
    if key == "state" and value not in {"ok", "warning", "critical", "unknown"}:
        raise DefinitionError("Status must be ok, warning, critical, or unknown")
    if key in {"min_width", "compact_width"} and not 20 <= value <= 512:
        raise DefinitionError("Width threshold must be between 20 and 512")
    if key == "max_rows" and not 1 <= value <= 128:
        raise DefinitionError("Row limit must be between 1 and 128")
    if key == "headers" and (
        not 1 <= len(value) <= 16 or any(not isinstance(cell, str) for cell in value)
    ):
        raise DefinitionError("Table requires 1-16 string headers")
    if key in {"widths", "compact_columns"} and (
        len(value) > 16 or any(type(item) is not int or not 0 <= item <= 512 for item in value)
    ):
        raise DefinitionError("Column settings must contain at most 16 non-negative integers")
    if key == "compact_columns" and (not value or len(set(value)) != len(value)):
        raise DefinitionError("Compact columns must be unique and non-empty")
    if key == "rows" and (
        len(value) > 128
        or any(
            not isinstance(row, (tuple, list))
            or len(row) > 16
            or any(
                cell is not None and not isinstance(cell, (str, int, float, bool)) for cell in row
            )
            for row in value
        )
    ):
        raise DefinitionError("Tables support up to 128 rows of at most 16 scalar cells")


class WidgetComposer:
    """Prepare definitions once and reuse widgets until an explicit reload or layout change."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._definitions: dict[Path, dict[str, Any]] = {}
        self._bindings: list[Binding] = []
        self._structures: list[Binding] = []
        self._widgets: list[urwid.Widget] | None = None
        self._build_count = 0
        self._validation_count = 0
        self.page_index = 0
        self._page_states = {}
        self._page_node_counts = {}
        self._source_cache = {}
        self._load_document(self.path, ())
        self.sources = frozenset(
            source for document in self._definitions.values() for source in document["sources"]
        )
        root = self._definitions[self.path]
        self.page_names = tuple(page["name"] for page in root.get("pages", []))
        self.intervals = {}
        for path, document in self._definitions.items():
            if path != self.path:
                self.intervals.update(document.get("intervals", {}))
        self.intervals.update(root.get("intervals", {}))
        self._page_sources = []
        for page in root.get("pages", [{"widgets": root.get("widgets", [])}]):
            needed = set(root["sources"]) | set(page.get("sources", []))
            self._collect_sources(page["widgets"], self.path, needed)
            self._page_sources.append(frozenset(needed))
        self.sources = self.sources | frozenset().union(*self._page_sources)

    @property
    def required_sources(self):
        return self._page_sources[self.page_index]

    def select_page(self, index):
        if not 0 <= index < len(self._page_sources):
            return
        self._page_states[self.page_index] = (self._widgets, self._bindings, self._structures)
        self.page_index = index
        self._widgets, self._bindings, self._structures = self._page_states.get(
            index, (None, [], [])
        )

    def _collect_sources(self, nodes, path, needed):
        for node in nodes:
            for reference in self._includes(node):
                included = (path.parent / reference).resolve()
                document = self._definitions[included]
                if included not in self._source_cache:
                    local = set(document["sources"])
                    self._collect_sources(document["widgets"], included, local)
                    self._source_cache[included] = frozenset(local)
                needed.update(self._source_cache[included])

    def _load_document(self, path: Path, ancestors: tuple[Path, ...]) -> None:
        if path in ancestors:
            raise DefinitionError(f"Circular include: {' -> '.join(map(str, (*ancestors, path)))}")
        if len(ancestors) >= MAX_DEPTH:
            raise DefinitionError(f"{path}: Include nesting exceeds {MAX_DEPTH}")
        if path in self._definitions:
            return
        if len(self._definitions) >= MAX_DEFINITIONS:
            raise DefinitionError(f"Dashboard exceeds {MAX_DEFINITIONS} definition files")
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_DEFINITION_BYTES + 1)
            if len(raw) > MAX_DEFINITION_BYTES:
                raise DefinitionError(f"{path}: Definition exceeds {MAX_DEFINITION_BYTES} bytes")
            document = yaml.load(raw.decode("utf-8"), Loader=UniqueKeyLoader)
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            raise DefinitionError(f"{path}: {error}") from error
        if not isinstance(document, dict):
            raise DefinitionError(f"{path}: Definition must be a mapping")
        unknown = document.keys() - {
            "schema_version",
            "name",
            "sources",
            "widgets",
            "pages",
            "intervals",
        }
        if unknown:
            raise DefinitionError(f"{path}: Unknown definition fields: {sorted(unknown)}")
        if type(document.get("schema_version")) is not int or document["schema_version"] != 2:
            raise DefinitionError(f"{path}: schema_version must be 2")
        if not isinstance(document.get("name"), str) or not document["name"]:
            raise DefinitionError(f"{path}: name must be a non-empty string")
        sources = document.get("sources", [])
        if (
            not isinstance(sources, list)
            or any(not isinstance(source, str) or source not in SOURCE_NAMES for source in sources)
            or len(set(sources)) != len(sources)
        ):
            raise DefinitionError(f"{path}: sources must list unique supported metric names")
        document["sources"] = sources
        intervals = document.get("intervals", {})
        if not isinstance(intervals, dict) or any(
            name not in SOURCE_NAMES
            or name == "alerts"
            or type(interval) not in (int, float)
            or not math.isfinite(interval)
            or not 0 <= interval <= 3600
            for name, interval in intervals.items()
        ):
            raise DefinitionError(f"{path}: intervals must map sources to finite seconds (0-3600)")
        if "pages" in document:
            pages = document["pages"]
            if (
                ancestors
                or "widgets" in document
                or not isinstance(pages, list)
                or not 1 <= len(pages) <= 9
            ):
                raise DefinitionError(
                    f"{path}: Only the root may define 1-9 pages instead of widgets"
                )
            names = set()
            for page in pages:
                if (
                    not isinstance(page, dict)
                    or page.keys() - {"name", "sources", "widgets"}
                    or not isinstance(page.get("name"), str)
                    or not page["name"]
                    or page["name"] in names
                    or len(page["name"]) > 24
                ):
                    raise DefinitionError(f"{path}: Pages require unique names up to 24 characters")
                names.add(page["name"])
                if not isinstance(page.get("sources", []), list) or any(
                    not isinstance(name, str) or name not in SOURCE_NAMES
                    for name in page.get("sources", [])
                ):
                    raise DefinitionError(f"{path}: Unknown page sources")
        else:
            pages = [{"widgets": document.get("widgets")}]
        self._definitions[path] = document
        for page in pages:
            if not isinstance(page.get("widgets"), list) or not page["widgets"]:
                raise DefinitionError(f"{path}: widgets must be a non-empty list")
            for index, node in enumerate(page["widgets"]):
                self._validate_node(
                    node,
                    f"{path}:widgets[{index}]",
                    set(sources) | set(page.get("sources", [])),
                    set(),
                    0,
                )
                for reference in self._includes(node):
                    self._load_document((path.parent / reference).resolve(), (*ancestors, path))

    def _validate_node(self, node, location, sources, variables, depth) -> None:
        self._validation_count += 1
        if self._validation_count > MAX_WIDGETS:
            raise DefinitionError(f"{location}: Definition exceeds {MAX_WIDGETS} nodes")
        if depth >= MAX_DEPTH:
            raise DefinitionError(f"{location}: Widget nesting exceeds {MAX_DEPTH}")
        if (
            not isinstance(node, dict)
            or not isinstance(node.get("type"), str)
            or node["type"] not in PROPERTY_TYPES
        ):
            raise DefinitionError(f"{location}: Unknown or missing widget type")
        kind = node["type"]
        allowed = {"type", "properties"}
        if kind in CONTAINERS:
            allowed.add("children")
        if kind == "repeat":
            allowed.add("template")
        unknown = node.keys() - allowed
        if unknown:
            raise DefinitionError(f"{location}: Unknown fields: {sorted(unknown)}")
        properties = node.get("properties", {})
        if not isinstance(properties, dict):
            raise DefinitionError(f"{location}: properties must be a mapping")
        for key, value in properties.items():
            if key not in PROPERTY_TYPES[kind]:
                raise DefinitionError(f"{location}: Unknown {kind} property: {key}")
            if isinstance(value, str) and value.startswith("@"):
                if key in {"path", "variable"}:
                    raise DefinitionError(f"{location}: {key} must be a literal string")
                try:
                    compile_expression(value[1:])
                except DefinitionError as error:
                    raise DefinitionError(f"{location}.properties.{key}: {error}") from error
                names = {
                    n.id
                    for n in ast.walk(ast.parse(value[1:], mode="eval"))
                    if isinstance(n, ast.Name)
                }
                missing = names - sources - variables - HELPERS.keys()
                if missing:
                    raise DefinitionError(
                        f"{location}.properties.{key}: Unknown names: {sorted(missing)}"
                    )
            else:
                try:
                    validate_property(kind, key, value)
                except DefinitionError as error:
                    raise DefinitionError(f"{location}.properties.{key}: {error}") from error
        if kind in CONTAINERS:
            children = node.get("children")
            if not isinstance(children, list) or not children:
                raise DefinitionError(f"{location}: children must be a non-empty list")
            if kind == "box" and len(children) != 1:
                raise DefinitionError(f"{location}: A box requires exactly one child")
            for index, child in enumerate(children):
                self._validate_node(
                    child, f"{location}.children[{index}]", sources, variables, depth + 1
                )
        if kind == "repeat":
            if "stop" not in properties or "template" not in node:
                raise DefinitionError(f"{location}: A repeat requires stop and template")
            variable = properties.get("variable", "i")
            validate_property(kind, "variable", variable)
            if variable in variables:
                raise DefinitionError(f"{location}: Nested loops must use distinct variables")
            self._validate_node(
                node["template"], f"{location}.template", sources, variables | {variable}, depth + 1
            )
        if kind == "include" and not properties.get("path"):
            raise DefinitionError(f"{location}: An include requires a non-empty path")

    def _includes(self, node):
        if node["type"] == "include":
            yield node["properties"]["path"]
        for child in node.get("children", []):
            yield from self._includes(child)
        if "template" in node:
            yield from self._includes(node["template"])

    def _binding(self, node, variables, location, context, apply):
        binding = Binding(
            node["type"], node.get("properties", {}), variables.copy(), location, apply, {}
        )
        values = binding.values(context)
        apply(values)
        binding.previous = values
        if binding.is_dynamic:
            self._bindings.append(binding)
        return values

    def _structure(self, node, variables, location, context):
        properties = {
            key: value
            for key, value in node.get("properties", {}).items()
            if key in STRUCTURAL_PROPERTIES.get(node["type"], set())
        }
        if not properties:
            return {}
        binding = Binding(
            node["type"], properties, variables.copy(), location, lambda values: None, {}
        )
        binding.previous = binding.values(context)
        if binding.is_dynamic:
            self._structures.append(binding)
        return binding.previous

    def _build_document(self, path, context, variables):
        document = self._definitions[path]
        nodes = (
            document["pages"][self.page_index]["widgets"]
            if "pages" in document
            else document["widgets"]
        )
        return [
            self._build(node, path, context, variables, f"{path}:widgets[{index}]")
            for index, node in enumerate(nodes)
        ]

    def _build(self, node, path, context, variables, location):
        self._build_count += 1
        cached_count = sum(
            count for index, count in self._page_node_counts.items() if index != self.page_index
        )
        if self._build_count + cached_count > MAX_WIDGETS:
            raise DefinitionError(f"{location}: Dashboard exceeds {MAX_WIDGETS} widgets")
        kind = node["type"]
        structural = self._structure(node, variables, location, context)
        if kind == "include":
            child_path = (path.parent / node["properties"]["path"]).resolve()
            children = self._build_document(child_path, context, variables)
            return children[0] if len(children) == 1 else FlowStack(children)
        if kind == "conditional" and not structural.get("visible", True):
            return urwid.Text("")
        if kind in CONTAINERS:
            children = [
                self._build(child, path, context, variables, f"{location}.children[{index}]")
                for index, child in enumerate(node["children"])
            ]
            if kind in {"stack", "conditional"}:
                return children[0] if len(children) == 1 else FlowStack(children)
            if kind == "columns":
                return FlowColumns(children, dividechars=structural.get("spacing", 1))
            if kind == "responsive":
                return ResponsiveColumns(
                    children, structural.get("min_width", 80), structural.get("spacing", 1)
                )
            widget = urwid.LineBox(urwid.AttrMap(children[0], "body"))
            self._binding(
                node, variables, location, context, lambda p: widget.set_title(p.get("title", ""))
            )
            return urwid.AttrMap(widget, "border")
        if kind == "repeat":
            start, stop = structural.get("start", 0), structural["stop"]
            columns = structural.get("columns", 1)
            order = structural.get("column_order", list(range(columns)))
            if stop < start or stop - start > 256 or any(index >= columns for index in order):
                raise DefinitionError(f"{location}: Invalid repeat range or column order")
            if stop == start:
                return urwid.Text("")
            children = [[] for _ in range(columns)]
            for index, value in enumerate(range(start, stop)):
                scope = {**variables, structural.get("variable", "i"): value}
                children[order[index % len(order)]].append(
                    self._build(
                        node["template"], path, context, scope, f"{location}.template[{value}]"
                    )
                )
            return FlowColumns(
                [FlowStack(items) if items else urwid.Text("") for items in children],
                dividechars=structural.get("spacing", 1),
            )
        if kind == "divider":
            return urwid.Divider(
                structural.get("char", " "),
                top=structural.get("top", 0),
                bottom=structural.get("bottom", 0),
            )
        if kind == "text":
            widget = urwid.Text("")

            def update_text(properties):
                widget.set_text(properties.get("value", ""))
                widget.set_align_mode(properties.get("align", "left"))

            self._binding(node, variables, location, context, update_text)
            return widget
        if kind == "progress":
            widget = urwid.ProgressBar("progress_normal", "progress_complete")

            def update_progress(properties):
                widget.normal = properties.get("normal", "progress_normal")
                widget.complete = properties.get("complete", "progress_complete")
                widget.done = properties.get("max", 100)
                widget.set_completion(max(0, min(widget.done, properties.get("value", 0))))

            self._binding(node, variables, location, context, update_progress)
            return widget
        if kind == "graph":
            widget = urwid.BarGraph(
                ["graph_background", "graph_complete"], satt={(1, 0): "graph_smooth"}
            )

            def update_graph(properties):
                maximum = properties.get("max", 100)
                data = [(max(0, min(maximum, value)),) for value in properties.get("value", [])]
                widget.set_data(data, maximum)

            self._binding(node, variables, location, context, update_graph)
            return urwid.BoxAdapter(widget, structural.get("height", 4))
        if kind in {"table", "status", "sparkline"}:
            widget = {"table": TableWidget, "status": StatusWidget, "sparkline": SparklineWidget}[
                kind
            ]()
            self._binding(node, variables, location, context, widget.update)
            return widget
        raise AssertionError(f"Unreachable widget type: {kind}")

    def update(self, context: dict[str, object]) -> list[urwid.Widget]:
        """Update changed values; rebuild only when a structural expression changes."""
        if self._widgets is None or any(
            binding.values(context) != binding.previous for binding in self._structures
        ):
            old_state = (self._widgets, self._bindings, self._structures)
            self._bindings, self._structures, self._build_count = [], [], 0
            try:
                self._widgets = self._build_document(self.path, context, {})
                self._page_node_counts[self.page_index] = self._build_count
            except (DefinitionError, TypeError, ValueError) as error:
                self._widgets, self._bindings, self._structures = old_state
                raise DefinitionError(f"{self.path}: {error}") from error
        else:
            # Resolve everything first so an invalid expression cannot half-update the display.
            updates = [(binding, binding.values(context)) for binding in self._bindings]
            for binding, values in updates:
                if values != binding.previous:
                    binding.apply(values)
                    binding.previous = values
        return self._widgets
