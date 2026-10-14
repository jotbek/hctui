"""Complete, standalone HTML snapshots written only on an explicit request."""

from __future__ import annotations

import html
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .sampling import BackgroundSampler


def serializable(value):
    """Preserve snapshot field names, including nested row and history values."""
    if hasattr(value, "_asdict"):
        return {key: serializable(item) for key, item in value._asdict().items()}
    if isinstance(value, dict):
        return {str(key): serializable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [serializable(item) for item in value]
    return value


def snapshot_report(context, metadata):
    return {
        "report_version": 1,
        "application": f"hctui {__version__}",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "units": {
            "bytes": "bytes",
            "rates": "bytes/second",
            "temperature": "Celsius",
            "cpu": "percent",
            "process_cpu": "100% = one logical CPU",
            "history": "ordered samples, oldest first",
            "sample_age": "seconds",
        },
        "sampling": metadata,
        "measurements": serializable(context),
    }


def _value_html(value):
    if isinstance(value, dict):
        return (
            "<table>"
            + "".join(
                f"<tr><th>{html.escape(str(key))}</th><td>{_value_html(item)}</td></tr>"
                for key, item in value.items()
            )
            + "</table>"
        )
    if isinstance(value, list):
        if value and all(isinstance(row, list) for row in value):
            return (
                "<table>"
                + "".join(
                    "<tr>" + "".join(f"<td>{_value_html(cell)}</td>" for cell in row) + "</tr>"
                    for row in value
                )
                + "</table>"
            )
        return html.escape(", ".join(str(item) for item in value)) or "<span>None</span>"
    return html.escape(str(value)) if value is not None else "<span>N/A</span>"


class _WriteReport:
    def __init__(self, payload, directory):
        self.payload = payload
        self.directory = Path(directory)

    def sample(self, now):
        self.directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        descriptor, temporary = tempfile.mkstemp(prefix=".hctui-", dir=self.directory)
        destination = Path(temporary).with_name(
            f"hctui-{timestamp}-{Path(temporary).name[7:]}.html"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(
                    "<!doctype html><html lang='en'><meta charset='utf-8'>"
                    "<meta name='viewport' content='width=device-width'>"
                    "<title>hctui snapshot</title><style>"
                    "body{font:16px system-ui;margin:2em auto;max-width:1000px;"
                    "padding:0 1em;background:#111820;color:#d4dde8}"
                    "table{border-collapse:collapse;width:100%;margin:.5em 0}"
                    "td,th{border:1px solid #384554;padding:.4em;text-align:left;"
                    "vertical-align:top;overflow-wrap:anywhere}th{color:#79d7ef}"
                    "pre{white-space:pre-wrap;overflow-wrap:anywhere}"
                    "a{color:#79d7ef}span{color:#8c9aaa}</style><h1>hctui snapshot</h1>"
                )
                stream.write(
                    _value_html(
                        {key: value for key, value in self.payload.items() if key != "measurements"}
                    )
                )
                stream.write(
                    "<p>Cached measurements have independent timestamps. "
                    "Unavailable or unfinished probes are marked in sampling. "
                    "Disk I/O covers all system disks. Byte values use raw bytes.</p>"
                )
                for name, values in self.payload["measurements"].items():
                    stream.write(f"<section><h2>{html.escape(name.title())}</h2>")
                    stream.write(_value_html(values) + "</section>")
                stream.write("<details><summary>Complete JSON snapshot</summary><pre>")
                stream.write(html.escape(json.dumps(self.payload, indent=2, ensure_ascii=False)))
                stream.write("</pre></details></html>")
            os.replace(temporary, destination)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        return str(destination.resolve())


class ReportExporter:
    """Start no thread until needed; allow only one bounded export at a time."""

    def __init__(self):
        self._worker = BackgroundSampler(capacity=1)
        self._seen = -1.0
        self.busy = False

    def submit(self, payload, directory):
        if self.busy:
            return False
        self.busy = True
        self._worker.submit("report", _WriteReport(payload, directory))
        return True

    def poll(self):
        result = self._worker.result("report")
        if result is not None and result.timestamp > self._seen:
            self._seen = result.timestamp
            self.busy = False
            self._worker.close()
            self._worker = BackgroundSampler(capacity=1)
            return result
        return None

    def close(self):
        self._worker.close()
