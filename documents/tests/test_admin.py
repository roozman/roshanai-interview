from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from documents.models import Document, DocumentChunk


class DocumentAdminDeletionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin-user",
            password="test-password",
        )
        self.client.force_login(self.user)

        self.document = Document.objects.create(
            title="Admin deletion test",
            file="documents/admin-delete.docx",
        )
        self.chunk = DocumentChunk.objects.create(
            document=self.document,
            content="Test chunk",
            chunk_index=0,
            start_offset=0,
            end_offset=10,
            token_count=2,
        )

    def test_document_deletion_cascades_to_chunks(self):
        document_id = self.document.pk
        chunk_id = self.chunk.pk

        response = self.client.post(
            reverse(
                "admin:documents_document_delete",
                args=[document_id],
            ),
            {"post": "yes"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Document.objects.filter(pk=document_id).exists()
        )
        self.assertFalse(
            DocumentChunk.objects.filter(pk=chunk_id).exists()
        )

    def test_direct_chunk_deletion_remains_forbidden(self):
        response = self.client.post(
            reverse(
                "admin:documents_documentchunk_delete",
                args=[self.chunk.pk],
            ),
            {"post": "yes"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            DocumentChunk.objects.filter(
                pk=self.chunk.pk
            ).exists()
        )