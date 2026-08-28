from django.db.models import Prefetch
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import mixins, status
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from config.api.serializers import (
    ApiErrorResponseSerializer,
)
from qa.exceptions import QuestionProcessingUnavailable
from qa.models import QuestionAnswer, RetrievedChunk
from qa.serializers import (
    QuestionAnswerSerializer,
    QuestionCreateSerializer,
)
from qa.services.history import process_question
from qa.services.rag import RAGServiceError


@extend_schema_view(
    list=extend_schema(
        tags=["Questions"],
        summary="List question-answer history",
        description=(
            "Return the paginated question-answer history."
        ),
        responses={
            200: QuestionAnswerSerializer(many=True),
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
        },
    ),
    retrieve=extend_schema(
        tags=["Questions"],
        summary="Retrieve a question answer",
        description=(
            "Return one stored answer together with its "
            "retrieved source chunks."
        ),
        responses={
            200: QuestionAnswerSerializer,
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
            404: ApiErrorResponseSerializer,
        },
    ),
    create=extend_schema(
        tags=["Questions"],
        summary="Ask a question",
        description=(
            "Retrieve relevant chunks and generate an "
            "answer using the configured OpenRouter model."
        ),
        request=QuestionCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=QuestionAnswerSerializer,
                description=(
                    "The generated answer and its sources."
                ),
            ),
            400: ApiErrorResponseSerializer,
            401: ApiErrorResponseSerializer,
            403: ApiErrorResponseSerializer,
            503: OpenApiResponse(
                response=ApiErrorResponseSerializer,
                description=(
                    "Question processing is temporarily "
                    "unavailable."
                ),
            ),
        },
        examples=[
            OpenApiExample(
                "Question request",
                value={
                    "question": (
                        "عملکرد مدل جنگل تصادفی "
                        "در آزمون نهایی چقدر بود؟"
                    ),
                    "document_ids": [4],
                },
                request_only=True,
            ),
            OpenApiExample(
                "Successful answer",
                value={
                    "id": 12,
                    "question": (
                        "عملکرد مدل جنگل تصادفی "
                        "در آزمون نهایی چقدر بود؟"
                    ),
                    "answer": (
                        "مقادیر RMSE، MAE و R² به‌ترتیب "
                        "۱٫۱۱۵، ۰٫۷۵۳ و ۰٫۷۷۷ بودند. "
                        "[Source 1]"
                    ),
                    "status": "completed",
                    "sources": [
                        {
                            "document_id": 4,
                            "document_title": "حلالیت",
                            "chunk_id": 17,
                            "rank": 1,
                            "score": 0.6473,
                            "excerpt": (
                                "عملکرد نهایی مدل..."
                            ),
                        }
                    ],
                    "model": (
                        "nvidia/"
                        "nemotron-3-super-120b-a12b:free"
                    ),
                    "latency_ms": 1250,
                    "error_message": "",
                    "created_at": (
                        "2026-08-28T10:30:00Z"
                    ),
                },
                response_only=True,
                status_codes=["201"],
            ),
            OpenApiExample(
                "Validation error",
                value={
                    "error": {
                        "code": "validation_error",
                        "message": (
                            "Request validation failed."
                        ),
                        "details": {
                            "question": [
                                "This field is required."
                            ]
                        },
                    }
                },
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "Processing unavailable",
                value={
                    "error": {
                        "code": (
                            "question_processing_unavailable"
                        ),
                        "message": (
                            "Question processing is "
                            "temporarily unavailable."
                        ),
                        "details": None,
                    }
                },
                response_only=True,
                status_codes=["503"],
            ),
        ],
    ),
)
class QuestionAnswerViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    queryset = QuestionAnswer.objects.prefetch_related(
        Prefetch(
            "retrieved_chunks",
            queryset=RetrievedChunk.objects.select_related(
                "chunk__document"
            ),
        )
    )

    http_method_names = (
        "get",
        "post",
        "head",
        "options",
    )

    def get_serializer_class(self):
        if self.action == "create":
            return QuestionCreateSerializer

        return QuestionAnswerSerializer

    def create(self, request, *args, **kwargs):
        input_serializer = self.get_serializer(
            data=request.data
        )
        input_serializer.is_valid(raise_exception=True)

        validated_data = input_serializer.validated_data

        try:
            question_answer = process_question(
                validated_data["question"],
                document_ids=validated_data.get(
                    "document_ids"
                ),
            )
        except RAGServiceError as exc:
            raise QuestionProcessingUnavailable() from exc

        stored_question_answer = self.get_queryset().get(
            pk=question_answer.pk
        )

        output_serializer = QuestionAnswerSerializer(
            stored_question_answer,
            context=self.get_serializer_context(),
        )

        return Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED,
        )
