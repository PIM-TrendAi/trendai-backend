"""
Fix orphaned threads_generated_videos rows:
- Row id=1 has video_url but session_id=None → link it to a real session
- Ensure all creator_sessions for threads have correct status
"""
import psycopg2

try:
    conn = psycopg2.connect(
        dbname='trendai_db', user='n8n', password='n8npassword',
        host='localhost', port='5433'
    )
    conn.autocommit = False
    cur = conn.cursor()

    print("=== BEFORE FIX ===")
    cur.execute("SELECT id, user_id, session_id, status, video_url FROM threads_generated_videos ORDER BY id DESC LIMIT 10;")
    for r in cur.fetchall():
        print(f"  id={r[0]} user_id={r[1]} session_id={r[2]} status={r[3]} has_video={bool(r[4])}")

    cur.execute("SELECT session_id, creator_id, platform, status FROM creator_sessions WHERE platform='threads' ORDER BY created_at DESC LIMIT 5;")
    sessions = cur.fetchall()
    print("\nCreator sessions:")
    for r in sessions:
        print(f"  {r[0]} creator={r[1]} platform={r[2]} status={r[3]}")

    # Fix 1: Update rows with session_id=None to link to latest threads session
    # by getting the latest creator_session for any user
    cur.execute("""
        UPDATE threads_generated_videos
        SET session_id = (
            SELECT session_id FROM creator_sessions
            WHERE platform = 'threads'
            ORDER BY created_at DESC
            LIMIT 1
        )
        WHERE session_id IS NULL
        RETURNING id, session_id
    """)
    updated = cur.fetchall()
    print(f"\nFixed {len(updated)} rows with NULL session_id: {updated}")

    # Fix 2: Ensure creator_sessions have correct status (not 'threads')
    cur.execute("""
        UPDATE creator_sessions
        SET status = 'script_generation'
        WHERE platform = 'threads' AND status = 'threads'
        RETURNING session_id
    """)
    fixed_status = cur.fetchall()
    print(f"Fixed {len(fixed_status)} sessions with wrong status: {fixed_status}")

    conn.commit()
    print("\n=== AFTER FIX ===")
    cur.execute("SELECT id, user_id, session_id, status, video_url FROM threads_generated_videos ORDER BY id DESC LIMIT 10;")
    for r in cur.fetchall():
        print(f"  id={r[0]} user_id={r[1]} session_id={r[2]} status={r[3]} has_video={bool(r[4])}")

    cur.close()
    conn.close()
    print("\nDone!")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
