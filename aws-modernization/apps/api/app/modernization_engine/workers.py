"""Future worker boundary. No production worker exists in Phase 2.4."""
from abc import ABC, abstractmethod
from threading import Event
from .models import AgentOutputMetadata, ExecutionTask


class ExecutionWorker(ABC):
    worker_id: str

    @abstractmethod
    def run(self, task: ExecutionTask) -> AgentOutputMetadata: ...


class CancellationSignal:
    def __init__(self): self._event = Event()
    def cancel(self) -> None: self._event.set()
    def requested(self) -> bool: return self._event.is_set()


class SafeMockWorker(ExecutionWorker):
    """Deterministic test-only worker; never changes source or claims modernization."""
    worker_id = "safe-mock-worker"

    def run(self, task: ExecutionTask, cancellation: CancellationSignal | None = None) -> AgentOutputMetadata:
        if cancellation and cancellation.requested():
            return AgentOutputMetadata(taskId=task.taskId, agentId=task.agentId, outputType="TEST_ONLY_SIMULATION", findings=["TEST_ONLY simulation cancelled before work."], validationStatus="not-produced", executionStatus="not-started")
        return AgentOutputMetadata(taskId=task.taskId, agentId=task.agentId, outputType="TEST_ONLY_SIMULATION",
            findings=["TEST_ONLY simulation: no source modification, acceptance validation, or behavioral parity was performed."], validationStatus="not-produced", executionStatus="not-started")
