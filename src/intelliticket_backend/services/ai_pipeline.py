from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from intelliticket_backend.config import Settings, get_settings
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.mock_ops_data import MockOpsDataRepository
from intelliticket_backend.schemas.tickets import DataMode, TicketCategory
from intelliticket_backend.services.agents.context import ContextRetrievalAgent
from intelliticket_backend.services.agents.diagnosis import DiagnosisAgent
from intelliticket_backend.services.agents.intake import IntakeAgent
from intelliticket_backend.services.knowledge import KnowledgeService
from intelliticket_backend.services.llm import DeepSeekChatClient, LlmClient

ProgressCallback = Callable[[str, int], None]


@dataclass(frozen=True)
class AiPipelineInput:
    ticket_id: str
    text: str
    desk_id: str
    data_mode: str


@dataclass(frozen=True)
class AiPipelineOutput:
    result: dict[str, Any]
    evidence: list[dict[str, Any]]
    confidence: float
    prompt_tokens: int
    completion_tokens: int
    duration_ms: int


class AiPipeline:
    """P2 three-stage AI pipeline used by persistent worker tasks."""

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: LlmClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.repository = MockOpsDataRepository()
        self.knowledge_service = KnowledgeService(
            settings=self.settings,
            repository=self.repository,
        )
        self.llm_client = llm_client or self._build_llm_client()
        self.intake = IntakeAgent(
            repository=self.repository,
            llm_client=self.llm_client,
            strategy=self.settings.intake_agent_strategy,
        )
        self.context = ContextRetrievalAgent(
            repository=self.repository,
            knowledge_service=self.knowledge_service,
        )
        self.diagnosis = DiagnosisAgent(
            llm_client=self.llm_client,
            strategy=self.settings.diagnosis_agent_strategy,
        )

    def run(
        self,
        item: AiPipelineInput,
        progress: ProgressCallback | None = None,
    ) -> AiPipelineOutput:
        started = perf_counter()
        data_mode = DataMode(item.data_mode)
        stages: list[dict[str, Any]] = []

        self._progress(progress, "triage", 10)
        stage_started = perf_counter()
        intake = self.intake.run(
            ticket_id=item.ticket_id,
            text=item.text,
            data_mode=data_mode,
            observed_at=datetime.now(UTC).isoformat(),
        )
        if intake.classification is None:
            raise AppError("AI_TRIAGE_FAILED", "AI 分诊未生成分类结果", 500, {})
        classification = intake.classification
        if item.desk_id == "support":
            classification = classification.model_copy(
                update={"category": TicketCategory.SUPPORT_REQUEST}
            )
        stages.append(self._stage("triage", stage_started, intake.evidence_ids))

        self._progress(progress, "retrieve_diagnose", 40)
        stage_started = perf_counter()
        context = self.context.run(
            intake.service_record,
            data_mode,
            ticket_text=item.text,
        )
        diagnosis = self.diagnosis.run(
            classification,
            context.context,
            data_mode,
            ticket_text=item.text,
        )
        evidence_by_id = {
            evidence.evidence_id: evidence for evidence in [*intake.evidence, *context.evidence]
        }
        stages.append(
            self._stage(
                "retrieve_diagnose",
                stage_started,
                sorted(set(context.evidence_ids + diagnosis.evidence_ids)),
            )
        )

        self._progress(progress, "quality_gate", 80)
        stage_started = perf_counter()
        referenced = set(classification.evidence_ids)
        for cause in diagnosis.diagnosis.candidate_root_causes:
            referenced.update(cause.evidence_ids)
        for action in diagnosis.diagnosis.recommended_actions:
            referenced.update(action.evidence_ids)
        missing = sorted(referenced - set(evidence_by_id))
        if missing:
            raise AppError(
                "AI_EVIDENCE_INVALID",
                "AI 输出引用了不存在的证据",
                500,
                {"missing_evidence_ids": missing},
            )
        confidence = max(
            (cause.confidence for cause in diagnosis.diagnosis.candidate_root_causes),
            default=0.0,
        )
        recommended_team = (
            context.context.service.owner_team if context.context.service else None
        )
        recommended_actions = [
            action.model_dump(mode="json")
            for action in diagnosis.diagnosis.recommended_actions
        ]
        suggested_reply = self._suggested_reply(
            classification.summary,
            recommended_actions,
            diagnosis.diagnosis.abstentions,
        )
        quality_gate = {
            "status": "passed",
            "recommended_team": recommended_team,
            "recommended_actions": recommended_actions,
            "suggested_reply": suggested_reply,
            "confidence": confidence,
            "evidence_ids": sorted(referenced),
            "requires_human_review": True,
        }
        stages.append(self._stage("quality_gate", stage_started, sorted(referenced)))
        self._progress(progress, "quality_gate", 95)

        result = {
            "stages": stages,
            "triage": {
                "classification": classification.model_dump(mode="json"),
            },
            "retrieve_diagnose": {
                "context": context.context.model_dump(mode="json"),
                "diagnosis": diagnosis.diagnosis.model_dump(mode="json"),
            },
            "quality_gate": quality_gate,
            "metadata": {
                "pipeline_version": self.settings.ai_pipeline_version,
                "prompt_version": self.settings.ai_prompt_version,
                "provider": self.settings.llm_provider,
                "model": self.settings.llm_model,
                "external_call_count": getattr(self.llm_client, "total_calls", 0),
            },
        }
        return AiPipelineOutput(
            result=result,
            evidence=[item.model_dump(mode="json") for item in evidence_by_id.values()],
            confidence=confidence,
            prompt_tokens=getattr(self.llm_client, "total_prompt_tokens", 0),
            completion_tokens=getattr(self.llm_client, "total_completion_tokens", 0),
            duration_ms=int((perf_counter() - started) * 1000),
        )

    def _build_llm_client(self) -> LlmClient | None:
        api_key = self.settings.resolved_deepseek_api_key
        if api_key is None or not api_key.get_secret_value().strip():
            return None
        if self.settings.llm_provider != "deepseek":
            raise AppError(
                "UNSUPPORTED_LLM_PROVIDER",
                "不支持的 LLM provider",
                500,
                {"provider": self.settings.llm_provider},
            )
        return DeepSeekChatClient(
            api_key=api_key,
            base_url=self.settings.deepseek_base_url,
            model=self.settings.llm_model,
            timeout_seconds=self.settings.llm_timeout_seconds,
            max_retries=self.settings.llm_max_retries,
            retry_backoff_seconds=self.settings.llm_retry_backoff_seconds,
            temperature=self.settings.llm_temperature,
        )

    @staticmethod
    def _stage(name: str, started: float, evidence_ids: list[str]) -> dict[str, Any]:
        return {
            "name": name,
            "status": "completed",
            "duration_ms": int((perf_counter() - started) * 1000),
            "evidence_ids": evidence_ids,
        }

    @staticmethod
    def _progress(callback: ProgressCallback | None, stage: str, progress: int) -> None:
        if callback is not None:
            callback(stage, progress)

    @staticmethod
    def _suggested_reply(
        summary: str,
        actions: list[dict[str, Any]],
        abstentions: list[str],
    ) -> str:
        if actions:
            action_text = "；".join(str(item["action"]) for item in actions[:3])
            return f"已完成初步分析：{summary}。建议下一步：{action_text}。"
        reason = abstentions[0] if abstentions else "当前证据不足"
        return f"已收到工单。{reason}，运维人员将继续人工排查。"
