# Fixes Applied - Frontend Build & Backend Startup Issues

## Problems Fixed

### 1. Frontend Build Failure
**Issue**: `env: node: No such file or directory`

**Root Cause**: Node.js was installed at `/opt/node/bin/` but not in the system PATH.

**Solution**: 
- Updated `scripts/start_system.sh` to prioritize `/opt/node/bin/` when detecting Node.js
- Added `export PATH="/opt/node/bin:$PATH"` before running npm commands

### 2. Backend Startup Hang
**Issue**: Backend would start but hang during database migration, never becoming responsive.

**Root Cause**: Alembic's `env.py` uses `asyncio.run()` internally, which conflicts when called from within an already-running async context using `asyncio.to_thread()`.

**Solution**: 
- Modified `app/core/database.py` to skip migrations during app startup
- Migrations are now run separately via `scripts/init_database.py` before starting the backend
- This prevents the event loop conflict

### 3. Process Persistence Issues
**Issue**: Services started with `nohup` would exit immediately when the parent shell closed.

**Solution**: 
- Added `</dev/null` to stdin redirection for proper backgrounding
- Created standalone wrapper scripts (`scripts/start_backend.sh`, `scripts/start_frontend.sh`)
- Created `start_services.sh` for easy manual startup

## Files Modified

1. `scripts/start_system.sh` - Fixed Node.js PATH and process backgrounding
2. `app/core/database.py` - Skipped migrations during startup to avoid async conflicts
3. `scripts/start_backend.sh` (new) - Standalone backend starter
4. `scripts/start_frontend.sh` (new) - Standalone frontend starter
5. `start_services.sh` (new) - Simple wrapper for manual startup

## How to Start the System

### Option 1: Using the main script (recommended for Docker environments)
```bash
./scripts/start_system.sh
```

### Option 2: Manual startup (if automated script has issues)
```bash
# Start Docker services
docker compose up -d postgres redis prometheus

# Start backend and frontend
./start_services.sh
```

### Option 3: Individual service control
```bash
# Backend only
./scripts/start_backend.sh > output/backend.log 2>&1 &

# Frontend only (after backend is running)
./scripts/start_frontend.sh > output/frontend.log 2>&1 &
```

## Verification

Check if services are running:
```bash
# Check processes
ps -p $(cat output/backend.pid) -p $(cat output/frontend.pid)

# Test endpoints
curl http://localhost:8000/docs
curl http://localhost:3000
```

## Stopping Services

```bash
./scripts/stop_system.sh
```

Or manually:
```bash
pkill -F output/backend.pid
pkill -F output/frontend.pid
docker compose down
```

## Notes

- Database migrations are run automatically by `scripts/init_database.py` before backend starts
- Frontend build happens once during startup and uses the production build
- All logs are saved to `output/backend.log` and `output/frontend.log`
- Process IDs are saved to `output/backend.pid` and `output/frontend.pid`
