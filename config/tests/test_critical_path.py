from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from documents.constants import EMBEDDING_DIMENSION
from documents.models import Document
from documents.tests.helpers import (
    FakeTokenizerMixin,
    TemporaryMediaRootMixin,
    build_test_embeddings,
    make_uploaded_docx,
)
from qa.models import QuestionAnswer


class CriticalPathTests(
    FakeTokenizerMixin,
    TemporaryMediaRootMixin,
    APITestCase,
):
    def setUp(self):
        super().setUp()

        self.user = get_user_model().objects.create_user(
            username="critical-path-user",
            password="test-password",
        )
        self.client.force_authenticate(user=self.user)

    @patch("qa.services.rag._build_chain")
    @patch(
        "documents.services.retrieval."
        "generate_query_embedding"
    )
    @patch(
        "documents.services.embeddings."
        "generate_document_embeddings",
        side_effect=build_test_embeddings,
    )
    def test_upload_to_answer_with_sources(
        self,
        mock_document_embeddings,
        mock_query_embedding,
        mock_build_chain,
    ):
        mock_query_embedding.return_value = (
            [0.1] * EMBEDDING_DIMENSION
        )
        mock_build_chain.return_value.invoke.return_value = (
            "The contract can be terminated with "
            "written notice. [Source 1]"
        )

        document_response = self.client.post(
            reverse("document-list"),
            {
                "title": "Termination contract",
                "file": make_uploaded_docx(
                    paragraphs=(
                        "The contract can be terminated "
                        "with written notice.",
                    ),
                ),
            },
            format="multipart",
        )

        self.assertEqual(
            document_response.status_code,
            status.HTTP_201_CREATED,
        )

        document = Document.objects.get(
            pk=document_response.data["id"]
        )
        chunks = list(document.chunks.all())

        self.assertEqual(
            document.status,
            Document.Status.INDEXED,
        )
        self.assertEqual(len(chunks), 1)
        self.assertIsNotNone(chunks[0].embedding)

        question = (
            "How can the contract be terminated?"
        )

        question_response = self.client.post(
            reverse("question-list"),
            {
                "question": question,
                "document_ids": [document.pk],
            },
            format="json",
        )

        self.assertEqual(
            question_response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            question_response.data["status"],
            QuestionAnswer.Status.COMPLETED,
        )
        self.assertEqual(
            len(question_response.data["sources"]),
            1,
        )
        self.assertEqual(
            question_response.data["sources"][0][
                "document_id"
            ],
            document.pk,
        )
        self.assertIn(
            "[Source 1]",
            question_response.data["answer"],
        )

        stored_answer = QuestionAnswer.objects.get(
            pk=question_response.data["id"]
        )

        self.assertEqual(
            stored_answer.retrieved_chunks.count(),
            1,
        )

        mock_chain = mock_build_chain.return_value
        prompt_input = mock_chain.invoke.call_args.args[0]

        self.assertEqual(
            prompt_input["question"],
            question,
        )
        self.assertIn(
            "written notice",
            prompt_input["context"],
        )

        mock_document_embeddings.assert_called_once()
        mock_query_embedding.assert_called_once_with(
            question
        )
        mock_chain.invoke.assert_called_once()