"""Loading the statistics without making a search wait.

The history counts, delay statistics and train messages come from Data Explorer.
The first use after a cold start has to wait for them. After that, a stale copy is
reloaded in a background thread while requests keep using the old one, so no search
waits for a reload. `warm()` starts the first load early (the web app calls
/warm when it opens), so by the first search the data is usually there.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

log = logging.getLogger(__name__)


class Refresh:
    def __init__(
        self,
        load: Callable[[], None],
        every_s: float,
        what: str,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.load = load
        self.every_s = every_s
        self.what = what
        self.clock = clock
        self.loaded_at: float | None = None
        self._busy = False
        self._lock = threading.Lock()

    def _run(self) -> None:
        try:
            self.load()
        except Exception:
            log.exception("could not load %s; keeping the previous state", self.what)
        self.loaded_at = self.clock()

    def ensure(self) -> None:
        """Load now if nothing is there yet; otherwise reload stale data in the background."""
        if self.loaded_at is None:
            with self._lock:  # a load already running (e.g. from warm()) is waited for
                if self.loaded_at is None:
                    self._run()
            return
        if self.clock() - self.loaded_at < self.every_s or self._busy:
            return
        with self._lock:
            if self._busy or self.clock() - self.loaded_at < self.every_s:
                return
            self._busy = True
        threading.Thread(target=self._background, daemon=True).start()

    def _background(self) -> None:
        try:
            with self._lock:
                self._run()
        finally:
            self._busy = False

    def warm(self) -> None:
        """Start the first load without waiting for it."""
        if self.loaded_at is None and not self._lock.locked():
            threading.Thread(target=self.ensure, daemon=True).start()
