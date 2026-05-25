#!/usr/bin/env python3
"""Fix alembic version in database using psycopg2."""
import psycopg2
import os

def fix_version():
    """Update the alembic version from old to new format."""
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        database=os.getenv("POSTGRES_DB", "utcms_rpa"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres")
    )
    
    try:
        cursor = conn.cursor()
        
        # Check current version
        cursor.execute("SELECT version_num FROM alembic_version")
        current = cursor.fetchone()[0]
        print(f"Current version: {current}")
        
        if current == "005_constraint_conflicts":
            cursor.execute(
                "UPDATE alembic_version SET version_num = '005_fix_constraint_conflicts' WHERE version_num = '005_constraint_conflicts'"
            )
            conn.commit()
            print("✅ Updated version to: 005_fix_constraint_conflicts")
        else:
            print(f"Version is already: {current}")
            
    finally:
        conn.close()

if __name__ == "__main__":
    fix_version()
