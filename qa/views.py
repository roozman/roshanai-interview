from django.db.models import Prefetch
from rest_framework import mixins, status
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from qa.exceptions import QuestionProcessingUnavailable
from qa.models import QuestionAnswer, RetrievedChunk
from qa.serializers import (
    QuestionAnswerSerializer,
    QuestionCreateSerializer,
)
from qa.services.history import process_question
from qa.services.rag import RAGServiceError


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
