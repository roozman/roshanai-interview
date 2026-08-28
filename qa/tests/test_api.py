from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from documents.models import Document, DocumentChunk
from documents.services.retrieval import (
    RetrievedDocumentChunk,
)
from qa.models import QuestionAnswer, RetrievedChunk
from qa.services.rag import (
    RAGAnswer,
    RAGGenerationError,
)


class QuestionAnswerAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="question-api-user",
            password="test-password",
        )
        self.client.force_authenticate(user=self.user)

        self.list_url = reverse("question-list")

        self.document = Document.objects.create(
            title="Contract sample",
            file="documents/question-api.docx",
            status=Document.Status.INDEXED,
        )
        self.chunk = DocumentChunk.objects.create(
            document=self.document,
            content="The contract can be terminated with notice.",
            chunk_index=0,
            start_offset=0,
            end_offset=43,
            token_count=9,
        )

    def make_rag_result(self) -> RAGAnswer:
        source = RetrievedDocumentChunk(
            chunk_id=self.chunk.pk,
            document_id=self.document.pk,
            document_title=self.document.title,
            content=self.chunk.content,
            chunk_index=self.chunk.chunk_index,
            similarity_score=0.86,
        )

        return RAGAnswer(
            answer=(
                "The contract can be terminated with notice. "
                "[Source 1]"
            ),
            model_name=(
                "nvidia/nemotron-3-super-120b-a12b:free"
            ),
            sources=(source,),
        )

    def test_creates_question_answer_with_sources(self):
        rag_result = self.make_rag_result()

        with patch(
            "qa.services.history.answer_question",
            return_value=rag_result,
        ) as mock_answer_question:
            with patch(
                "qa.services.history.perf_counter",
                side_effect=[100.0, 100.24],
            ):
                response = self.client.post(
                    self.list_url,
                    {
                        "question": (
                            "How can the contract be terminated?"
                        ),
                        "document_ids": [
                            self.document.pk,
                            self.document.pk,
                        ],
                    },
                    format="json",
                )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            response.data["status"],
            QuestionAnswer.Status.COMPLETED,
        )
        self.assertEqual(
            response.data["answer"],
            rag_result.answer,
        )
        self.assertEqual(
            response.data["model"],
            rag_result.model_name,
        )
        self.assertEqual(
            response.data["latency_ms"],
            240,
        )

        self.assertEqual(len(response.data["sources"]), 1)

        source = response.data["sources"][0]

        self.assertEqual(
            source["document_id"],
            self.document.pk,
        )
        self.assertEqual(
            source["document_title"],
            self.document.title,
        )
        self.assertEqual(
            source["chunk_id"],
            self.chunk.pk,
        )
        self.assertEqual(source["rank"], 1)
        self.assertEqual(source["score"], 0.86)
        self.assertEqual(
            source["excerpt"],
            self.chunk.content,
        )

        mock_answer_question.assert_called_once_with(
            "How can the contract be terminated?",
            document_ids=[self.document.pk],
        )

        stored = QuestionAnswer.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(
            stored.retrieved_chunks.count(),
            1,
        )

    def test_returns_validation_errors(self):
        invalid_payloads = (
            {},
            {"question": "   "},
            {
                "question": "Valid question?",
                "document_ids": [0],
            },
            {
                "question": "Valid question?",
                "document_ids": ["invalid"],
            },
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    self.list_url,
                    payload,
                    format="json",
                )

                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertEqual(
                    response.data["error"]["code"],
                    "validation_error",
                )

        self.assertFalse(
            QuestionAnswer.objects.exists()
        )

    def test_returns_controlled_error_and_saves_failure(
        self,
    ):
        model_error = RAGGenerationError(
            "OpenRouter could not generate an answer."
        )

        with patch(
            "qa.services.history.answer_question",
            side_effect=model_error,
        ):
            with patch(
                "qa.services.history.perf_counter",
                side_effect=[200.0, 200.5],
            ):
                response = self.client.post(
                    self.list_url,
                    {
                        "question": "A valid question?",
                    },
                    format="json",
                )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(
            response.data["error"]["code"],
            "question_processing_unavailable",
        )
        self.assertEqual(
            response.data["error"]["details"],
            None,
        )

        stored = QuestionAnswer.objects.get()

        self.assertEqual(
            stored.status,
            QuestionAnswer.Status.FAILED,
        )
        self.assertEqual(stored.latency_ms, 500)
        self.assertEqual(
            stored.error_message,
            "OpenRouter could not generate an answer.",
        )

    def test_lists_paginated_history(self):
        QuestionAnswer.objects.bulk_create(
            [
                QuestionAnswer(
                    question=f"Question {index}",
                    answer=f"Answer {index}",
                    status=QuestionAnswer.Status.COMPLETED,
                )
                for index in range(21)
            ]
        )

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(response.data["count"], 21)
        self.assertEqual(
            len(response.data["results"]),
            20,
        )
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

    def test_retrieves_history_after_document_deletion(
        self,
    ):
        question_answer = QuestionAnswer.objects.create(
            question="Historical question?",
            answer="Historical answer.",
            status=QuestionAnswer.Status.COMPLETED,
        )
        retrieved_record = RetrievedChunk.objects.create(
            question_answer=question_answer,
            chunk=self.chunk,
            rank=1,
            similarity_score=0.8,
            excerpt="Preserved historical excerpt.",
        )

        self.document.delete()
        retrieved_record.refresh_from_db()

        detail_url = reverse(
            "question-detail",
            args=[question_answer.pk],
        )
        response = self.client.get(detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        source = response.data["sources"][0]

        self.assertIsNone(source["document_id"])
        self.assertIsNone(source["document_title"])
        self.assertIsNone(source["chunk_id"])
        self.assertEqual(
            source["excerpt"],
            "Preserved historical excerpt.",
        )

    def test_rejects_unsupported_updates(self):
        question_answer = QuestionAnswer.objects.create(
            question="Immutable question?",
            answer="Immutable answer.",
            status=QuestionAnswer.Status.COMPLETED,
        )
        detail_url = reverse(
            "question-detail",
            args=[question_answer.pk],
        )

        response = self.client.patch(
            detail_url,
            {"answer": "Modified answer."},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.list_url)

        self.assertIn(
            response.status_code,
            (
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ),
        )
