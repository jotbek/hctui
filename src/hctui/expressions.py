"""Bounded expression compilation for widget properties, without arbitrary calls."""

from __future__ import annotations

import ast
from functools import lru_cache
from types import CodeType
from typing import Any

from .formatting import format_bytes, format_duration, format_rate, format_temperature

HELPERS = {
    "str": str,
    "len": len,
    "round": round,
    "min": min,
    "max": max,
    "abs": abs,
    "int": int,
    "float": float,
    "format_bytes": format_bytes,
    "format_rate": format_rate,
    "format_duration": format_duration,
    "format_temperature": format_temperature,
}
EXPRESSION_GLOBALS = {"__builtins__": {}, **HELPERS}
ALLOWED_NODES = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Subscript,
    ast.Slice,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Call,
    ast.keyword,
    ast.JoinedStr,
    ast.FormattedValue,
    ast.List,
    ast.Tuple,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
)


class DefinitionError(ValueError):
    """A widget definition could not be loaded, validated, or evaluated."""


@lru_cache(maxsize=256)
def compile_expression(expression: str) -> CodeType:
    """Compile a small expression language; definitions are still trusted local files."""
    if len(expression) > 4096:
        raise DefinitionError("Expression exceeds 4096 characters")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise DefinitionError(f"Invalid expression: {expression!r}") from error
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise DefinitionError(f"Unsupported expression operation: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise DefinitionError("Private names are not allowed in expressions")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise DefinitionError("Private attributes are not allowed in expressions")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in HELPERS:
                raise DefinitionError("Expressions may only call documented formatting helpers")
            if any(keyword.arg is None for keyword in node.keywords):
                raise DefinitionError("Keyword unpacking is not allowed")
    return compile(tree, "<widget expression>", "eval")


def evaluate(code: CodeType, expression: str, context: dict[str, object]) -> Any:
    """Evaluate already compiled code without consulting a compilation cache."""
    try:
        return eval(code, EXPRESSION_GLOBALS, context)
    except DefinitionError:
        raise
    except (
        AttributeError,
        NameError,
        TypeError,
        ValueError,
        IndexError,
        KeyError,
        ZeroDivisionError,
        OverflowError,
    ) as error:
        raise DefinitionError(f"Cannot evaluate {expression!r}: {error}") from error


def resolve(value: Any, context: dict[str, object]) -> Any:
    """Return a literal property or evaluate an ``@`` expression."""
    if not isinstance(value, str) or not value.startswith("@"):
        return value
    return evaluate(compile_expression(value[1:]), value, context)
