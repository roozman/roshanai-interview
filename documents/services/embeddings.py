import time
from collections.abc import Callable, Sequence
from typing import Literal

import httpx
from django.conf import settings

from django.db import transaction

from documents.models import DocumentChunk

from documents.constants import EMBEDDING_DIMENSION


EmbeddingInputType = Literal["passage", "query"]

DOCUMENT_INPUT_TYPE: EmbeddingInputType = "passage"
QUERY_INPUT_TYPE: EmbeddingInputType = "query"

MAX_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 30

RETRYABLE_STATUS_CODES = {
    408,
    429,
    500,
    502,
    503,
    524,
    529,
}


class EmbeddingServiceError(RuntimeError):
    pass


class EmbeddingConfigurationError(
    EmbeddingServiceError
):
    pass


def _validate_configuration() -> None:
    if not settings.OPENROUTER_API_KEY:
        raise EmbeddingConfigurationError(
            "OPENROUTER_API_KEY is not configured."
        )

    if settings.OPENROUTER_EMBEDDING_BATCH_SIZE <= 0:
        raise EmbeddingConfigurationError(
            "OPENROUTER_EMBEDDING_BATCH_SIZE "
            "must be greater than zero."
        )

    if settings.OPENROUTER_TIMEOUT_SECONDS <= 0:
        raise EmbeddingConfigurationError(
            "OPENROUTER_TIMEOUT_SECONDS "
            "must be greater than zero."
        )


def _error_message(response: httpx.Response) -> str:
    message = ""

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    error = payload.get("error")

    if isinstance(error, dict):
        raw_message = error.get("message")

        if isinstance(raw_message, str):
            message = raw_message[:300]

    base_message = (
        "OpenRouter embedding request failed "
        f"with HTTP {response.status_code}."
    )

    if message:
        return f"{base_message} {message}"

    return base_message


def _retry_delay(
    response: httpx.Response | None,
    attempt: int,
) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")

        if retry_after:
            try:
                return min(
                    float(retry_after),
                    MAX_RETRY_DELAY_SECONDS,
                )
            except ValueError:
                pass

    return min(
        2 ** attempt,
        MAX_RETRY_DELAY_SECONDS,
    )


def _parse_embeddings(
    response: httpx.Response,
    expected_count: int,
) -> list[list[float]]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise EmbeddingServiceError(
            "OpenRouter returned invalid JSON."
        ) from exc

    data = payload.get("data")

    if not isinstance(data, list):
        raise EmbeddingServiceError(
            "OpenRouter response does not contain "
            "an embedding data list."
        )

    if len(data) != expected_count:
        raise EmbeddingServiceError(
            "OpenRouter returned an unexpected "
            "number of embeddings."
        )

    ordered_embeddings: list[
        list[float] | None
    ] = [None] * expected_count

    for item in data:
        if not isinstance(item, dict):
            raise EmbeddingServiceError(
                "OpenRouter returned an invalid "
                "embedding item."
            )

        index = item.get("index")
        embedding = item.get("embedding")

        if (
            not isinstance(index, int)
            or not 0 <= index < expected_count
            or ordered_embeddings[index] is not None
        ):
            raise EmbeddingServiceError(
                "OpenRouter returned invalid or "
                "duplicate embedding indexes."
            )

        if (
            not isinstance(embedding, list)
            or len(embedding) != EMBEDDING_DIMENSION
        ):
            raise EmbeddingServiceError(
                "OpenRouter returned an embedding "
                f"with an invalid dimension; expected "
                f"{EMBEDDING_DIMENSION}."
            )

        if not all(
            isinstance(value, int | float)
            for value in embedding
        ):
            raise EmbeddingServiceError(
                "OpenRouter returned non-numeric "
                "embedding values."
            )

        ordered_embeddings[index] = [
            float(value)
            for value in embedding
        ]

    if any(
        embedding is None
        for embedding in ordered_embeddings
    ):
        raise EmbeddingServiceError(
            "OpenRouter response is missing embeddings."
        )

    return [
        embedding
        for embedding in ordered_embeddings
        if embedding is not None
    ]


def _request_batch(
    *,
    client: httpx.Client,
    texts: list[str],
    input_type: EmbeddingInputType,
    sleep: Callable[[float], None],
) -> list[list[float]]:
    response: httpx.Response | None = None

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = client.post(
                f"{settings.OPENROUTER_BASE_URL}/embeddings",
                headers={
                    "Authorization": (
                        f"Bearer "
                        f"{settings.OPENROUTER_API_KEY}"
                    ),
                    "Content-Type": "application/json",
                },
                json={
                    "model": (
                        settings.OPENROUTER_EMBEDDING_MODEL
                    ),
                    "input": texts,
                    "input_type": input_type,
                    "dimensions": EMBEDDING_DIMENSION,
                    "encoding_format": "float",
                },
                timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
            )
        except httpx.RequestError as exc:
            if attempt == MAX_ATTEMPTS - 1:
                raise EmbeddingServiceError(
                    "Could not connect to OpenRouter."
                ) from exc

        else:
            if response.is_success:
                return _parse_embeddings(
                    response,
                    expected_count=len(texts),
                )

            if (
                response.status_code
                not in RETRYABLE_STATUS_CODES
                or attempt == MAX_ATTEMPTS - 1
            ):
                raise EmbeddingServiceError(
                    _error_message(response)
                )

        sleep(_retry_delay(response, attempt))

    raise EmbeddingServiceError(
        "OpenRouter embedding request failed."
    )


def generate_embeddings(
    texts: Sequence[str],
    *,
    input_type: EmbeddingInputType,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[list[float]]:
    _validate_configuration()

    normalized_texts = list(texts)

    if not normalized_texts:
        return []

    if any(
        not isinstance(text, str) or not text.strip()
        for text in normalized_texts
    ):
        raise EmbeddingServiceError(
            "Embedding inputs must be non-empty strings."
        )

    active_client = client or httpx.Client()
    owns_client = client is None
    embeddings: list[list[float]] = []

    try:
        batch_size = (
            settings.OPENROUTER_EMBEDDING_BATCH_SIZE
        )

        for start in range(
            0,
            len(normalized_texts),
            batch_size,
        ):
            batch = normalized_texts[
                start:start + batch_size
            ]

            embeddings.extend(
                _request_batch(
                    client=active_client,
                    texts=batch,
                    input_type=input_type,
                    sleep=sleep,
                )
            )
    finally:
        if owns_client:
            active_client.close()

    return embeddings


def generate_document_embeddings(
    texts: Sequence[str],
    **kwargs,
) -> list[list[float]]:
    return generate_embeddings(
        texts,
        input_type=DOCUMENT_INPUT_TYPE,
        **kwargs,
    )


def generate_query_embedding(
    text: str,
    **kwargs,
) -> list[float]:
    embeddings = generate_embeddings(
        [text],
        input_type=QUERY_INPUT_TYPE,
        **kwargs,
    )

    return embeddings[0]

def embed_document_chunks(
    document_id: int,
) -> int:
    source_chunks = list(
        DocumentChunk.objects.filter(
            document_id=document_id
        ).order_by("chunk_index")
    )

    if not source_chunks:
        raise EmbeddingServiceError(
            "The document does not have any chunks."
        )

    embeddings = generate_document_embeddings(
        [chunk.content for chunk in source_chunks]
    )

    if len(embeddings) != len(source_chunks):
        raise EmbeddingServiceError(
            "The number of embeddings does not match "
            "the number of document chunks."
        )

    source_chunk_ids = [
        chunk.pk
        for chunk in source_chunks
    ]

    with transaction.atomic():
        current_chunks = list(
            DocumentChunk.objects.select_for_update()
            .filter(document_id=document_id)
            .order_by("chunk_index")
        )

        current_chunk_ids = [
            chunk.pk
            for chunk in current_chunks
        ]

        if current_chunk_ids != source_chunk_ids:
            raise EmbeddingServiceError(
                "Document chunks changed while "
                "embeddings were being generated."
            )

        for chunk, embedding in zip(
            current_chunks,
            embeddings,
            strict=True,
        ):
            chunk.embedding = embedding

        DocumentChunk.objects.bulk_update(
            current_chunks,
            fields=["embedding"],
        )

    return len(current_chunks)