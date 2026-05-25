#!/usr/bin/env python3
"""Fix alembic version in database."""
import asyncio
import asyncpg
import os

async def fix_version():
    """Update the alembic version from old to new format."""
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/utcms_rpa")
    
    # Convert asyncpg URL format
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        # Check current version
        current = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"Current version: {current}")
        
        if current == "005_constraint_conflicts":
            await conn.execute(
                "UPDATE alembic_version SET version_num = '005_fix_constraint_conflicts' WHERE version_num = '005_constraint_conflicts'"
            )
            print("✅ Updated version to: 005_fix_constraint_conflicts")
        else:
            print(f"Version is already: {current}")
            
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_version())
