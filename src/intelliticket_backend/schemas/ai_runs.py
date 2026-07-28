from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AiRunStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
AiDecision = Literal["accepted", "modified", "rejected"]


class AiRunResponse(BaseModel):
    id: str
    ticket_id: str
    status: AiRunStatus
    celery_task_id: str | None = None
    stage: str
    progress: int
    pipeline_version: str
    provider: str
    model: str
    prompt_version: str
    result: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    error_code: str | None = None
    error_message: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    retry_count: int
    duration_ms: int | None = None
    decision: AiDecision | None = None
    decision_note: str | None = None
    modified_result: dict[str, Any] | None = None
    decided_by: str | None = None
    decided_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    heartbeat_at: str | None = None
    created_at: str
    updated_at: str

    model_config = ConfigDict(extra="forbid")


class AiRunDecisionRequest(BaseModel):
    decision: AiDecision
    note: str | None = Field(default=None, max_length=2000)
    modified_result: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_modified_result(self) -> AiRunDecisionRequest:
        if self.decision == "modified" and self.modified_result is None:
            raise ValueError("修改 AI 建议时必须提交 modified_result")
        return self


class AiRunStatusEvent(BaseModel):
    type: Literal["ai_run_status"] = "ai_run_status"
    run: AiRunResponse


class StaleRecoveryResponse(BaseModel):
    recovered_run_ids: list[str]
