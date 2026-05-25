 #!/bin/bash
 # Reset PostgreSQL database for fresh migration
 
 set -e
 
 echo "🔄 Resetting PostgreSQL database..."
 
 # Load environment variables
 if [ -f .env ]; then
     export $(grep -v '^#' .env | xargs)
 fi
 
 POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
 POSTGRES_PORT="${POSTGRES_PORT:-5432}"
 POSTGRES_USER="${POSTGRES_USER:-postgres}"
 POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
 POSTGRES_DB="${POSTGRES_DB:-utcms_rpa}"
 
 echo "📋 Database: $POSTGRES_DB on $POSTGRES_HOST:$POSTGRES_PORT"
 
 # Drop and recreate database
 PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d postgres <<EOF
 DROP DATABASE IF EXISTS $POSTGRES_DB;
 CREATE DATABASE $POSTGRES_DB;
 EOF
 
 echo "✅ Database reset complete"
 echo "🔄 Running migrations..."
 
 # Run migrations
 python -m alembic upgrade head
 
 echo "✅ Migrations complete"
