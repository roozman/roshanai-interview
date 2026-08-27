from hashlib import sha256

from django.test import TestCase

from documents.models import Document
from documents.services.ingestion import process_document
from documents.tests.helpers import (
    TemporaryMediaRootMixin,
    build_docx_bytes,
    make_uploaded_docx,
)


class DocumentIngestionTests(
    TemporaryMediaRootMixin,
    TestCase,
):
    def test_extracts_paragraphs_and_tables(self):
        content = build_docx_bytes(
            paragraphs=("First   paragraph",),
            table_rows=(("Column A", "Column B"),),
        )

        document = Document.objects.create(
            title="Structured document",
            file=make_uploaded_docx(
                paragraphs=("First   paragraph",),
                table_rows=(("Column A", "Column B"),),
            ),
        )

        processed_document = process_document(document.pk)

        self.assertEqual(
            processed_document.status,
            Document.Status.PROCESSING,
        )
        self.assertEqual(
            processed_document.full_text,
            "First paragraph\nColumn A | Column B",
        )
        self.assertEqual(
            processed_document.checksum,
            sha256(content).hexdigest(),
        )
        self.assertEqual(processed_document.error_message, "")

    def test_marks_empty_docx_as_failed(self):
        document = Document.objects.create(
            title="Empty document",
            file=make_uploaded_docx(),
        )

        processed_document = process_document(document.pk)

        self.assertEqual(
            processed_document.status,
            Document.Status.FAILED,
        )
        self.assertEqual(processed_document.full_text, "")
        self.assertIn(
            "does not contain extractable text",
            processed_document.error_message,
        )
        self.assertEqual(len(processed_document.checksum), 64)