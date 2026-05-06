"""
Migration: Add session_id column to threads_generated_videos
"""
import psycopg2

try:
    conn = psycopg2.connect(
        dbname='trendai_db',
        user='n8n',
        password='n8npassword',
        host='localhost',
        port='5433'
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Add session_id column
    cur.execute("""
        ALTER TABLE threads_generated_videos
        ADD COLUMN IF NOT EXISTS session_id TEXT;
    """)
    print("OK: session_id column added (or already existed).")

    # Create index for fast lookup
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_threads_gen_session_id
        ON threads_generated_videos(session_id);
    """)
    print("OK: index created.")

    # Show current columns
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'threads_generated_videos'
        ORDER BY ordinal_position;
    """)
    rows = cur.fetchall()
    print("Current columns in threads_generated_videos:")
    for r in rows:
        print(f"  - {r[0]}: {r[1]}")

    # Show existing rows
    cur.execute("SELECT id, post_id, user_id, status, video_url FROM threads_generated_videos ORDER BY id DESC LIMIT 5;")
    rows = cur.fetchall()
    print(f"\nLast {len(rows)} rows in threads_generated_videos:")
    for r in rows:
        print(f"  id={r[0]}, post_id={r[1]}, user_id={r[2]}, status={r[3]}, video_url={'YES' if r[4] else 'NULL'}")

    cur.close()
    conn.close()
    print("\nMigration completed successfully.")

except Exception as e:
    print(f"ERROR: {e}")
