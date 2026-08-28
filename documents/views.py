from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework.parsers import (
    FormParser,
    JSONParser,
    MultiPartParser,
)
from rest_framework.viewsets import ModelViewSet

from config.api.serializers import (
    ApiErrorResponseSerializer,
)
from documents.models import Document
from documents.serializers import (
    DocumentDetailSerializer,
    DocumentListSerializer,
)
from documents.services.ingestion import process_document


@extend_schema_view(
    list=extend_schema(
        tags=["Documents"],
        summary="List documents",
        description=(
            "Return a paginated list of uploaded documents. "
            "The extracted full text is omitted."
        ),
        responses={
            200: DocumentListSerializer(many=True),
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
        },
    ),
    retrieve=extend_schema(
        tags=["Documents"],
        summary="Retrieve a document",
        description=(
            "Return one document including its extracted "
            "full text and processing information."
        ),
        responses={
            200: DocumentDetailSerializer,
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
            404: ApiErrorResponseSerializer,
        },
    ),
    create=extend_schema(
        tags=["Documents"],
        summary="Upload and index a document",
        description=(
            "Upload a DOCX file, extract its text, split it "
            "into chunks, generate embeddings, and index it."
        ),
        request={
            "multipart/form-data": (
                DocumentDetailSerializer
            ),
        },
        responses={
            201: OpenApiResponse(
                response=DocumentDetailSerializer,
                description=(
                    "The uploaded and processed document."
                ),
            ),
            400: ApiErrorResponseSerializer,
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
            415: ApiErrorResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Document upload",
                value={
                    "title": "گزارش حلالیت",
                    "file": "solubility-report.docx",
                },
                request_only=True,
                media_type="multipart/form-data",
            ),
            OpenApiExample(
                "Indexed document",
                value={
                    "id": 4,
                    "title": "گزارش حلالیت",
                    "file": (
                        "/media/documents/2026/08/28/"
                        "solubility-report.docx"
                    ),
                    "full_text": (
                        "گزارش نهایی توسعه و ارزیابی "
                        "مدل پیش‌بینی حلالیت..."
                    ),
                    "status": "indexed",
                    "error_message": "",
                    "checksum": (
                        "d2a54f0b19c7e33a"
                        "127e50e234abc901"
                        "5a87021ad604e60f"
                        "9ec81ab70321e4ca"
                    ),
                    "created_at": (
                        "2026-08-28T10:00:00Z"
                    ),
                    "updated_at": (
                        "2026-08-28T10:00:04Z"
                    ),
                },
                response_only=True,
                status_codes=["201"],
            ),
            OpenApiExample(
                "Invalid document",
                value={
                    "error": {
                        "code": "validation_error",
                        "message": (
                            "Request validation failed."
                        ),
                        "details": {
                            "file": [
                                "Only valid DOCX files "
                                "are supported."
                            ]
                        },
                    }
                },
                response_only=True,
                status_codes=["400"],
            ),
        ],
    ),
    partial_update=extend_schema(
        tags=["Documents"],
        summary="Update a document",
        description=(
            "Update the title or replace the DOCX file. "
            "Replacing the file triggers re-indexing."
        ),
        request={
            "application/json": DocumentDetailSerializer,
            "multipart/form-data": (
                DocumentDetailSerializer
            ),
        },
        responses={
            200: DocumentDetailSerializer,
            400: ApiErrorResponseSerializer,
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
            404: ApiErrorResponseSerializer,
            415: ApiErrorResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Update title",
                value={
                    "title": "گزارش نهایی حلالیت",
                },
                request_only=True,
                media_type="application/json",
            ),
        ],
    ),
    destroy=extend_schema(
        tags=["Documents"],
        summary="Delete a document",
        description=(
            "Delete the document and all of its chunks. "
            "Stored historical question excerpts remain."
        ),
        responses={
            204: OpenApiResponse(
                response=None,
                description=(
                    "The document was deleted successfully."
                ),
            ),
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
            404: ApiErrorResponseSerializer,
        },
    ),
)
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