"""Run a real DeepSeek smoke test without logging secrets or model payloads."""
from __future__ import annotations

import json
import os
from uuid import uuid4


def main() -> int:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("SKIPPED: DEEPSEEK_API_KEY is not configured.")
        return 2

    os.environ.setdefault("INTAKE_AGENT_STRATEGY", "llm")
    os.environ.setdefault("DIAGNOSIS_AGENT_STRATEGY", "llm")
    os.environ.setdefault("LLM_PROVIDER", "deepseek")
    os.environ.setdefault("LLM_MODEL", "deepseek-chat")
    os.environ.setdefault("DATA_MODE", "mock")

    from intelliticket_backend.errors import AppError
    from intelliticket_backend.services.ai_pipeline import AiPipeline, AiPipelineInput

    ticket_id = f"SMOKE-{uuid4().hex[:8].upper()}"
    try:
        output = AiPipeline().run(
            AiPipelineInput(
                ticket_id=ticket_id,
                text=(
                    "The payment API has timed out for ten minutes. "
                    "Success rate dropped from 99.9% to 72%."
                ),
                desk_id="ops",
                data_mode="mock",
            )
        )
    except AppError as exc:
        print(json.dumps({"status": "failed", "error_code": exc.code}))
        return 1
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 1

    metadata = output.result.get("metadata", {})
    quality_gate = output.result.get("quality_gate", {})
    external_calls = int(metadata.get("external_call_count", 0))
    passed = (
        quality_gate.get("status") == "passed"
        and quality_gate.get("requires_human_review") is True
        and external_calls >= 2
        and bool(output.evidence)
    )
    print(
        json.dumps(
            {
                "status": "passed" if passed else "failed",
                "model": metadata.get("model"),
                "external_call_count": external_calls,
                "duration_ms": output.duration_ms,
                "confidence": output.confidence,
                "evidence_count": len(output.evidence),
                "requires_human_review": quality_gate.get("requires_human_review"),
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
