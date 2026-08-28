from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite

from django.conf import settings
from pgvector import HalfVector
from pgvector.django import CosineDistance

from documents.models import Document, DocumentChunk
from documents.services.embeddings import (
    EmbeddingServiceError,
    generate_query_embedding,
)


@dataclass(frozen=True, slots=True)
class RetrievedDocumentChunk:
    chunk_id: int
    document_id: int
    document_title: str
    content: str
    chunk_index: int
    similarity_score: float


class RetrievalError(RuntimeError):
    pass


class RetrievalConfigurationError(RetrievalError):
    pass


class RetrievalInputError(RetrievalError):
    pass


def _get_retrieval_configuration() -> tuple[int, float]:
    top_k = settings.RETRIEVAL_TOP_K
    score_threshold = settings.RETRIEVAL_SCORE_THRESHOLD

    if (
        isinstance(top_k, bool)
        or not isinstance(top_k, int)
        or top_k <= 0
    ):
        raise RetrievalConfigurationError(
            "RETRIEVAL_TOP_K must be a positive integer."
        )

    if (
        isinstance(score_threshold, bool)
        or not isinstance(score_threshold, int | float)
        or not isfinite(score_threshold)
        or not 0 <= score_threshold <= 1
    ):
        raise RetrievalConfigurationError(
            "RETRIEVAL_SCORE_THRESHOLD must be "
            "between zero and one."
        )

    return top_k, float(score_threshold)


def _normalize_document_ids(
    document_ids: Iterable[int] | None,
) -> tuple[int, ...] | None:
    if document_ids is None:
        return None

    normalized_ids: list[int] = []
    seen_ids: set[int] = set()

    for document_id in document_ids:
        if (
            isinstance(document_id, bool)
            or not isinstance(document_id, int)
            or document_id <= 0
        ):
            raise RetrievalInputError(
                "document_ids must contain "
                "positive integers."
            )

        if document_id not in seen_ids:
            normalized_ids.append(document_id)
            seen_ids.add(document_id)

    return tuple(normalized_ids)


def retrieve_relevant_chunks(
    question: str,
    *,
    document_ids: Iterable[int] | None = None,
) -> list[RetrievedDocumentChunk]:
    if not isinstance(question, str) or not question.strip():
        raise RetrievalInputError(
            "The question must be a non-empty string."
        )

    top_k, score_threshold = (
        _get_retrieval_configuration()
    )
    normalized_document_ids = (
        _normalize_document_ids(document_ids)
    )

    if normalized_document_ids == ():
        return []

    try:
        query_embedding = generate_query_embedding(
            question.strip()
        )
    except EmbeddingServiceError as exc:
        raise RetrievalError(
            "The question embedding could not be generated."
        ) from exc

    distance_expression = CosineDistance(
        "embedding",
        HalfVector(query_embedding),
    )

    queryset = (
        DocumentChunk.objects.filter(
            embedding__isnull=False,
            document__status=Document.Status.INDEXED,
        )
        .select_related("document")
        .only(
            "id",
            "document",
            "document__title",
            "content",
            "chunk_index",
        )
    )

    if normalized_document_ids is not None:
        queryset = queryset.filter(
            document_id__in=normalized_document_ids
        )

    nearest_chunks = (
        queryset.annotate(
            retrieval_distance=distance_expression,
        )
        .order_by("retrieval_distance")[:top_k]
    )

    results: list[RetrievedDocumentChunk] = []

    for chunk in nearest_chunks:
        distance = float(chunk.retrieval_distance)

        if not isfinite(distance):
            raise RetrievalError(
                "The database returned an invalid "
                "cosine distance."
            )

        similarity_score = max(
            -1.0,
            min(1.0, 1.0 - distance),
        )

        if similarity_score < score_threshold:
            continue

        results.append(
            RetrievedDocumentChunk(
                chunk_id=chunk.pk,
                document_id=chunk.document_id,
                document_title=chunk.document.title,
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                similarity_score=similarity_score,
            )
        )

    return results
