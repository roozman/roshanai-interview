from unittest.mock import patch

from django.test import TestCase, override_settings

from documents.constants import EMBEDDING_DIMENSION
from documents.models import Document, DocumentChunk
from documents.services.embeddings import EmbeddingServiceError
from documents.services.retrieval import (
    RetrievalConfigurationError,
    RetrievalError,
    RetrievalInputError,
    retrieve_relevant_chunks,
)


def make_embedding(
    first: float,
    second: float,
) -> list[float]:
    embedding = [0.0] * EMBEDDING_DIMENSION
    embedding[0] = first
    embedding[1] = second
    return embedding


@override_settings(
    RETRIEVAL_TOP_K=5,
    RETRIEVAL_SCORE_THRESHOLD=0.5,
)
class DocumentRetrievalTests(TestCase):
    def setUp(self):
        self.embedding_patcher = patch(
            "documents.services.retrieval."
            "generate_query_embedding",
            return_value=make_embedding(1.0, 0.0),
        )
        self.mock_generate_query_embedding = (
            self.embedding_patcher.start()
        )
        self.addCleanup(self.embedding_patcher.stop)

        self.document_counter = 0

    def create_chunk(
        self,
        *,
        title: str,
        content: str,
        embedding: list[float] | None,
        status: str = Document.Status.INDEXED,
    ) -> DocumentChunk:
        self.document_counter += 1

        document = Document.objects.create(
            title=title,
            file=(
                "documents/"
                f"retrieval-{self.document_counter}.docx"
            ),
            status=status,
        )

        return DocumentChunk.objects.create(
            document=document,
            content=content,
            chunk_index=0,
            start_offset=0,
            end_offset=len(content),
            token_count=1,
            embedding=embedding,
        )

    @override_settings(
        RETRIEVAL_SCORE_THRESHOLD=0.0,
    )
    def test_returns_top_five_in_similarity_order(self):
        vectors = (
            ("First", make_embedding(1.0, 0.0)),
            ("Second", make_embedding(4.0, 1.0)),
            ("Third", make_embedding(3.0, 2.0)),
            ("Fourth", make_embedding(2.0, 2.0)),
            ("Fifth", make_embedding(1.0, 2.0)),
            ("Sixth", make_embedding(1.0, 3.0)),
        )

        for title, embedding in vectors:
            self.create_chunk(
                title=title,
                content=f"{title} content",
                embedding=embedding,
            )

        results = retrieve_relevant_chunks(
            "Test question"
        )

        self.assertEqual(len(results), 5)
        self.assertEqual(
            [result.document_title for result in results],
            [
                "First",
                "Second",
                "Third",
                "Fourth",
                "Fifth",
            ],
        )

        scores = [
            result.similarity_score
            for result in results
        ]
        self.assertEqual(
            scores,
            sorted(scores, reverse=True),
        )

        self.mock_generate_query_embedding.assert_called_once_with(
            "Test question"
        )

    @override_settings(
        RETRIEVAL_SCORE_THRESHOLD=0.75,
    )
    def test_excludes_chunks_below_threshold(self):
        self.create_chunk(
            title="Exact",
            content="Exact match",
            embedding=make_embedding(1.0, 0.0),
        )
        self.create_chunk(
            title="Related",
            content="Related match",
            embedding=make_embedding(4.0, 3.0),
        )
        self.create_chunk(
            title="Unrelated",
            content="Unrelated text",
            embedding=make_embedding(0.0, 1.0),
        )

        results = retrieve_relevant_chunks(
            "Test question"
        )

        self.assertEqual(
            [result.document_title for result in results],
            ["Exact", "Related"],
        )
        self.assertTrue(
            all(
                result.similarity_score >= 0.75
                for result in results
            )
        )

    def test_filters_by_document_ids(self):
        first_chunk = self.create_chunk(
            title="First document",
            content="First content",
            embedding=make_embedding(1.0, 0.0),
        )
        second_chunk = self.create_chunk(
            title="Second document",
            content="Second content",
            embedding=make_embedding(1.0, 0.0),
        )

        results = retrieve_relevant_chunks(
            "Test question",
            document_ids=[
                second_chunk.document_id,
                second_chunk.document_id,
            ],
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0].document_id,
            second_chunk.document_id,
        )
        self.assertNotEqual(
            results[0].document_id,
            first_chunk.document_id,
        )

    @override_settings(
        RETRIEVAL_SCORE_THRESHOLD=0.0,
    )
    def test_ignores_unavailable_chunks(self):
        visible_chunk = self.create_chunk(
            title="Indexed document",
            content="Visible content",
            embedding=make_embedding(1.0, 0.0),
        )
        self.create_chunk(
            title="Failed document",
            content="Failed content",
            embedding=make_embedding(1.0, 0.0),
            status=Document.Status.FAILED,
        )
        self.create_chunk(
            title="Missing embedding",
            content="Missing embedding content",
            embedding=None,
        )

        results = retrieve_relevant_chunks(
            "Test question"
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0].chunk_id,
            visible_chunk.pk,
        )

    def test_empty_document_filter_skips_embedding_request(
        self,
    ):
        results = retrieve_relevant_chunks(
            "Test question",
            document_ids=[],
        )

        self.assertEqual(results, [])
        self.mock_generate_query_embedding.assert_not_called()

    def test_rejects_invalid_input(self):
        invalid_questions = (
            "",
            "   ",
            None,
        )

        for question in invalid_questions:
            with self.subTest(question=question):
                with self.assertRaises(
                    RetrievalInputError
                ):
                    retrieve_relevant_chunks(question)

        invalid_document_ids = (
            [0],
            [-1],
            [True],
            ["1"],
        )

        for document_ids in invalid_document_ids:
            with self.subTest(
                document_ids=document_ids
            ):
                with self.assertRaises(
                    RetrievalInputError
                ):
                    retrieve_relevant_chunks(
                        "Question",
                        document_ids=document_ids,
                    )

        self.mock_generate_query_embedding.assert_not_called()

    def test_rejects_invalid_configuration(self):
        with self.settings(RETRIEVAL_TOP_K=0):
            with self.assertRaises(
                RetrievalConfigurationError
            ):
                retrieve_relevant_chunks(
                    "Test question"
                )

        with self.settings(
            RETRIEVAL_SCORE_THRESHOLD=1.1
        ):
            with self.assertRaises(
                RetrievalConfigurationError
            ):
                retrieve_relevant_chunks(
                    "Test question"
                )

        self.mock_generate_query_embedding.assert_not_called()

    def test_wraps_embedding_service_errors(self):
        self.mock_generate_query_embedding.side_effect = (
            EmbeddingServiceError(
                "OpenRouter is unavailable."
            )
        )

        with self.assertRaisesRegex(
            RetrievalError,
            "question embedding could not be generated",
        ):
            retrieve_relevant_chunks(
                "Test question"
            )

    @override_settings(
        RETRIEVAL_TOP_K=2,
        RETRIEVAL_SCORE_THRESHOLD=0.0,
    )
    def test_removes_duplicate_content_and_backfills(
        self,
    ):
        self.create_chunk(
            title="First duplicate",
            content="Repeated content",
            embedding=make_embedding(1.0, 0.0),
        )
        self.create_chunk(
            title="Second duplicate",
            content="  repeated   CONTENT  ",
            embedding=make_embedding(4.0, 1.0),
        )
        self.create_chunk(
            title="Unique result",
            content="Unique content",
            embedding=make_embedding(3.0, 2.0),
        )

        results = retrieve_relevant_chunks(
            "Test question"
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(
            [result.content for result in results],
            [
                "Repeated content",
                "Unique content",
            ],
        )
