from rest_framework.parsers import (
    FormParser,
    JSONParser,
    MultiPartParser,
)
from rest_framework.viewsets import ModelViewSet

from documents.models import Document
from documents.serializers import (
    DocumentDetailSerializer,
    DocumentListSerializer,
)
from documents.services.ingestion import process_document


class DocumentViewSet(ModelViewSet):
    queryset = Document.objects.all()

    parser_classes = (
        JSONParser,
        FormParser,
        MultiPartParser,
    )

    http_method_names = (
        "get",
        "post",
        "patch",
        "delete",
        "head",
        "options",
    )

    def get_serializer_class(self):
        if self.action == "list":
            return DocumentListSerializer

        return DocumentDetailSerializer

    def perform_create(self, serializer):
        document = serializer.save()
        serializer.instance = process_document(document.pk)

    def perform_update(self, serializer):
        file_changed = "file" in serializer.validated_data
        document = serializer.save()

        if file_changed:
            serializer.instance = process_document(document.pk)