import os
import sys
import django
from django.db import connection

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def check_threads():
    with connection.cursor() as cursor:
        print("Checking threads_generated_videos table...")
        try:
            cursor.execute("SELECT id, post_id, user_id, niche, status, script_text FROM threads_generated_videos ORDER BY id DESC LIMIT 5;")
            rows = cursor.fetchall()
            for row in rows:
                print(f"ID: {row[0]}, post_id: {row[1]}, user_id: {row[2]}, niche: {row[3]}, status: {row[4]}, script_len: {len(row[5]) if row[5] else 0}")
        except Exception as e:
            print(f"Error: {e}")

    from n8n_integration.models import CreatorSession
    print("\nRecent Threads sessions:")
    for s in CreatorSession.objects.filter(platform='threads').order_by('-created_at')[:5]:
        print(f"SessionID: {s.session_id}, user_id: {s.creator_id}, selected_video_id: {s.selected_video_id}, niche: {s.niche}")

if __name__ == "__main__":
    check_threads()
