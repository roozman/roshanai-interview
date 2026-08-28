from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from documents.models import Document
from documents.tests.helpers import (
    DOCX_CONTENT_TYPE,
    TemporaryMediaRootMixin,
    make_uploaded_docx,
)

from unittest.mock import patch
from documents.tests.helpers import (
    DOCX_CONTENT_TYPE,
    TemporaryMediaRootMixin,
    build_test_embeddings,
    make_uploaded_docx,
)


class DocumentAPITests(
    TemporaryMediaRootMixin,
    APITestCase,
):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(
            username="api-user",
            password="test-password",
        )
        self.client.force_authenticate(user=self.user)
        self.list_url = reverse("document-list")
        self.embedding_patcher = patch(
            "documents.services.embeddings."
            "generate_document_embeddings",
            side_effect=build_test_embeddings,
        )
        self.embedding_patcher.start()
        self.addCleanup(self.embedding_patcher.stop)

    def upload_document(
        self,
        title: str = "Test document",
        text: str = "Document body",
    ):
        return self.client.post(
            self.list_url,
            {
                "title": title,
                "file": make_uploaded_docx(
                    paragraphs=(text,),
                ),
            },
            format="multipart",
        )

    def test_uploads_and_extracts_valid_docx(self):
        response = self.upload_document(
            title="Contract",
            text="Termination conditions",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        document = Document.objects.get(pk=response.data["id"])

        self.assertEqual(document.title, "Contract")
        self.assertEqual(
            document.full_text,
            "Termination conditions",
        )
        self.assertEqual(len(document.checksum), 64)
        self.assertEqual(
            document.status,
            Document.Status.INDEXED,
        )

    def test_rejects_non_docx_file(self):
        invalid_file = SimpleUploadedFile(
            name="notes.txt",
            content=b"plain text",
            content_type="text/plain",
        )

        response = self.client.post(
            self.list_url,
            {
                "title": "Invalid document",
                "file": invalid_file,
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data["error"]["code"],
            "validation_error",
        )
        self.assertIn(
            "file",
            response.data["error"]["details"],
        )
        self.assertFalse(Document.objects.exists())

    def test_rejects_corrupted_docx(self):
        corrupted_file = SimpleUploadedFile(
            name="corrupted.docx",
            content=b"this is not a zip archive",
            content_type=DOCX_CONTENT_TYPE,
        )

        response = self.client.post(
            self.list_url,
            {
                "title": "Corrupted document",
                "file": corrupted_file,
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "file",
            response.data["error"]["details"],
        )
        self.assertFalse(Document.objects.exists())

    def test_lists_documents_without_full_text(self):
        create_response = self.upload_document()
        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
        )

        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(response.data["count"], 1)
        self.assertNotIn(
            "full_text",
            response.data["results"][0],
        )

    def test_retrieves_document_with_full_text(self):
        create_response = self.upload_document(
            text="Detailed content",
        )
        detail_url = reverse(
            "document-detail",
            args=[create_response.data["id"]],
        )

        response = self.client.get(detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["full_text"],
            "Detailed content",
        )

    def test_patches_title_without_reprocessing_file(self):
        create_response = self.upload_document(
            text="Original content",
        )
        document_id = create_response.data["id"]
        document = Document.objects.get(pk=document_id)
        original_checksum = document.checksum

        detail_url = reverse(
            "document-detail",
            args=[document_id],
        )

        response = self.client.patch(
            detail_url,
            {"title": "Updated title"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        document.refresh_from_db()

        self.assertEqual(document.title, "Updated title")
        self.assertEqual(document.checksum, original_checksum)
        self.assertEqual(
            document.full_text,
            "Original content",
        )

    def test_reprocesses_document_when_file_changes(self):
        create_response = self.upload_document(
            text="Original content",
        )
        document_id = create_response.data["id"]
        document = Document.objects.get(pk=document_id)
        original_checksum = document.checksum

        detail_url = reverse(
            "document-detail",
            args=[document_id],
        )

        response = self.client.patch(
            detail_url,
            {
                "file": make_uploaded_docx(
                    name="replacement.docx",
                    paragraphs=("Replacement content",),
                )
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        document.refresh_from_db()

        self.assertEqual(
            document.full_text,
            "Replacement content",
        )
        self.assertNotEqual(
            document.checksum,
            original_checksum,
        )

    def test_deletes_document(self):
        create_response = self.upload_document()
        document_id = create_response.data["id"]

        detail_url = reverse(
            "document-detail",
            args=[document_id],
        )

        response = self.client.delete(detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(
            Document.objects.filter(pk=document_id).exists()
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