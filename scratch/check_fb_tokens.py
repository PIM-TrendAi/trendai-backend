import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from platforms.models import UserPlatform
from django.contrib.auth import get_user_model

User = get_user_model()
users = User.objects.all()

print(f"Checking {users.count()} users...")
for user in users:
    try:
        platform = UserPlatform.objects.get(user=user, platform_name="Facebook")
        token_preview = platform.access_token[:20] if platform.access_token else "None"
        print(f"User: {user.email}, Platform: {platform.platform_name}, Connected: {platform.connected}, Token: {token_preview}...")
        
        # If we want to force fallback to .env, we can set connected=False or access_token=None
        # platform.connected = False
        # platform.access_token = None
        # platform.save()
    except UserPlatform.DoesNotExist:
        print(f"User: {user.email}, No Facebook platform entry.")
