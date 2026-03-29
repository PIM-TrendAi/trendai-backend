"""
Root URL Configuration for TrendAI API.
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health(request):
    return JsonResponse({"status": "ok", "service": "trendai"})


urlpatterns = [
    path("api/health/", health),
    path("admin/", admin.site.urls),

    # API v1
    path("api/auth/", include("accounts.urls")),
    path("api/n8n/", include("n8n_integration.urls")),
    path("api/trends/", include("trends.urls")),
    path("api/scripts/", include("ai_scripts.urls")),
    path("api/analytics/", include("analytics.urls")),
    path("api/platforms/", include("platforms.urls")),

    # Swagger / OpenAPI docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
