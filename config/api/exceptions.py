import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import (
    exception_handler as drf_exception_handler,
)


logger = logging.getLogger(__name__)

STATUS_CODE_TO_ERROR_CODE = {
    400: "bad_request",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    415: "unsupported_media_type",
    429: "throttled",
}


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is None:
        logger.exception(
            "Unhandled API exception.",
            exc_info=exc,
        )

        return Response(
            {
                "error": {
                    "code": "internal_server_error",
                    "message": (
                        "An unexpected error occurred."
                    ),
                    "details": None,
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    original_data = response.data

    if (
        isinstance(original_data, dict)
        and set(original_data) == {"detail"}
    ):
        detail = original_data["detail"]
        code = getattr(
            detail,
            "code",
            STATUS_CODE_TO_ERROR_CODE.get(
                response.status_code,
                "request_error",
            ),
        )
        message = str(detail)
        details = None

    else:
        code = (
            "validation_error"
            if response.status_code == 400
            else STATUS_CODE_TO_ERROR_CODE.get(
                response.status_code,
                "request_error",
            )
        )
        message = (
            "Request validation failed."
            if response.status_code == 400
            else "The request could not be completed."
        )
        details = original_data

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }

    return response