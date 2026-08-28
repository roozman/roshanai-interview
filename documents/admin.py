from django.contrib import admin, messages
from django.db.models import Count
from django.utils.html import format_html

from documents.models import Document, DocumentChunk
from documents.services.ingestion import process_document


FULL_TEXT_PREVIEW_MAX_CHARACTERS = 2000
CHUNK_CONTENT_PREVIEW_MAX_CHARACTERS = 100


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "status",
        "chunk_count",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "created_at",
    )
    search_fields = ("title",)
    readonly_fields = (
        "status",
        "full_text_preview",
        "chunk_count",
        "error_message",
        "checksum",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
    list_per_page = 50
    actions = ("reindex_selected_documents",)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "title",
                    "file",
                )
            },
        ),
        (
            "Processing",
            {
                "fields": (
                    "status",
                    "chunk_count",
                    "full_text_preview",
                    "error_message",
                    "checksum",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _chunk_count=Count("chunks")
        )

    def save_model(self, request, obj, form, change):
        file_changed = "file" in form.changed_data

        super().save_model(request, obj, form, change)

        if not change or file_changed:
            processed_document = process_document(obj.pk)
            obj.refresh_from_db()

            if (
                processed_document.status
                == Document.Status.FAILED
            ):
                self.message_user(
                    request,
                    processed_document.error_message,
                    level=messages.ERROR,
                )

    @admin.display(
        ordering="_chunk_count",
        description="Chunks",
    )
    def chunk_count(self, obj):
        if hasattr(obj, "_chunk_count"):
            return obj._chunk_count

        return obj.chunks.count()

    @admin.display(description="Extracted text preview")
    def full_text_preview(self, obj):
        if not obj or not obj.full_text:
            return "No extracted text is available."

        text = obj.full_text

        if len(text) > FULL_TEXT_PREVIEW_MAX_CHARACTERS:
            text = (
                text[:FULL_TEXT_PREVIEW_MAX_CHARACTERS]
                + "…"
            )

        return format_html(
            (
                '<pre style="white-space: pre-wrap; '
                'max-width: 80rem;">{}</pre>'
            ),
            text,
        )

    @admin.action(
        description="Reindex selected documents"
    )
    def reindex_selected_documents(
        self,
        request,
        queryset,
    ):
        document_ids = list(
            queryset.values_list("pk", flat=True)
        )
        indexed_count = 0
        failed_count = 0

        for document_id in document_ids:
            processed_document = process_document(
                document_id
            )

            if (
                processed_document.status
                == Document.Status.INDEXED
            ):
                indexed_count += 1
            else:
                failed_count += 1

        if indexed_count:
            self.message_user(
                request,
                (
                    f"{indexed_count} document(s) "
                    "were reindexed successfully."
                ),
                level=messages.SUCCESS,
            )

        if failed_count:
            self.message_user(
                request,
                (
                    f"{failed_count} document(s) "
                    "could not be reindexed."
                ),
                level=messages.WARNING,
            )

    def get_deleted_objects(self, objs, request):
        (
            deleted_objects,
            model_count,
            perms_needed,
            protected,
        ) = super().get_deleted_objects(
            objs,
            request,
        )

        perms_needed.discard(
            DocumentChunk._meta.verbose_name
        )

        return (
            deleted_objects,
            model_count,
            perms_needed,
            protected,
        )


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "document",
        "chunk_index",
        "token_count",
        "start_offset",
        "end_offset",
        "has_embedding",
        "content_preview",
        "created_at",
    )
    list_select_related = ("document",)
    search_fields = (
        "document__title",
        "content",
    )
    readonly_fields = (
        "document",
        "content",
        "chunk_index",
        "start_offset",
        "end_offset",
        "token_count",
        "embedding",
        "created_at",
    )
    ordering = (
        "document_id",
        "chunk_index",
    )
    list_per_page = 50

    @admin.display(
        boolean=True,
        description="Embedded",
    )
    def has_embedding(self, obj):
        return obj.embedding is not None

    @admin.display(description="Content")
    def content_preview(self, obj):
        if (
            len(obj.content)
            <= CHUNK_CONTENT_PREVIEW_MAX_CHARACTERS
        ):
            return obj.content

        return (
            obj.content[
                :CHUNK_CONTENT_PREVIEW_MAX_CHARACTERS
            ]
            + "…"
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False
