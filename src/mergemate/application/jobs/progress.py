"""Progress event models."""

from dataclasses import dataclass


@dataclass(slots=True)
class ProgressEvent:
    run_id: str
    status: str
    estimate_seconds: int | None = None