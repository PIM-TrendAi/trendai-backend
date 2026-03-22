import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv

load_dotenv()

try:
    con = psycopg2.connect(
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "n8npassword"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432")
    )
    con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = con.cursor()
    cursor.execute(f"CREATE DATABASE {os.getenv('DB_NAME', 'trendai_db')};")
    print(f"Database created successfully.")
except psycopg2.errors.DuplicateDatabase:
    print("Database already exists.")
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'con' in locals() and con:
        cursor.close()
        con.close()
