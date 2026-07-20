from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ReActStep(BaseModel):
    """可审计 ReAct 步骤摘要，不保存私有 chain-of-thought。"""

    step_index: int = Field(ge=1)
    decision_summary: str
    action: str
    action_input_summary: str
    observation_summary: str
    evidence_ids: list[str] = Field(default_factory=list)


class AgentTaskError(BaseModel):
    """内部任务信封错误。"""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class InternalTaskRequest(BaseModel):
    """内部 Agent 任务请求信封，不代表正式 A2A 协议兼容。"""

    task_id: str
    ticket_id: str
    run_id: str
    from_agent: str
    to_agent: str
    message_type: str
    payload: dict[str, Any]
    evidence_ids: list[str] = Field(default_factory=list)
    idempotency_key: str
    created_at: str = Field(default_factory=_utc_now)


class InternalTaskResult(BaseModel):
    """内部 Agent 任务执行结果信封。"""

    task_id: str
    ticket_id: str
    run_id: str
    agent_name: str
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    react_steps: list[ReActStep] = Field(default_factory=list)
    error: AgentTaskError | None = None
    completed_at: str = Field(default_factory=_utc_now)
