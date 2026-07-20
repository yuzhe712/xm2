from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from intelliticket_backend.services.agents.envelope import (
    AgentTaskError,
    InternalTaskRequest,
    InternalTaskResult,
    ReActStep,
)


class AgentCapability(StrEnum):
    """IntelliTicket Agent 能力声明。"""

    TICKET_INTAKE = "ticket_intake"
    CONTEXT_RETRIEVAL = "context_retrieval"
    DIAGNOSIS = "diagnosis"
    ROUTING = "routing"
    REPORT = "report"
    REVIEW = "review"
    SUPPORT_KB_RETRIEVAL = "support_kb_retrieval"
    SUPPORT_REPLY = "support_reply"


@dataclass(frozen=True)
class AgentMetadata:
    """可序列化 Agent 元信息。"""

    name: str
    description: str
    capabilities: list[AgentCapability]


class BaseAgent(ABC):
    """轻量 Agent 基础契约。"""

    name: str
    description: str
    capabilities: list[AgentCapability]

    def get_metadata(self) -> AgentMetadata:
        return AgentMetadata(
            name=self.name,
            description=self.description,
            capabilities=list(self.capabilities),
        )

    def make_task_result(
        self,
        request: InternalTaskRequest,
        status: str,
        payload: dict[str, Any] | None = None,
        evidence_ids: list[str] | None = None,
        observations: list[str] | None = None,
        react_steps: list[ReActStep] | None = None,
        error: AgentTaskError | None = None,
    ) -> InternalTaskResult:
        return InternalTaskResult(
            task_id=request.task_id,
            ticket_id=request.ticket_id,
            run_id=request.run_id,
            agent_name=self.name,
            status=status,
            payload=payload or {},
            evidence_ids=evidence_ids or [],
            observations=observations or [],
            react_steps=react_steps or [],
            error=error,
        )

    def wrong_target_result(self, request: InternalTaskRequest) -> InternalTaskResult:
        return self.make_task_result(
            request=request,
            status="failed",
            error=AgentTaskError(
                code="INVALID_AGENT_TARGET",
                message="内部任务信封目标 Agent 不匹配",
                details={"to_agent": request.to_agent, "expected": self.name},
            ),
        )

    def invalid_payload_result(
        self,
        request: InternalTaskRequest,
        exc: Exception,
    ) -> InternalTaskResult:
        return self.make_task_result(
            request=request,
            status="failed",
            error=AgentTaskError(
                code="INVALID_TASK_PAYLOAD",
                message="内部任务 payload 无法通过 schema 校验",
                details={"error": str(exc)},
            ),
        )

    @abstractmethod
    def handle_task(self, request: InternalTaskRequest) -> InternalTaskResult:
        """处理内部任务信封。"""
