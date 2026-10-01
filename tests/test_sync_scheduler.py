from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import Settings
from app.workers import sync_worker as worker


@contextmanager
def fake_session():
    yield object()


def test_interval_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, POLLING_INTERVAL_SECONDS=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, POLLING_INTERVAL_SECONDS=-1)


def test_due_interval_creates_one_job(monkeypatch):
    created = []
    monkeypatch.setattr(worker.settings, "POLLING_ENABLED", True)
    monkeypatch.setattr(worker.settings, "POLLING_INTERVAL_SECONDS", 30.0)
    monkeypatch.setattr(worker, "SessionLocal", fake_session)
    monkeypatch.setattr(worker.SyncService, "create", lambda db, request: (
        created.append(request.model_dump()) or type("Job", (), {"job_id": "job-1"})()
    ))

    assert worker.schedule_if_due(100.0, 100.0) == 130.0
    assert created == [{"page_size": 100, "max_products": 1000}]


def test_not_due_or_disabled_never_creates_job(monkeypatch):
    monkeypatch.setattr(worker, "SessionLocal", lambda: pytest.fail("Unexpected DB session"))
    monkeypatch.setattr(worker.settings, "POLLING_ENABLED", True)
    assert worker.schedule_if_due(9.0, 10.0) == 10.0
    monkeypatch.setattr(worker.settings, "POLLING_ENABLED", False)
    assert worker.schedule_if_due(20.0, 10.0) == 10.0


def test_active_sync_skips_interval(monkeypatch):
    calls = []
    monkeypatch.setattr(worker.settings, "POLLING_ENABLED", True)
    monkeypatch.setattr(worker.settings, "POLLING_INTERVAL_SECONDS", 30.0)
    monkeypatch.setattr(worker, "SessionLocal", fake_session)

    def active(db, request):
        calls.append(1)
        raise HTTPException(409, "Active sync job")

    monkeypatch.setattr(worker.SyncService, "create", active)
    assert worker.schedule_if_due(100.0, 100.0) == 130.0
    assert worker.schedule_if_due(101.0, 130.0) == 130.0
    assert calls == [1]


def test_every_loop_runs_pending_jobs_and_skips_missed_intervals(monkeypatch):
    clock_values = iter((0.0, 0.0, 40.0, 41.0, 41.0))
    scheduled = []
    processed = []
    sleeps = []
    monkeypatch.setattr(worker.settings, "POLLING_ENABLED", True)
    monkeypatch.setattr(worker.settings, "POLLING_INTERVAL_SECONDS", 30.0)
    monkeypatch.setattr(worker, "SessionLocal", fake_session)
    monkeypatch.setattr(worker.SyncService, "create", lambda db, request: (
        scheduled.append(1) or type("Job", (), {"job_id": "job-1"})()
    ))
    monkeypatch.setattr(worker, "run_once", lambda: processed.append(1))

    def sleep_and_stop(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        worker.run_forever(clock=lambda: next(clock_values), sleeper=sleep_and_stop)
    assert scheduled == [1]  # the work took 40s; the 30s slot was skipped
    assert processed == [1, 1]  # run_once also ran at t=41, between intervals
    assert sleeps == [1.0, 1.0]


class FakeConnection:
    def __init__(self, acquired=True):
        self.acquired = acquired
        self.statements = []
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execution_options(self, **options):
        assert options["isolation_level"] == "AUTOCOMMIT"
        return self

    def exec_driver_sql(self, sql, args):
        self.statements.append((sql, args))
        value = self.acquired if "pg_try_advisory_lock" in sql else True
        return type("Result", (), {"scalar_one": lambda self: value})()

    def rollback(self):
        self.rollbacks += 1

    def invalidate(self):
        pytest.fail("Unexpected invalidate")


def test_singleton_lock_uses_dedicated_autocommit_connection(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(worker.engine, "connect", lambda: connection)
    with worker.singleton_lock():
        assert connection.rollbacks == 1
    assert connection.rollbacks == 2
    assert len(connection.statements) == 2
    assert connection.statements[0][1] == (worker.LOCK_NAMESPACE, worker.LOCK_KEY)
    assert connection.statements[0][1][0] != 1128549715


def test_second_worker_cannot_acquire_lock(monkeypatch):
    connection = FakeConnection(acquired=False)
    monkeypatch.setattr(worker.engine, "connect", lambda: connection)

    with pytest.raises(RuntimeError, match="Another sync worker"):
        with worker.singleton_lock():
            pass

    assert len(connection.statements) == 1