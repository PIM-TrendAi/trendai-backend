import os
import django
import sys

# Add the project directory to sys.path
sys.path.append('/Users/apple/Desktop/PIM 2/trendai-backend')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connections

def list_tables(db):
    print(f"\nTables in {db}:")
    try:
        with connections[db].cursor() as cursor:
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = cursor.fetchall()
            for t in tables:
                print(f"- {t[0]}")
    except Exception as e:
        print(f"Error listing tables in {db}: {e}")

list_tables('default')
list_tables('n8n')

def inspect_threads(db):
    print(f"\nInspecting threads_generated_videos in {db}...")
    try:
        with connections[db].cursor() as cursor:
            cursor.execute("SELECT * FROM threads_generated_videos ORDER BY id DESC LIMIT 5")
            rows = cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            for row in rows:
                print(dict(zip(columns, row)))
    except Exception as e:
        print(f"Error inspecting threads in {db}: {e}")

inspect_threads('default')
inspect_threads('n8n')
