import os
import sys
import django
from django.db import connection

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def check_posts():
    with connection.cursor() as cursor:
        print("Checking threads_posts table...")
        cursor.execute("SELECT post_id, username, niche FROM threads_posts ORDER BY created_at DESC LIMIT 5;")
        rows = cursor.fetchall()
        for row in rows:
            print(f"PostID: {row[0]}, username: {row[1]}, niche: {row[2]}")

if __name__ == "__main__":
    check_posts()
