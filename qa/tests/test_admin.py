from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from documents.models import Document, DocumentChunk
from qa.models import QuestionAnswer, RetrievedChunk


class QuestionAnswerAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="question-admin-user",
            password="test-password",
        )
        self.client.force_login(self.user)

        self.document = Document.objects.create(
            title="Admin source document",
            file="documents/admin-source.docx",
            status=Document.Status.INDEXED,
        )
        self.chunk = DocumentChunk.objects.create(
            document=self.document,
            content="Source content for the answer.",
            chunk_index=0,
            start_offset=0,
            end_offset=30,
            token_count=6,
        )
        self.question_answer = (
            QuestionAnswer.objects.create(
                question="What is the source?",
                answer="This is the answer. [Source 1]",
                status=QuestionAnswer.Status.COMPLETED,
                model_name="test-model",
                latency_ms=250,
            )
        )
        self.retrieved_chunk = (
            RetrievedChunk.objects.create(
                question_answer=self.question_answer,
                chunk=self.chunk,
                rank=1,
                similarity_score=0.9,
                excerpt=self.chunk.content,
            )
        )

    def test_changelist_shows_history_and_source_count(
        self,
    ):
        response = self.client.get(
            reverse(
                "admin:qa_questionanswer_changelist"
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            self.question_answer.question,
        )
        self.assertContains(response, "Completed")
        self.assertContains(response, "test-model")

        stored_question = (
            response.context["cl"].result_list[0]
        )

        self.assertEqual(
            stored_question._source_count,
            1,
        )

    def test_detail_shows_readonly_sources_inline(
        self,
    ):
        response = self.client.get(
            reverse(
                "admin:qa_questionanswer_change",
                args=[self.question_answer.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            self.question_answer.question,
        )
        self.assertContains(
            response,
            self.question_answer.answer,
        )
        self.assertContains(
            response,
            self.document.title,
        )
        self.assertContains(
            response,
            self.retrieved_chunk.excerpt,
        )

    def test_history_cannot_be_modified(self):
        response = self.client.post(
            reverse(
                "admin:qa_questionanswer_change",
                args=[self.question_answer.pk],
            ),
            {
                "question": "Modified question",
                "answer": "Modified answer",
            },
        )

        self.assertEqual(response.status_code, 403)

        self.question_answer.refresh_from_db()

        self.assertEqual(
            self.question_answer.question,
            "What is the source?",
        )
        self.assertEqual(
            self.question_answer.answer,
            "This is the answer. [Source 1]",
        )

    def test_inline_survives_document_deletion(self):
        self.document.delete()

        response = self.client.get(
            reverse(
                "admin:qa_questionanswer_change",
                args=[self.question_answer.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deleted document")
        self.assertContains(
            response,
            "Source content for the answer.",
        )
