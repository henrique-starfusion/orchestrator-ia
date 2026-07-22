"""Locks e workspace helpers."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            synchronize = 0x00100000
            handle = kernel32.OpenProcess(synchronize, False, int(pid))
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class WriteLock:
    def __init__(self, lock_path: Path, timeout_s: int = 30) -> None:
        self.lock_path = lock_path
        self.timeout_s = timeout_s
        self._held = False
        self._depth = 0

    def _reclaim_stale(self) -> bool:
        """Remove lock órfão (PID morto) ou do mesmo processo sem hold ativo."""
        if not self.lock_path.exists():
            return False
        try:
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
            ts = float(data.get("ts") or 0)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.lock_path.unlink(missing_ok=True)
            return True

        if pid == os.getpid() and not self._held:
            self.lock_path.unlink(missing_ok=True)
            return True
        if not _pid_alive(pid):
            self.lock_path.unlink(missing_ok=True)
            return True
        # lock muito antigo além de várias janelas de timeout
        if ts and (time.time() - ts) > max(self.timeout_s * 10, 300):
            self.lock_path.unlink(missing_ok=True)
            return True
        return False

    def acquire(self) -> None:
        if self._held:
            self._depth += 1
            return

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        start = time.time()
        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump({"pid": os.getpid(), "ts": time.time()}, fh)
                self._held = True
                self._depth = 1
                return
            except FileExistsError:
                self._reclaim_stale()
                if time.time() - start > self.timeout_s:
                    raise TimeoutError(f"Não foi possível obter lock: {self.lock_path}")
                time.sleep(0.2)

    def release(self) -> None:
        if not self._held:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        if self.lock_path.exists():
            self.lock_path.unlink(missing_ok=True)
        self._held = False
        self._depth = 0

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
