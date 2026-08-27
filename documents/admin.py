from django.contrib import admin

from documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
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