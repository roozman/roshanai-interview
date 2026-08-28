from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework import status

from config.api.exceptions import api_exception_handler


class ApiExceptionHandlerTests(SimpleTestCase):
    @patch("config.api.exceptions.logger")
    def test_hides_unhandled_exception_details(
        self,
        mock_logger,
    ):
        exception = RuntimeError(
            "sensitive internal information"
        )

        response = api_exception_handler(
            exception,
            context={},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        self.assertEqual(
            response.data,
            {
                "error": {
                    "code": "internal_server_error",
                    "message": (
                        "An unexpected error occurred."
                    ),
                    "details": None,
                }
            },
        )
        self.assertNotIn(
            "sensitive internal information",
            str(response.data),
        )
        mock_logger.exception.assert_called_once_with(
            "Unhandled API exception.",
            exc_info=exception,
        )