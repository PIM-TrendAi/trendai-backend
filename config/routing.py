"""
Django Channels routing — maps WebSocket paths to consumers.
"""
from django.urls import path
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from platforms.consumers import TikTokStatsConsumer

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter([
        path("ws/tiktok-stats/", TikTokStatsConsumer.as_asgi()),
    ]),
})
