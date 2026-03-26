"""
ASGI config for TrendAI project.
Uses Django Channels for WebSocket support alongside standard HTTP.
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Import routing AFTER setting the env var so Django initialises correctly.
from config.routing import application  # noqa: E402, F401
