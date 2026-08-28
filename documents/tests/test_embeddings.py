import json
from unittest.mock import Mock

import httpx
from django.test import SimpleTestCase, override_settings

from documents.constants import EMBEDDING_DIMENSION
from documents.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingServiceError,
    generate_document_embeddings,
    generate_query_embedding,
)


@override_settings(
    OPENROUTER_API_KEY="test-api-key",
    OPENROUTER_BASE_URL="https://openrouter.test/api/v1",
    OPENROUTER_EMBEDDING_MODEL=(
        "nvidia/nemotron-3-embed-1b:free"
    ),
    OPENROUTER_EMBEDDING_BATCH_SIZE=2,
    OPENROUTER_TIMEOUT_SECONDS=10,
)
class EmbeddingServiceTests(SimpleTestCase):
    def test_batches_and_orders_embeddings(self):
        payloads = []

        def handler(request):
            payload = json.loads(request.content)
            payloads.append(payload)

            data = [
                {
                    "index": index,
                    "embedding": (
                        [float(len(text))]
                        * EMBEDDING_DIMENSION
                    ),
                }
                for index, text in enumerate(
                    payload["input"]
                )
            ]

            return httpx.Response(
                200,
                json={
                    "data": list(reversed(data)),
                    "model": (
                        "private/openrouter/nvidia/"
                        "nemotron-3-embed-1b"
                    ),
                    "object": "list",
                },
            )

        transport = httpx.MockTransport(handler)

        with httpx.Client(
            transport=transport
        ) as client:
            embeddings = generate_document_embeddings(
                ["a", "bb", "ccc"],
                client=client,
                sleep=lambda delay: None,
            )

        self.assertEqual(len(payloads), 2)
        self.assertTrue(
            all(
                payload["input_type"] == "passage"
                for payload in payloads
            )
        )
        self.assertEqual(
            [
                embedding[0]
                for embedding in embeddings
            ],
            [1.0, 2.0, 3.0],
        )
        self.assertTrue(
            all(
                len(embedding)
                == EMBEDDING_DIMENSION
                for embedding in embeddings
            )
        )

    def test_query_uses_query_input_type(self):
        def handler(request):
            payload = json.loads(request.content)

            self.assertEqual(
                payload["input_type"],
                "query",
            )

            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "index": 0,
                            "embedding": (
                                [0.2]
                                * EMBEDDING_DIMENSION
                            ),
                        }
                    ],
                    "model": "internal-model-name",
                    "object": "list",
                },
            )

        transport = httpx.MockTransport(handler)

        with httpx.Client(
            transport=transport
        ) as client:
            embedding = generate_query_embedding(
                "پرسش آزمایشی",
                client=client,
                sleep=lambda delay: None,
            )

        self.assertEqual(
            len(embedding),
            EMBEDDING_DIMENSION,
        )

    def test_retries_rate_limit_response(self):
        request_count = 0
        sleep = Mock()

        def handler(request):
            nonlocal request_count
            request_count += 1

            if request_count == 1:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "0"},
                    json={
                        "error": {
                            "message": (
                                "Rate limit exceeded"
                            )
                        }
                    },
                )

            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "index": 0,
                            "embedding": (
                                [0.3]
                                * EMBEDDING_DIMENSION
                            ),
                        }
                    ],
                    "model": "internal-model-name",
                    "object": "list",
                },
            )

        transport = httpx.MockTransport(handler)

        with httpx.Client(
            transport=transport
        ) as client:
            embeddings = generate_document_embeddings(
                ["متن"],
                client=client,
                sleep=sleep,
            )

        self.assertEqual(request_count, 2)
        self.assertEqual(len(embeddings), 1)
        sleep.assert_called_once_with(0.0)

    def test_rejects_invalid_dimension(self):
        def handler(request):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "index": 0,
                            "embedding": (
                                [0.1]
                                * (
                                    EMBEDDING_DIMENSION - 1
                                )
                            ),
                        }
                    ],
                    "model": "internal-model-name",
                    "object": "list",
                },
            )

        transport = httpx.MockTransport(handler)

        with httpx.Client(
            transport=transport
        ) as client:
            with self.assertRaises(
                EmbeddingServiceError
            ):
                generate_document_embeddings(
                    ["متن"],
                    client=client,
                    sleep=lambda delay: None,
                )

    @override_settings(OPENROUTER_API_KEY="")
    def test_rejects_missing_api_key(self):
        with self.assertRaises(
            EmbeddingConfigurationError
        ):
            generate_document_embeddings(
                ["متن"]
            )