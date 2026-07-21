"""Locks e workspace helpers."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


class WriteLock:
    def __init__(self, lock_path: Path, timeout_s: int = 30) -> None:
        self.lock_path = lock_path
        self.timeout_s = timeout_s
        self._held = False

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        start = time.time()
        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump({"pid": os.getpid(), "ts": time.time()}, fh)
                self._held = True
                return
            except FileExistsError:
                if time.time() - start > self.timeout_s:
                    raise TimeoutError(f"Não foi possível obter lock: {self.lock_path}")
                time.sleep(0.2)

    def release(self) -> None:
        if self._held and self.lock_path.exists():
            self.lock_path.unlink(missing_ok=True)
            self._held = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
