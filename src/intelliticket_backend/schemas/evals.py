from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from intelliticket_backend.schemas.tickets import DataMode
from intelliticket_backend.services.agents.envelope import AgentTaskError

EvalCaseStatus = Literal["passed", "failed"]


class EvalCaseResult(BaseModel):
    """单个 eval case 的可审计结果。"""

    case_id: str
    name: str
    status: EvalCaseStatus
    data_mode: DataMode
    duration_ms: int = Field(ge=0)
    observations: list[str] = Field(default_factory=list)
    error: AgentTaskError | None = None

    model_config = ConfigDict(extra="forbid")


class EvalReport(BaseModel):
    """独立 eval CLI 输出报告。"""

    generated_at: str
    data_mode: DataMode
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    cases: list[EvalCaseResult] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
