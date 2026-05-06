import os
import sys
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from platforms.models import UserPlatform

User = get_user_model()
email = 'messaoudmay6@gmail.com'
token = 'EAAXy6xhiyMABRRMqsBVVSsxm3AaXvBALUev4nZBbmJHIeyApP4XvGLQnAtQX1wRCZBv6axMl884ZBYiSxLcNAPncrEO3NDTjnO8AeB9ZBGJl19jIFebWQLQFuDqWzp5OPHkPIdZACE0quHcaZBaVSv6DsvK6Q6Ub8jyk1LjZCt9n3rPgMGMk19jT7VrC7ckICZAzYdaO5UqHvMXLjc6l3cgQSeDLnZCFp4Fn1yZCHt8xlntRVmwDLmiDTawCM2XZC12'

user, created = User.objects.get_or_create(email=email, defaults={'name': 'Messaoud May'})
if created:
    user.set_password('trendai2026')
    user.save()
    print(f"Created user: {email}")
else:
    print(f"User already exists: {email}")

platform, _ = UserPlatform.objects.get_or_create(user=user, platform_name='Facebook')
platform.access_token = token
platform.connected = True
platform.save()
print("Successfully updated platform database.")
