from django.contrib import admin, messages

from documents.models import Document
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