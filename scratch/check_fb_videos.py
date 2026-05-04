import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

with connection.cursor() as cursor:
    cursor.execute("SELECT id, user_id, status, video_url FROM facebook_generated_videos ORDER BY id DESC LIMIT 5;")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
