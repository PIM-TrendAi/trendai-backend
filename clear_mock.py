import psycopg2

try:
    conn = psycopg2.connect(
        dbname='trendai_db', user='n8n', password='n8npassword',
        host='localhost', port='5433'
    )
    conn.autocommit = True
    cur = conn.cursor()

    print("Deleting mock videos...")
    cur.execute("DELETE FROM threads_generated_videos WHERE video_url LIKE '%w3schools%' OR video_url IS NULL;")
    print(f"Deleted {cur.rowcount} rows.")

    cur.close()
    conn.close()
    print("Done!")

except Exception as e:
    print(f"ERROR: {e}")
