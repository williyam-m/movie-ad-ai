from __future__ import annotations

import threading
import uuid

from backend.schemas import AnalysisResult, JobRecord


class JobNotFoundError(KeyError):
    pass


class JobStore:
    def __init__(self) -> None:
        self._records: dict[str, JobRecord] = {}
        self._lock = threading.RLock()

    def create(self) -> JobRecord:
        job_id = uuid.uuid4().hex
        record = JobRecord(
            id=job_id,
            status="queued",
            stage="Queued for analysis",
            progress=0,
        )
        with self._lock:
            self._records[job_id] = record
        return record.model_copy(deep=True)

    def get(self, job_id: str) -> JobRecord:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                raise JobNotFoundError(job_id)
            return record.model_copy(deep=True)

    def progress(self, job_id: str, stage: str, progress: float) -> None:
        with self._lock:
            record = self._records[job_id]
            record.status = "running"
            record.stage = stage
            record.progress = max(record.progress, min(0.99, progress))

    def complete(self, job_id: str, result: AnalysisResult) -> None:
        with self._lock:
            record = self._records[job_id]
            record.status = "completed"
            record.stage = "Analysis complete"
            record.progress = 1
            record.result = result

    def fail(self, job_id: str, error: Exception) -> None:
        with self._lock:
            record = self._records[job_id]
            record.status = "failed"
            record.stage = "Analysis failed"
            record.error = str(error)[:500]
