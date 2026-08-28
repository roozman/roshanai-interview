from collections.abc import Iterable
from time import perf_counter

from django.conf import settings
from django.db import transaction

from qa.constants import (
    QUESTION_ERROR_MESSAGE_MAX_CHARACTERS,
    RETRIEVED_CHUNK_EXCERPT_MAX_CHARACTERS,
)
from qa.models import QuestionAnswer, RetrievedChunk
from qa.services.rag import answer_question


def _elapsed_milliseconds(started_at: float) -> int:
    elapsed_seconds = perf_counter() - started_at

    return max(
        0,
        round(elapsed_seconds * 1000),
    )


def _error_message(exc: Exception) -> str:
    message = str(exc).strip()

    if not message:
        message = "Question processing failed."

    return message[
        :QUESTION_ERROR_MESSAGE_MAX_CHARACTERS
    ]


def process_question(
    question: str,
    *,
    document_ids: Iterable[int] | None = None,
) -> QuestionAnswer:
    if not isinstance(question, str) or not question.strip():
        raise ValueError(
            "The question must be a non-empty string."
        )

    normalized_question = question.strip()

    question_answer = QuestionAnswer.objects.create(
        question=normalized_question,
        status=QuestionAnswer.Status.PROCESSING,
        model_name=settings.OPENROUTER_CHAT_MODEL,
    )

    started_at = perf_counter()

    try:
        result = answer_question(
            normalized_question,
            document_ids=document_ids,
        )
    except Exception as exc:
        question_answer.status = (
            QuestionAnswer.Status.FAILED
        )
        question_answer.error_message = _error_message(
            exc
        )
        question_answer.latency_ms = (
            _elapsed_milliseconds(started_at)
        )
        question_answer.save(
            update_fields=[
                "status",
                "error_message",
                "latency_ms",
            ]
        )
        raise

    latency_ms = _elapsed_milliseconds(started_at)

    retrieved_records = [
        RetrievedChunk(
            question_answer=question_answer,
            chunk_id=source.chunk_id,
            rank=rank,
            similarity_score=source.similarity_score,
            excerpt=source.content.strip()[
                :RETRIEVED_CHUNK_EXCERPT_MAX_CHARACTERS
            ],
        )
        for rank, source in enumerate(
            result.sources,
            start=1,
        )
    ]

    with transaction.atomic():
        question_answer.answer = result.answer
        question_answer.status = (
            QuestionAnswer.Status.COMPLETED
        )
        question_answer.model_name = result.model_name
        question_answer.latency_ms = latency_ms
        question_answer.error_message = ""
        question_answer.save(
            update_fields=[
                "answer",
                "status",
                "model_name",
                "latency_ms",
                "error_message",
            ]
        )

        RetrievedChunk.objects.bulk_create(
            retrieved_records
        )

    return question_answer