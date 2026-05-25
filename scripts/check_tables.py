#!/usr/bin/env python3
"""Check which tables exist in database."""
import os
import psycopg2

def check_tables():
    """Check existing tables."""
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        database=os.getenv("POSTGRES_DB", "utcms_rpa"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres")
    )
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        print("📊 Existing tables:")
        for table in tables:
            print(f"  - {table[0]}")
            
    finally:
        conn.close()

if __name__ == "__main__":
    check_tables()
