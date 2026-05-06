import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from n8n_integration.models import CreatorSession

session_id = "1_1777219794494" # From the logs in the request
try:
    session = CreatorSession.objects.get(session_id=session_id)
    print(f"Session found: {session.session_id}, platform: {session.platform}, status: {session.status}")
except CreatorSession.DoesNotExist:
    print(f"Session {session_id} not found")

# Also list recent sessions
print("\nRecent sessions:")
for s in CreatorSession.objects.order_by('-created_at')[:5]:
    print(f"ID: {s.session_id}, platform: {s.platform}, status: {s.status}, created: {s.created_at}")
