import os
import sys
import django

# Add the project root to sys.path
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

def fix_threads_table():
    with connection.cursor() as cursor:
        # Check if table exists
        cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'threads_generated_videos')")
        exists = cursor.fetchone()[0]
        print(f"Table threads_generated_videos exists: {exists}")
        
        if not exists:
            print("Creating table...")
            with open('threads_schema.sql', 'r') as f:
                # Split by semicolon to execute multiple statements
                sql = f.read()
                for statement in sql.split(';'):
                    if statement.strip():
                        cursor.execute(statement)
        
        # Check for session_id column
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'threads_generated_videos'")
        columns = [c[0] for c in cursor.fetchall()]
        print(f"Columns: {columns}")
        
        if 'session_id' not in columns:
            print("Adding session_id column...")
            cursor.execute("ALTER TABLE threads_generated_videos ADD COLUMN session_id TEXT")
        
        # Verify
        cursor.execute("SELECT * FROM threads_generated_videos ORDER BY id DESC LIMIT 5")
        rows = cursor.fetchall()
        print(f"Latest records: {rows}")

if __name__ == "__main__":
    fix_threads_table()
