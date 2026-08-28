from django.contrib import admin, messages

from documents.models import Document, DocumentChunk
from documents.services.ingestion import process_document

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        file_changed = "file" in form.changed_data

        super().save_model(request, obj, form, change)

        if not change or file_changed:
            processed_document = process_document(obj.pk)
            obj.refresh_from_db()

            if processed_document.status == Document.Status.FAILED:
                self.message_user(
                    request,
                    processed_document.error_message,
                    level=messages.ERROR,
                )
    list_display = (
        "id",
        "title",
        "status",
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
        "full_text",
        "error_message",
        "checksum",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
    list_per_page = 50

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
                    "full_text",
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
        maximum_length = 100

        if len(obj.content) <= maximum_length:
            return obj.content

        return f"{obj.content[:maximum_length]}…"

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