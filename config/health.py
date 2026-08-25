from django.db import DatabaseError, connections
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health_check(request: HttpRequest) -> JsonResponse:
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse(
            {
                "status": "unhealthy",
                "checks": {
                    "database": "unavailable",
                },
            },
            status=503,
        )

    return JsonResponse(
        {
            "status": "healthy",
            "checks": {
                "database": "available",
            },
        }
    )