"""Byte formatting handles empty, large, invalid, and fractional values."""

import pytest

from hctui.formatting import format_bytes, format_rate


@pytest.mark.parametrize(
    "value, expected",
    [
        (0, "0.0 B"),
        (-1, "0.0 B"),
        (1024, "1.0 KiB"),
        (1536, "1.5 KiB"),
        (1024**3, "1.0 GiB"),
        (float("nan"), "N/A"),
        (float("inf"), "N/A"),
    ],
)
def test_format_bytes(value, expected):
    assert format_bytes(value) == expected


def test_format_rate():
    assert format_rate(1024) == "1.0 KiB/s"
