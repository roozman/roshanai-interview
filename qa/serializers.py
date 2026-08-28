from rest_framework import serializers

from qa.constants import (
    QUESTION_DOCUMENT_FILTER_MAX_ITEMS,
    QUESTION_MAX_CHARACTERS,
)
from qa.models import QuestionAnswer, RetrievedChunk


class QuestionCreateSerializer(serializers.Serializer):
    question = serializers.CharField(
        max_length=QUESTION_MAX_CHARACTERS,
        trim_whitespace=True,
    )
    document_ids = serializers.ListField(
        child=serializers.IntegerField(
            min_value=1,
        ),
        required=False,
        allow_empty=True,
        max_length=QUESTION_DOCUMENT_FILTER_MAX_ITEMS,
    )

    def validate_document_ids(
        self,
        document_ids: list[int],
    ) -> list[int]:
        return list(dict.fromkeys(document_ids))


class RetrievedChunkSerializer(
    serializers.ModelSerializer
):
    document_id = serializers.SerializerMethodField()
    document_title = serializers.SerializerMethodField()
    chunk_id = serializers.IntegerField(
        read_only=True,
        allow_null=True,
    )
    score = serializers.FloatField(
        source="similarity_score",
        read_only=True,
    )

    class Meta:
        model = RetrievedChunk
        fields = (
            "document_id",
            "document_title",
            "chunk_id",
            "rank",
            "score",
            "excerpt",
        )
        read_only_fields = fields

    def get_document_id(
        self,
        retrieved_chunk: RetrievedChunk,
    ) -> int | None:
        if retrieved_chunk.chunk_id is None:
            return None

        return retrieved_chunk.chunk.document_id

    def get_document_title(
        self,
        retrieved_chunk: RetrievedChunk,
    ) -> str | None:
        if retrieved_chunk.chunk_id is None:
            return None

        return retrieved_chunk.chunk.document.title


class QuestionAnswerSerializer(
    serializers.ModelSerializer
):
    sources = RetrievedChunkSerializer(
        source="retrieved_chunks",
        many=True,
        read_only=True,
    )
    model = serializers.CharField(
        source="model_name",
        read_only=True,
    )

    class Meta:
        model = QuestionAnswer
        fields = (
            "id",
            "question",
            "answer",
            "status",
            "sources",
            "model",
            "latency_ms",
            "error_message",
            "created_at",
        )
        read_only_fields = fields
