from django.contrib import admin
from django.db.models import Count

from qa.models import QuestionAnswer, RetrievedChunk


QUESTION_PREVIEW_MAX_CHARACTERS = 100
ANSWER_PREVIEW_MAX_CHARACTERS = 120
SOURCE_EXCERPT_PREVIEW_MAX_CHARACTERS = 300


class RetrievedChunkInline(admin.TabularInline):
    model = RetrievedChunk
    extra = 0
    can_delete = False
    show_change_link = False

    fields = (
        "rank",
        "document_title",
        "chunk",
        "similarity_score",
        "excerpt_preview",
    )
    readonly_fields = fields
    ordering = ("rank",)

    def get_queryset(self, request):
        return super().get_queryset(
            request
        ).select_related(
            "chunk__document"
        )

    @admin.display(description="Document")
    def document_title(self, obj):
        if obj.chunk_id is None:
            return "Deleted document"

        return obj.chunk.document.title

    @admin.display(description="Excerpt")
    def excerpt_preview(self, obj):
        if (
            len(obj.excerpt)
            <= SOURCE_EXCERPT_PREVIEW_MAX_CHARACTERS
        ):
            return obj.excerpt

        return (
            obj.excerpt[
                :SOURCE_EXCERPT_PREVIEW_MAX_CHARACTERS
            ]
            + "…"
        )

    def has_add_permission(
        self,
        request,
        obj=None,
    ):
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


@admin.register(QuestionAnswer)
class QuestionAnswerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "question_preview",
        "answer_preview",
        "status",
        "model_name",
        "latency_ms",
        "source_count",
        "created_at",
    )
    list_filter = (
        "status",
        "model_name",
        "created_at",
    )
    search_fields = (
        "question",
        "answer",
        "error_message",
    )
    readonly_fields = (
        "question",
        "answer",
        "status",
        "model_name",
        "latency_ms",
        "error_message",
        "created_at",
    )
    inlines = (RetrievedChunkInline,)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50

    fieldsets = (
        (
            "Question and answer",
            {
                "fields": (
                    "question",
                    "answer",
                    "status",
                )
            },
        ),
        (
            "Execution",
            {
                "fields": (
                    "model_name",
                    "latency_ms",
                    "error_message",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                )
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _source_count=Count("retrieved_chunks")
        )

    @admin.display(description="Question")
    def question_preview(self, obj):
        if (
            len(obj.question)
            <= QUESTION_PREVIEW_MAX_CHARACTERS
        ):
            return obj.question

        return (
            obj.question[
                :QUESTION_PREVIEW_MAX_CHARACTERS
            ]
            + "…"
        )

    @admin.display(description="Answer")
    def answer_preview(self, obj):
        if (
            len(obj.answer)
            <= ANSWER_PREVIEW_MAX_CHARACTERS
        ):
            return obj.answer

        return (
            obj.answer[
                :ANSWER_PREVIEW_MAX_CHARACTERS
            ]
            + "…"
        )

    @admin.display(
        ordering="_source_count",
        description="Sources",
    )
    def source_count(self, obj):
        if hasattr(obj, "_source_count"):
            return obj._source_count

        return obj.retrieved_chunks.count()

    def has_add_permission(self, request):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False
