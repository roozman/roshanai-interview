from django.db import IntegrityError, transaction
from django.test import TestCase

from documents.constants import EMBEDDING_DIMENSION
from documents.models import Document, DocumentChunk


class DocumentChunkModelTests(TestCase):
    def setUp(self):
        self.content = "این یک متن آزمایشی برای تست chunk است."

        self.document = Document.objects.create(
            title="Test document",
            file="documents/test.docx",
            full_text=self.content,
        )

    def create_chunk(self, chunk_index=0):
        return DocumentChunk.objects.create(
            document=self.document,
            content=self.content,
            chunk_index=chunk_index,
            start_offset=0,
            end_offset=len(self.content),
            token_count=9,
            embedding=[0.1] * EMBEDDING_DIMENSION,
        )

    def test_chunk_can_be_stored_and_retrieved(self):
        chunk = self.create_chunk()

        stored_chunk = DocumentChunk.objects.get(pk=chunk.pk)

        self.assertEqual(stored_chunk.content, self.content)
        self.assertEqual(
            len(stored_chunk.embedding),
            EMBEDDING_DIMENSION,
        )
        self.assertEqual(self.document.chunks.count(), 1)

    def test_chunks_are_deleted_with_document(self):
        chunk = self.create_chunk()
        chunk_id = chunk.pk

        self.document.delete()

        self.assertFalse(
            DocumentChunk.objects.filter(pk=chunk_id).exists()
        )

    def test_chunk_index_is_unique_per_document(self):
        self.create_chunk(chunk_index=0)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.create_chunk(chunk_index=0)