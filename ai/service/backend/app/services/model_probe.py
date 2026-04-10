"""Background prober for periodic OCR model availability refresh."""

from __future__ import annotations

import threading
from typing import Protocol


class ProbedEngine(Protocol):
    def probe(self) -> bool:
        ...


class ModelAvailabilityProber:
    def __init__(self, engines: list[ProbedEngine], interval_s: float = 15.0) -> None:
        self.engines = engines
        self.interval_s = max(1.0, float(interval_s))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="model-availability-prober", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def _run(self) -> None:
        # Warm up cache once at start.
        self._probe_once()

        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self.interval_s):
                break
            self._probe_once()

    def _probe_once(self) -> None:
        for engine in self.engines:
            try:
                engine.probe()
            except Exception:
                # Prober should never crash the process.
                pass
