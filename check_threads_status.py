"""
Debug: check all threads-related data in the DB to diagnose video display issue.
"""
import psycopg2

try:
    conn = psycopg2.connect(
        dbname='trendai_db', user='n8n', password='n8npassword',
        host='localhost', port='5433'
    )
    cur = conn.cursor()

    print("=" * 60)
    print("1. threads_generated_videos table")
    print("=" * 60)
    cur.execute("SELECT id, user_id, session_id, status, video_url, script_text FROM threads_generated_videos ORDER BY id DESC LIMIT 5;")
    rows = cur.fetchall()
    for r in rows:
        print(f"  id={r[0]}, user_id={r[1]}, session_id={r[2]}, status={r[3]}, video_url={'YES: '+str(r[4])[:80] if r[4] else 'NULL'}")
        if r[5]:
            print(f"    script_text={str(r[5])[:100]}...")

    print()
    print("=" * 60)
    print("2. creator_sessions for threads platform")
    print("=" * 60)
    cur.execute("SELECT session_id, creator_id, platform, status, selected_video_id, created_at FROM creator_sessions WHERE platform='threads' ORDER BY created_at DESC LIMIT 5;")
    rows = cur.fetchall()
    for r in rows:
        print(f"  session_id={r[0]}, creator_id={r[1]}, status={r[2]}, selected_video_id={r[4]}, created_at={r[5]}")

    print()
    print("=" * 60)
    print("3. generated_videos for threads sessions")
    print("=" * 60)
    cur.execute("""
        SELECT v.video_id, v.session_id, v.creator_id, v.video_url, v.status
        FROM generated_videos v
        WHERE v.session_id LIKE 'threads_%'
        ORDER BY v.created_at DESC LIMIT 5;
    """)
    rows = cur.fetchall()
    for r in rows:
        print(f"  video_id={r[0]}, session_id={r[1]}, creator_id={r[2]}, status={r[4]}, url={'YES: '+str(r[3])[:80] if r[3] else 'NULL'}")

    if not rows:
        print("  (no rows)")

    cur.close()
    conn.close()

except Exception as e:
    print(f"ERROR: {e}")
