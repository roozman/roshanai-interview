from django.db import DatabaseError, connections
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
)
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from config.api.serializers import HealthResponseSerializer


@extend_schema(
    tags=["Health"],
    summary="Check service health",
    description=(
        "Check whether the API and its PostgreSQL database "
        "connection are available."
    ),
    auth=[],
    request=None,
    responses={
        200: OpenApiResponse(
            response=HealthResponseSerializer,
            description=(
                "The API and database are available."
            ),
        ),
        503: OpenApiResponse(
            response=HealthResponseSerializer,
            description=(
                "The database is currently unavailable."
            ),
        ),
    },
    examples=[
        OpenApiExample(
            "Healthy service",
            value={
                "status": "healthy",
                "checks": {
                    "database": "available",
                },
            },
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "Unavailable database",
            value={
                "status": "unhealthy",
                "checks": {
                    "database": "unavailable",
                },
            },
            response_only=True,
            status_codes=["503"],
        ),
    ],
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_check(request: Request) -> Response:
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return Response(
            {
                "status": "unhealthy",
                "checks": {
                    "database": "unavailable",
                },
            },
            status=503,
        )

    return Response(
        {
            "status": "healthy",
            "checks": {
                "database": "available",
            },
        }
    )