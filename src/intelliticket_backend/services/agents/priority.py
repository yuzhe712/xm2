from __future__ import annotations

from pydantic import BaseModel, Field

from intelliticket_backend.errors import AppError
from intelliticket_backend.services.llm import LlmClient, LlmClientError


class PriorityAssessment(BaseModel):
    """LLM 优先级评估结构化输出。"""

    priority: str = Field(pattern=r"^P[1-4]$")
    reason: str = Field(min_length=1, max_length=300)


class PriorityAssessmentAgent:
    """提交时自动判定工单优先级。LLM 不可用时 fallback 到关键词规则。"""

    name = "priority_assessment_agent"

    def __init__(self, llm_client: LlmClient | None = None) -> None:
        self.llm_client = llm_client

    def assess(self, text: str) -> PriorityAssessment:
        if self.llm_client is not None:
            try:
                return self._llm_assess(text)
            except (LlmClientError, AppError):
                pass
        return self._deterministic_assess(text)

    def _llm_assess(self, text: str) -> PriorityAssessment:
        if self.llm_client is None:  # pragma: no cover
            return self._deterministic_assess(text)
        return self.llm_client.structured_json_call(
            system_prompt=(
                "你是 IntelliTicket 的优先级评估 Agent。"
                "根据用户提交的工单内容，判定优先级 P1/P2/P3/P4。"
                "只能输出 JSON：{\"priority\": \"P1\", \"reason\": \"...\"}。"
                "判定标准：\n"
                "- P1: 核心服务中断、影响大量用户、安全事件、数据丢失\n"
                "- P2: 关键功能异常、影响部分用户、有业务损失\n"
                "- P3: 一般问题、影响单个用户、有临时解决方案\n"
                "- P4: 咨询、建议、非紧急需求\n"
                "reason 用中文，30 字以内。"
            ),
            user_payload={"text": text},
            response_schema=PriorityAssessment,
        )

    def _deterministic_assess(self, text: str) -> PriorityAssessment:
        lower = text.lower()
        p1_keywords = [
            "系统崩溃", "全部宕机", "数据丢失", "安全漏洞", "被攻击",
            "所有用户", "完全无法", "核心业务中断", "生产事故",
        ]
        p2_keywords = [
            "超时", "延迟", "无法访问", "报错", "异常", "告警",
            "大量", "多个", "订单下降", "连接失败",
        ]
        p4_keywords = ["咨询", "请问", "如何", "建议", "申请权限", "开通"]

        if any(kw in lower or kw in text for kw in p1_keywords):
            return PriorityAssessment(
                priority="P1", reason="工单内容包含核心服务中断或安全事件关键词。"
            )
        if any(kw in lower or kw in text for kw in p2_keywords):
            return PriorityAssessment(
                priority="P2", reason="工单内容包含异常或性能问题关键词。"
            )
        if any(kw in lower or kw in text for kw in p4_keywords):
            return PriorityAssessment(
                priority="P4", reason="工单内容属于咨询或非紧急请求。"
            )
        return PriorityAssessment(
            priority="P3", reason="未识别到高优先级关键词，按普通优先级处理。"
        )
