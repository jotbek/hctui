"""One lazy daemon worker and a bounded queue for slow, read-only probes."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from typing import NamedTuple


class Result(NamedTuple):
    value: object
    timestamp: float
    error: str = ""


class CommandRunner:
    """Run bounded commands in the worker and terminate an active command on exit."""

    def __init__(self):
        self._lock = threading.Lock()
        self._process = None
        self._closed = False

    def run(self, arguments: list[str], timeout: float = 1.0, accept_status=False) -> str:
        with self._lock:
            if self._closed:
                raise OSError("Monitor is shutting down")
            process = subprocess.Popen(
                arguments, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
            )
            self._process = process
        try:
            output, _ = process.communicate(timeout=timeout)
            if process.returncode and not (
                accept_status and "LoadState=" in output and "Id=" in output
            ):
                raise OSError(f"{arguments[0]} exited with code {process.returncode}")
            return output[:65536]
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.communicate()
            raise OSError(f"{arguments[0]} timed out") from error
        finally:
            with self._lock:
                self._process = None

    def close(self):
        with self._lock:
            self._closed = True
            if self._process is not None and self._process.poll() is None:
                try:
                    self._process.terminate()
                except ProcessLookupError:
                    pass


class BackgroundSampler:
    """Never enqueue more than one job per source or retain more than one result."""

    def __init__(self, capacity: int = 8):
        self._queue = queue.Queue(maxsize=capacity)
        self._pending = set()
        self._results = {}
        self._lock = threading.Lock()
        self._thread = None
        self.closed = threading.Event()

    def submit(self, name, provider):
        with self._lock:
            if self.closed.is_set() or name in self._pending:
                return
            try:
                self._queue.put_nowait((name, provider))
            except queue.Full:
                return
            self._pending.add(name)
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="hctui-probes", daemon=True)
                self._thread.start()

    def result(self, name):
        with self._lock:
            return self._results.get(name)

    @property
    def pending_count(self):
        with self._lock:
            return len(self._pending)

    @property
    def pending_sources(self):
        with self._lock:
            return frozenset(self._pending)

    def _run(self):
        while True:
            job = self._queue.get()
            if job is None:
                self._queue.task_done()
                break
            name, provider = job
            try:
                value = provider.sample(time.monotonic())
                result = Result(value, time.monotonic())
            except Exception as error:
                # A failed optional probe must not kill the worker or the terminal UI.
                result = Result(None, time.monotonic(), f"{type(error).__name__}: {error}")
            with self._lock:
                self._results[name] = result
                self._pending.discard(name)
            self._queue.task_done()

    def close(self):
        with self._lock:
            if self.closed.is_set():
                return
            self.closed.set()
            self._pending.clear()
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        if self._thread is not None:
            self._queue.put_nowait(None)
            self._thread.join(timeout=0.3)
