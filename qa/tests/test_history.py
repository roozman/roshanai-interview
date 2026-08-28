from unittest.mock import patch

from django.test import TestCase, override_settings

from documents.models import Document, DocumentChunk
from documents.services.retrieval import (
    RetrievedDocumentChunk,
)
from qa.models import QuestionAnswer, RetrievedChunk
from qa.services.history import process_question
from qa.services.rag import (
    RAGAnswer,
    RAGGenerationError,
)


@override_settings(
    OPENROUTER_CHAT_MODEL=(
        "nvidia/nemotron-3-super-120b-a12b:free"
    ),
)
class QuestionHistoryServiceTests(TestCase):
    def setUp(self):
        self.document = Document.objects.create(
            title="Test document",
            file="documents/history-test.docx",
            status=Document.Status.INDEXED,
        )

    def create_chunk(
        self,
        *,
        chunk_index: int,
        content: str,
    ) -> DocumentChunk:
        return DocumentChunk.objects.create(
            document=self.document,
            content=content,
            chunk_index=chunk_index,
            start_offset=0,
            end_offset=len(content),
            token_count=10,
        )

    def make_source(
        self,
        chunk: DocumentChunk,
        *,
        score: float,
    ) -> RetrievedDocumentChunk:
        return RetrievedDocumentChunk(
            chunk_id=chunk.pk,
            document_id=self.document.pk,
            document_title=self.document.title,
            content=chunk.content,
            chunk_index=chunk.chunk_index,
            similarity_score=score,
        )

    def test_saves_successful_answer_and_sources(self):
        first_chunk = self.create_chunk(
            chunk_index=0,
            content="A" * 1200,
        )
        second_chunk = self.create_chunk(
            chunk_index=1,
            content="Second source content.",
        )

        rag_result = RAGAnswer(
            answer="Supported answer. [Source 1]",
            model_name=(
                "nvidia/nemotron-3-super-120b-a12b:free"
            ),
            sources=(
                self.make_source(
                    first_chunk,
                    score=0.91,
                ),
                self.make_source(
                    second_chunk,
                    score=0.82,
                ),
            ),
        )

        with patch(
            "qa.services.history.answer_question",
            return_value=rag_result,
        ) as mock_answer_question:
            with patch(
                "qa.services.history.perf_counter",
                side_effect=[100.0, 100.125],
            ):
                result = process_question(
                    "  Test question?  ",
                    document_ids=[self.document.pk],
                )

        stored = QuestionAnswer.objects.get(
            pk=result.pk
        )

        self.assertEqual(
            stored.question,
            "Test question?",
        )
        self.assertEqual(
            stored.answer,
            "Supported answer. [Source 1]",
        )
        self.assertEqual(
            stored.status,
            QuestionAnswer.Status.COMPLETED,
        )
        self.assertEqual(stored.latency_ms, 125)
        self.assertEqual(stored.error_message, "")
        self.assertEqual(
            stored.model_name,
            rag_result.model_name,
        )

        mock_answer_question.assert_called_once_with(
            "Test question?",
            document_ids=[self.document.pk],
        )

        retrieved_records = list(
            stored.retrieved_chunks.all()
        )

        self.assertEqual(len(retrieved_records), 2)
        self.assertEqual(
            [record.rank for record in retrieved_records],
            [1, 2],
        )
        self.assertEqual(
            [
                record.chunk_id
                for record in retrieved_records
            ],
            [first_chunk.pk, second_chunk.pk],
        )
        self.assertEqual(
            [
                record.similarity_score
                for record in retrieved_records
            ],
            [0.91, 0.82],
        )
        self.assertEqual(
            len(retrieved_records[0].excerpt),
            1000,
        )
        self.assertEqual(
            retrieved_records[1].excerpt,
            second_chunk.content,
        )

    def test_saves_failed_generation(self):
        error = RAGGenerationError(
            "OpenRouter could not generate an answer."
        )

        with patch(
            "qa.services.history.answer_question",
            side_effect=error,
        ):
            with patch(
                "qa.services.history.perf_counter",
                side_effect=[200.0, 200.25],
            ):
                with self.assertRaises(
                    RAGGenerationError
                ):
                    process_question("Failed question?")

        stored = QuestionAnswer.objects.get()

        self.assertEqual(
            stored.status,
            QuestionAnswer.Status.FAILED,
        )
        self.assertEqual(stored.answer, "")
        self.assertEqual(stored.latency_ms, 250)
        self.assertEqual(
            stored.error_message,
            "OpenRouter could not generate an answer.",
        )
        self.assertEqual(
            stored.retrieved_chunks.count(),
            0,
        )

    def test_saves_completed_answer_without_sources(self):
        rag_result = RAGAnswer(
            answer=(
                "اطلاعات کافی برای پاسخ در اسناد "
                "موجود پیدا نشد."
            ),
            model_name=(
                "nvidia/nemotron-3-super-120b-a12b:free"
            ),
            sources=(),
        )

        with patch(
            "qa.services.history.answer_question",
            return_value=rag_result,
        ):
            with patch(
                "qa.services.history.perf_counter",
                side_effect=[300.0, 300.01],
            ):
                stored = process_question(
                    "سؤال نامرتبط چیست؟"
                )

        self.assertEqual(
            stored.status,
            QuestionAnswer.Status.COMPLETED,
        )
        self.assertEqual(stored.latency_ms, 10)
        self.assertEqual(
            stored.retrieved_chunks.count(),
            0,
        )

    @patch("qa.services.history.answer_question")
    def test_rejects_empty_question_without_history(
        self,
        mock_answer_question,
    ):
        with self.assertRaises(ValueError):
            process_question("   ")

        self.assertEqual(
            QuestionAnswer.objects.count(),
            0,
        )
        mock_answer_question.assert_not_called()

    def test_preserves_excerpt_after_document_deletion(
        self,
    ):
        chunk = self.create_chunk(
            chunk_index=0,
            content="Historical source excerpt.",
        )
        question_answer = QuestionAnswer.objects.create(
            question="Historical question?",
            answer="Historical answer.",
            status=QuestionAnswer.Status.COMPLETED,
        )
        retrieved_record = RetrievedChunk.objects.create(
            question_answer=question_answer,
            chunk=chunk,
            rank=1,
            similarity_score=0.9,
            excerpt=chunk.content,
        )

        self.document.delete()
        retrieved_record.refresh_from_db()

        self.assertIsNone(retrieved_record.chunk_id)
        self.assertEqual(
            retrieved_record.excerpt,
            "Historical source excerpt.",
        )
        self.assertTrue(
            QuestionAnswer.objects.filter(
                pk=question_answer.pk
            ).exists()
        )