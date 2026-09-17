from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.business.signals.contracts import SignalEvaluationReport
from app.workers import tasks


class Operations:
    def __init__(self) -> None:
        self.operation_id = uuid.uuid4()
        self.registered: list[tuple[str, str | None]] = []
        self.running: list[tuple[uuid.UUID, str | None]] = []
        self.completed: list[tuple[uuid.UUID, dict[str, object]]] = []

    def register(self, *, operation_type: str, request_id: str | None):
        self.registered.append((operation_type, request_id))
        return self.operation_id

    def mark_running(self, operation_id, *, celery_task_id=None):
        self.running.append((operation_id, celery_task_id))

    def mark_completed(self, operation_id, *, result=None):
        self.completed.append((operation_id, result))

    def mark_failed(self, operation_id, *, reason):
        raise AssertionError((operation_id, reason))


class Evaluation:
    def evaluate_all(self):
        return SignalEvaluationReport(
            generated_at=datetime(2025, 4, 1, tzinfo=UTC), records=()
        )


def test_signal_task_registers_persistent_operation_and_returns_report(
    monkeypatch,
) -> None:
    operations = Operations()
    monkeypatch.setattr(tasks, "_operation_service", lambda: operations)
    monkeypatch.setattr(tasks, "_signal_evaluation_service", lambda: Evaluation())

    result = tasks.evaluate_signals.run(None)

    assert operations.registered == [("signals.evaluate", None)]
    assert operations.running[0][0] == operations.operation_id
    assert operations.completed[0][0] == operations.operation_id
    assert result["operation_id"] == str(operations.operation_id)
    assert result["report"]["records"] == []
