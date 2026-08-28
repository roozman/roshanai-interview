from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from documents.models import Document, DocumentChunk


class DocumentAdminFeatureTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="document-admin-feature-user",
            password="test-password",
        )
        self.client.force_login(self.user)

        self.document = Document.objects.create(
            title="Indexed report",
            file="documents/admin-report.docx",
            full_text="Extracted report content.",
            status=Document.Status.INDEXED,
        )

        for index in range(2):
            DocumentChunk.objects.create(
                document=self.document,
                content=f"Chunk content {index}",
                chunk_index=index,
                start_offset=index * 20,
                end_offset=(index * 20) + 15,
                token_count=3,
            )

    def test_changelist_shows_status_and_chunk_count(
        self,
    ):
        response = self.client.get(
            reverse("admin:documents_document_changelist")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.document.title)
        self.assertContains(response, "Indexed")

        stored_document = (
            response.context["cl"].result_list[0]
        )

        self.assertEqual(
            stored_document._chunk_count,
            2,
        )

    def test_change_page_shows_safe_text_preview(self):
        self.document.full_text = (
            "<script>alert('unsafe')</script>"
            + ("A" * 2100)
        )
        self.document.save(update_fields=["full_text"])

        response = self.client.get(
            reverse(
                "admin:documents_document_change",
                args=[self.document.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>")
        self.assertContains(response, "…")

    def test_reindex_action_processes_selected_documents(
        self,
    ):
        failed_document = Document.objects.create(
            title="Failed report",
            file="documents/failed-report.docx",
            status=Document.Status.FAILED,
        )

        with patch(
            "documents.admin.process_document",
            side_effect=[
                SimpleNamespace(
                    status=Document.Status.INDEXED
                ),
                SimpleNamespace(
                    status=Document.Status.FAILED
                ),
            ],
        ) as mock_process_document:
            response = self.client.post(
                reverse(
                    "admin:documents_document_changelist"
                ),
                {
                    "action": (
                        "reindex_selected_documents"
                    ),
                    "_selected_action": [
                        self.document.pk,
                        failed_document.pk,
                    ],
                    "select_across": "0",
                    "index": "0",
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mock_process_document.call_count,
            2,
        )
        self.assertEqual(
            {
                call.args[0]
                for call
                in mock_process_document.call_args_list
            },
            {
                self.document.pk,
                failed_document.pk,
            },
        )
        self.assertContains(
            response,
            "1 document(s) were reindexed successfully.",
        )
        self.assertContains(
            response,
            "1 document(s) could not be reindexed.",
        )
