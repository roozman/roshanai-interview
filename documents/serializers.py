from rest_framework import serializers

from documents.models import Document


class DocumentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = (
            "id",
            "title",
            "file",
            "status",
            "checksum",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DocumentDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = (
            "id",
            "title",
            "file",
            "full_text",
            "status",
            "error_message",
            "checksum",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "full_text",
            "status",
            "error_message",
            "checksum",
            "created_at",
            "updated_at",
        )