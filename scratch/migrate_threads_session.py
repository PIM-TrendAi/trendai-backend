import os
import sys
import django
from django.db import connection

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def add_session_id():
    with connection.cursor() as cursor:
        print("Adding session_id column to threads_generated_videos...")
        try:
            cursor.execute("ALTER TABLE threads_generated_videos ADD COLUMN IF NOT EXISTS session_id TEXT;")
            print("Done.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    add_session_id()
