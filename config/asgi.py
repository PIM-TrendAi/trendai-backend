"""
ASGI config for TrendAI project.
Uses Django Channels for WebSocket support alongside standard HTTP.
"""

import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Import routing AFTER Django is initialised.
from config.routing import application  # noqa: E402, F401
