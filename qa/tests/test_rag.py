from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from documents.services.retrieval import (
    RetrievedDocumentChunk,
    RetrievalError,
)
from qa.services.rag import (
    RAGConfigurationError,
    RAGGenerationError,
    RAGRetrievalError,
    RAGServiceError,
    _format_context,
    answer_question,
)


@override_settings(
    OPENROUTER_API_KEY="test-api-key",
    OPENROUTER_BASE_URL="https://openrouter.ai/api/v1",
    OPENROUTER_CHAT_MODEL=(
        "nvidia/nemotron-3-super-120b-a12b:free"
    ),
    OPENROUTER_CHAT_TEMPERATURE=0,
    OPENROUTER_CHAT_MAX_TOKENS=800,
    OPENROUTER_CHAT_TIMEOUT_MS=60000,
    OPENROUTER_CHAT_MAX_RETRIES=0,
    RAG_MAX_CONTEXT_CHARACTERS=12000,
)
class RAGServiceTests(SimpleTestCase):
    def make_chunk(
        self,
        *,
        chunk_id: int = 10,
        document_id: int = 4,
        title: str = "Test document",
        content: str = "Relevant document content.",
        chunk_index: int = 0,
        score: float = 0.82,
    ) -> RetrievedDocumentChunk:
        return RetrievedDocumentChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            document_title=title,
            content=content,
            chunk_index=chunk_index,
            similarity_score=score,
        )

    @patch("qa.services.rag._build_chain")
    @patch(
        "qa.services.rag.retrieve_relevant_chunks"
    )
    def test_generates_answer_with_sources(
        self,
        mock_retrieve,
        mock_build_chain,
    ):
        chunk = self.make_chunk()
        mock_retrieve.return_value = [chunk]

        mock_chain = mock_build_chain.return_value
        mock_chain.invoke.return_value = (
            "The supported answer. [Source 1]"
        )

        result = answer_question(
            "What does the document say?",
            document_ids=[4],
        )

        self.assertEqual(
            result.answer,
            "The supported answer. [Source 1]",
        )
        self.assertEqual(result.sources, (chunk,))
        self.assertEqual(
            result.model_name,
            "nvidia/nemotron-3-super-120b-a12b:free",
        )

        mock_retrieve.assert_called_once_with(
            "What does the document say?",
            document_ids=[4],
        )

        prompt_input = (
            mock_chain.invoke.call_args.args[0]
        )

        self.assertEqual(
            prompt_input["question"],
            "What does the document say?",
        )
        self.assertIn(
            "[Source 1",
            prompt_input["context"],
        )
        self.assertIn(
            chunk.content,
            prompt_input["context"],
        )

    @patch("qa.services.rag._build_chain")
    @patch(
        "qa.services.rag.retrieve_relevant_chunks",
        return_value=[],
    )
    def test_returns_controlled_persian_answer_without_evidence(
        self,
        mock_retrieve,
        mock_build_chain,
    ):
        result = answer_question(
            "این سند درباره چه موضوعی است؟"
        )

        self.assertEqual(
            result.answer,
            (
                "اطلاعات کافی برای پاسخ به این سؤال "
                "در اسناد موجود پیدا نشد."
            ),
        )
        self.assertEqual(result.sources, ())
        mock_retrieve.assert_called_once()
        mock_build_chain.assert_not_called()

    @patch(
        "qa.services.rag.retrieve_relevant_chunks"
    )
    def test_wraps_retrieval_errors(
        self,
        mock_retrieve,
    ):
        mock_retrieve.side_effect = RetrievalError(
            "Embedding service failed."
        )

        with self.assertRaises(RAGRetrievalError):
            answer_question("A valid question")

    @patch("qa.services.rag._build_chain")
    @patch(
        "qa.services.rag.retrieve_relevant_chunks"
    )
    def test_wraps_model_errors(
        self,
        mock_retrieve,
        mock_build_chain,
    ):
        mock_retrieve.return_value = [
            self.make_chunk()
        ]
        mock_build_chain.return_value.invoke.side_effect = (
            TimeoutError("Request timed out.")
        )

        with self.assertRaises(RAGGenerationError):
            answer_question("A valid question")

    @patch("qa.services.rag._build_chain")
    @patch(
        "qa.services.rag.retrieve_relevant_chunks"
    )
    def test_rejects_empty_model_response(
        self,
        mock_retrieve,
        mock_build_chain,
    ):
        mock_retrieve.return_value = [
            self.make_chunk()
        ]
        mock_build_chain.return_value.invoke.return_value = (
            "   "
        )

        with self.assertRaises(RAGGenerationError):
            answer_question("A valid question")

    def test_limits_context_size(self):
        first_chunk = self.make_chunk(
            content="A" * 500,
        )
        second_chunk = self.make_chunk(
            chunk_id=11,
            chunk_index=1,
            content="B" * 500,
        )

        with self.settings(
            RAG_MAX_CONTEXT_CHARACTERS=180
        ):
            context, used_chunks = _format_context(
                [first_chunk, second_chunk]
            )

        self.assertLessEqual(len(context), 180)
        self.assertEqual(
            used_chunks,
            (first_chunk,),
        )
        self.assertIn("[Source 1", context)
        self.assertNotIn("[Source 2", context)

    @patch(
        "qa.services.rag.retrieve_relevant_chunks"
    )
    def test_rejects_missing_api_key(
        self,
        mock_retrieve,
    ):
        with self.settings(
            OPENROUTER_API_KEY="",
        ):
            with self.assertRaises(
                RAGConfigurationError
            ):
                answer_question("A valid question")

        mock_retrieve.assert_not_called()

    def test_rejects_empty_question(self):
        with self.assertRaises(RAGServiceError):
            answer_question("   ")