from rest_framework import status
from rest_framework.exceptions import APIException


class QuestionProcessingUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        "Question processing is temporarily unavailable."
    )
    default_code = "question_processing_unavailable"
