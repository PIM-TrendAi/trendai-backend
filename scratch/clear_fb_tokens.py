import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from platforms.models import UserPlatform

# Clear all Facebook tokens in DB to force fallback to .env
updated = UserPlatform.objects.filter(platform_name="Facebook").update(access_token=None, connected=False)
print(f"Cleared Facebook tokens for {updated} users.")
