from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin

from config.health import health_check
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health-check"),
    path("api/v1/", include("documents.urls")),
    path("api/v1/", include("qa.urls")),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
