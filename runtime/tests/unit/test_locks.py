"""Testes do WriteLock: reentrancy e reclaim de PID morto."""

from __future__ import annotations

import json
import os

from orchestrator_runtime.execution.locks import WriteLock


def test_write_lock_reentrant(tmp_path):
    lock = WriteLock(tmp_path / "workspace.write.lock", timeout_s=5)
    with lock:
        assert lock._held
        assert lock._depth == 1
        with lock:
            assert lock._depth == 2
        assert lock._depth == 1
        assert lock.lock_path.exists()
    assert not lock._held
    assert not lock.lock_path.exists()


def test_write_lock_reclaims_dead_pid(tmp_path):
    path = tmp_path / "workspace.write.lock"
    path.write_text(json.dumps({"pid": 999_999_999, "ts": 1.0}), encoding="utf-8")
    lock = WriteLock(path, timeout_s=5)
    lock.acquire()
    assert lock._held
    assert json.loads(path.read_text(encoding="utf-8"))["pid"] == os.getpid()
    lock.release()
    assert not path.exists()


def test_write_lock_reclaims_same_pid_stale_file(tmp_path):
    path = tmp_path / "workspace.write.lock"
    path.write_text(
        json.dumps({"pid": os.getpid(), "ts": 1.0}), encoding="utf-8"
    )
    lock = WriteLock(path, timeout_s=5)
    # _held False → arquivo do mesmo PID é considerado órfão desta instância
    lock.acquire()
    assert lock._held
    lock.release()
