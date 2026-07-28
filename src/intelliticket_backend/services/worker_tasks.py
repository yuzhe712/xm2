from __future__ import annotations

from celery import Task

from intelliticket_backend.celery_app import celery_app
from intelliticket_backend.config import get_settings
from intelliticket_backend.db import session_scope
from intelliticket_backend.errors import AppError
from intelliticket_backend.repositories.ai_runs import AiRunRepository
from intelliticket_backend.services.ai_pipeline import AiPipeline, AiPipelineInput

RETRYABLE_CODES = {
    "INTAKE_LLM_FAILED",
    "DIAGNOSIS_LLM_FAILED",
    "LLM_PROVIDER_ERROR",
    "LLM_RETRY_EXHAUSTED",
    "LLM_TIMEOUT",
}


@celery_app.task(bind=True, name="intelliticket.process_ai_run")
def process_ai_run(task: Task, run_id: str) -> dict:
    settings = get_settings()
    task_id = getattr(task.request, "id", None)
    with session_scope() as session:
        repository = AiRunRepository(session)
        run = repository.mark_running(run_id, task_id)
        if run is None:
            existing = repository.get(run_id)
            if existing is None:
                raise AppError("AI_RUN_NOT_FOUND", "AI 任务不存在", 404, {"run_id": run_id})
            return AiRunRepository.to_response(existing).model_dump(mode="json")
        linked = repository.get_for_ticket(run_id)
        assert linked is not None
        _, ticket = linked
        pipeline_input = AiPipelineInput(
            ticket_id=ticket.ticket_id,
            text=ticket.input_text,
            desk_id=ticket.desk_id,
            data_mode=ticket.data_mode,
        )

    def progress(stage: str, percent: int) -> None:
        with session_scope() as progress_session:
            AiRunRepository(progress_session).mark_stage(run_id, stage, percent)

    try:
        output = AiPipeline(settings=settings).run(pipeline_input, progress=progress)
    except AppError as exc:
        retries = int(getattr(task.request, "retries", 0))
        retryable = exc.code in RETRYABLE_CODES and retries < settings.ai_task_max_retries
        with session_scope() as session:
            AiRunRepository(session).fail(
                run_id,
                exc.code,
                exc.message,
                terminal=not retryable,
            )
        if retryable:
            countdown = settings.ai_task_retry_backoff_seconds * (2**retries)
            raise task.retry(
                exc=exc,
                countdown=countdown,
                max_retries=settings.ai_task_max_retries,
            ) from exc
        with session_scope() as session:
            failed = AiRunRepository(session).get(run_id)
            assert failed is not None
            return AiRunRepository.to_response(failed).model_dump(mode="json")
    except Exception as exc:
        retries = int(getattr(task.request, "retries", 0))
        retryable = retries < settings.ai_task_max_retries
        with session_scope() as session:
            AiRunRepository(session).fail(
                run_id,
                "AI_PIPELINE_ERROR",
                str(exc),
                terminal=not retryable,
            )
        if retryable:
            countdown = settings.ai_task_retry_backoff_seconds * (2**retries)
            raise task.retry(
                exc=exc,
                countdown=countdown,
                max_retries=settings.ai_task_max_retries,
            ) from exc
        with session_scope() as session:
            failed = AiRunRepository(session).get(run_id)
            assert failed is not None
            return AiRunRepository.to_response(failed).model_dump(mode="json")

    with session_scope() as session:
        completed = AiRunRepository(session).complete(
            run_id,
            result=output.result,
            evidence=output.evidence,
            confidence=output.confidence,
            prompt_tokens=output.prompt_tokens,
            completion_tokens=output.completion_tokens,
            duration_ms=output.duration_ms,
        )
        return AiRunRepository.to_response(completed).model_dump(mode="json")


def dispatch_ai_run(run_id: str) -> str | None:
    """Dispatch after the queue row is committed; broker failure is persisted."""
    try:
        result = process_ai_run.apply_async(args=[run_id])
    except Exception as exc:
        with session_scope() as session:
            AiRunRepository(session).fail(
                run_id,
                "AI_QUEUE_UNAVAILABLE",
                f"AI task could not be enqueued: {type(exc).__name__}",
            )
        return None
    with session_scope() as session:
        AiRunRepository(session).mark_dispatched(run_id, result.id)
    return result.id
