"""Generate the editor schema from the same property registry as runtime validation."""

from __future__ import annotations

import argparse
import json
import keyword
from pathlib import Path

from hctui.expressions import HELPERS
from hctui.metrics import SOURCE_NAMES
from hctui.widget_composer import CONTAINERS, PROPERTY_TYPES

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src/hctui/widget_schema.json"


def property_schema(kind: str, key: str, expected) -> dict:
    if expected is bool:
        literal = {"type": "boolean"}
    elif expected is str:
        literal = {"type": "string"}
    elif expected is int:
        literal = {"type": "integer"}
    elif expected == (int, float):
        literal = {"type": "number"}
    else:
        literal = {"type": "array"}
    if key in {"spacing", "top", "bottom", "start", "stop"}:
        literal["minimum"] = 0
    if key in {"height", "columns"}:
        literal.update(minimum=1, maximum=256)
    if key == "max":
        literal["exclusiveMinimum"] = 0
    if key == "align":
        literal["enum"] = ["left", "center", "right"]
    if key == "char":
        literal["maxLength"] = 1
    if key == "column_order":
        literal.update(minItems=1, items={"type": "integer", "minimum": 0})
    if kind in {"graph", "sparkline"} and key == "value":
        literal.update(maxItems=600, items={"type": "number"})
    if key in {"min_width", "compact_width"}:
        literal.update(minimum=20, maximum=512)
    if key == "max_rows":
        literal.update(minimum=1, maximum=128)
    if key == "headers":
        literal.update(minItems=1, maxItems=16, items={"type": "string"})
    if key in {"widths", "compact_columns"}:
        literal.update(maxItems=16, items={"type": "integer", "minimum": 0, "maximum": 512})
    if key == "compact_columns":
        literal.update(minItems=1, uniqueItems=True)
    if key == "rows":
        literal.update(
            maxItems=128,
            items={
                "type": "array",
                "maxItems": 16,
                "items": {"type": ["string", "number", "boolean", "null"]},
            },
        )
    if key == "state":
        literal["enum"] = ["ok", "warning", "critical", "unknown"]
    if key in {"path", "variable"}:
        literal.update(minLength=1, **{"not": {"pattern": "^@"}})
        if key == "variable":
            literal["pattern"] = "^[A-Za-z][A-Za-z0-9_]*$"
            literal["not"] = {"enum": sorted(set(keyword.kwlist) | SOURCE_NAMES | HELPERS.keys())}
        return literal
    if expected is str:
        literal["not"] = {"pattern": "^@"}
    return {"anyOf": [literal, {"$ref": "#/$defs/expression"}]}


def generate_schema() -> dict:
    variants = []
    for kind, properties in PROPERTY_TYPES.items():
        property_definition = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                key: property_schema(kind, key, value) for key, value in properties.items()
            },
        }
        node = {
            "type": "object",
            "additionalProperties": False,
            "required": ["type"],
            "properties": {"type": {"const": kind}, "properties": property_definition},
        }
        if kind in CONTAINERS:
            children = {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/widget"}}
            if kind == "box":
                children["maxItems"] = 1
            node["properties"]["children"] = children
            node["required"].append("children")
        if kind == "repeat":
            node["properties"]["template"] = {"$ref": "#/$defs/widget"}
            node["required"].extend(["properties", "template"])
            property_definition["required"] = ["stop"]
        if kind == "include":
            node["required"].append("properties")
            property_definition["required"] = ["path"]
        variants.append(node)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "hctui widget definition, version 2",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "name"],
        "oneOf": [{"required": ["widgets"]}, {"required": ["pages"]}],
        "properties": {
            "schema_version": {"const": 2, "type": "integer"},
            "name": {"type": "string", "minLength": 1},
            "sources": {
                "type": "array",
                "uniqueItems": True,
                "items": {"enum": sorted(SOURCE_NAMES)},
            },
            "widgets": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/widget"}},
            "pages": {
                "type": "array",
                "minItems": 1,
                "maxItems": 9,
                "items": {"$ref": "#/$defs/page"},
            },
            "intervals": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    name: {"type": "number", "minimum": 0, "maximum": 3600}
                    for name in sorted(SOURCE_NAMES - {"alerts"})
                },
            },
        },
        "$defs": {
            "expression": {"type": "string", "pattern": "^@.+", "maxLength": 4097},
            "widget": {"oneOf": variants},
            "page": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "widgets"],
                "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 24},
                    "sources": {
                        "type": "array",
                        "uniqueItems": True,
                        "items": {"enum": sorted(SOURCE_NAMES)},
                    },
                    "widgets": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"$ref": "#/$defs/widget"},
                    },
                },
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check for schema drift")
    arguments = parser.parse_args()
    generated = json.dumps(generate_schema(), indent=2) + "\n"
    if arguments.check:
        if SCHEMA_PATH.read_text(encoding="utf-8") != generated:
            raise SystemExit("Widget schema is outdated; run scripts/generate_widget_schema.py")
        print("Widget schema is up to date")
    else:
        SCHEMA_PATH.write_text(generated, encoding="utf-8")


if __name__ == "__main__":
    main()
