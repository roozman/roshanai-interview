from django.db import models
from documents.validators import validate_docx_file
from pgvector.django import HalfVectorField, HnswIndex
from documents.constants import EMBEDDING_DIMENSION


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        INDEXED = "indexed", "Indexed"
        FAILED = "failed", "Failed"

    title = models.CharField(max_length=255)
    file = models.FileField(
        upload_to="documents/%Y/%m/%d/",
        validators=[validate_docx_file],
    )    
    full_text = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    error_message = models.TextField(blank=True)
    checksum = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

class DocumentChunk(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    content = models.TextField()
    chunk_index = models.PositiveIntegerField()
    start_offset = models.PositiveIntegerField()
    end_offset = models.PositiveIntegerField()
    token_count = models.PositiveIntegerField()
    embedding = HalfVectorField(
        dimensions=EMBEDDING_DIMENSION,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document_id", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="unique_document_chunk_index",
            ),
            models.CheckConstraint(
                condition=~models.Q(content=""),
                name="chunk_content_not_empty",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    end_offset__gt=models.F("start_offset"),
                ),
                name="chunk_offsets_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(token_count__gt=0),
                name="chunk_token_count_positive",
            ),
        ]
        indexes = [
            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["halfvec_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document.title} — chunk {self.chunk_index}"