"""
Root URL Configuration for TrendAI API.
"""
from django.contrib import admin
from django.http import JsonResponse, HttpResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views import View
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
import httpx


def health(request):
    return JsonResponse({"status": "ok", "service": "trendai"})


N8N_BASE = "http://localhost:5678"


class N8NProxyView(View):
    """Forward /webhook/* and /rest/* requests to n8n running on localhost:5678."""

    def dispatch(self, request, path="", prefix="", *args, **kwargs):
        url = f"{N8N_BASE}/{prefix}/{path}" if prefix else f"{N8N_BASE}/{path}"
        if request.META.get("QUERY_STRING"):
            url += f"?{request.META['QUERY_STRING']}"

        headers = {
            key[5:].replace("_", "-").title(): value
            for key, value in request.META.items()
            if key.startswith("HTTP_") and key != "HTTP_Host"
        }

        try:
            resp = httpx.request(
                method=request.method,
                url=url,
                headers=headers,
                content=request.body,
                follow_redirects=False,
                timeout=30.0,
            )
            response = HttpResponse(
                content=resp.content,
                status=resp.status_code,
                content_type=resp.headers.get("content-type", "application/octet-stream"),
            )
            for header in ["location", "set-cookie", "cache-control"]:
                if header in resp.headers:
                    response[header] = resp.headers[header]
            return response
        except Exception as e:
            return HttpResponse(f"Proxy error: {e}", status=502)


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

    # Proxy n8n webhooks and REST API through the same ngrok tunnel
    path("webhook/<path:path>", N8NProxyView.as_view(), {"prefix": "webhook"}, name="n8n-webhook-proxy"),
    path("rest/<path:path>", N8NProxyView.as_view(), {"prefix": "rest"}, name="n8n-rest-proxy"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
