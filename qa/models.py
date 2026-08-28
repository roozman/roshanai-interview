from django.db import models

from documents.models import DocumentChunk


class QuestionAnswer(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    question = models.TextField()
    answer = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PROCESSING,
        db_index=True,
    )

    model_name = models.CharField(
        max_length=255,
        blank=True,
    )
    latency_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.question[:80]


class RetrievedChunk(models.Model):
    question_answer = models.ForeignKey(
        QuestionAnswer,
        on_delete=models.CASCADE,
        related_name="retrieved_chunks",
    )
    chunk = models.ForeignKey(
        DocumentChunk,
        on_delete=models.SET_NULL,
        related_name="retrieval_records",
        null=True,
        blank=True,
    )

    rank = models.PositiveSmallIntegerField()
    similarity_score = models.FloatField()
    excerpt = models.TextField()

    class Meta:
        ordering = ["question_answer_id", "rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["question_answer", "rank"],
                name="unique_question_answer_rank",
            ),
            models.UniqueConstraint(
                fields=["question_answer", "chunk"],
                name="unique_question_answer_chunk",
            ),
            models.CheckConstraint(
                condition=models.Q(rank__gt=0),
                name="retrieved_chunk_rank_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(similarity_score__gte=-1.0)
                    & models.Q(similarity_score__lte=1.0)
                ),
                name="retrieved_chunk_score_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(excerpt=""),
                name="retrieved_chunk_excerpt_not_empty",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Question {self.question_answer_id} "
            f"— rank {self.rank}"
        )