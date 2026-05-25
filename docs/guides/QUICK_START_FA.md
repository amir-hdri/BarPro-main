 # Quick Start Guide - UTCMS Automation System
 
 ## Prerequisites
 
 - Docker and Docker Compose
 - Python 3.11+ (for local backend)
 - Node.js 18+ (for local frontend)
 - PostgreSQL client tools (optional, for manual DB access)
 
 ## Installation
 
 ### 1. Clone and Setup
 
 ```bash
 git clone <repository-url>
 cd Automation-Barname-main
 
 # Copy environment file
 cp .env.example .env
 
 # Edit .env with your settings
 nano .env
 ```
 
 ### 2. Install Dependencies
 
 ```bash
 # Python dependencies
 pip install -r requirements.txt
 
 # Frontend dependencies
 cd apps/web
 yarn install
 cd ../..
 ```
 
 ### 3. Start the System
 
 ```bash
 # Start everything (infrastructure + backend + frontend)
 ./scripts/start_system.sh
 ```
 
 This will:
 - Pull and start Docker containers (PostgreSQL, Redis, Prometheus)
 - Initialize the database with migrations
 - Start the backend API on port 8000
 - Build and start the frontend on port 3000
 
 ## Access Points
 
 After successful startup:
 
 - **Frontend**: http://localhost:3000
 - **Backend API**: http://localhost:8000
 - **API Documentation**: http://localhost:8000/docs
 - **Prometheus**: http://localhost:9090
 
 ## Common Commands
 
 ### System Management
 
 ```bash
 # Start system
 ./scripts/start_system.sh
 
 # Stop system
 ./scripts/stop_system.sh
 
 # Check health
 ./scripts/check_health.sh
 
 # View logs
 ./scripts/view_logs.sh backend
 ./scripts/view_logs.sh frontend
 ./scripts/view_logs.sh follow  # Follow all logs
 ```
 
 ### Database Management
 
 ```bash
 # Initialize/migrate database
 python scripts/init_database.py
 
 # Reset database (DESTRUCTIVE - loses all data)
 ./scripts/reset_database.sh
 
 # Check migration status
 alembic current
 
 # Upgrade to latest
 alembic upgrade head
 
 # Downgrade one version
 alembic downgrade -1
 ```
 
 ### Docker Commands
 
 ```bash
 # View running containers
 docker compose ps
 
 # View logs
 docker compose logs -f postgres
 docker compose logs -f redis
 
 # Restart a service
 docker compose restart postgres
 
 # Stop all containers
 docker compose down
 
 # Stop and remove volumes (DESTRUCTIVE)
 docker compose down -v
 ```
 
 ## Troubleshooting
 
 ### Backend won't start
 
 1. Check if PostgreSQL is running:
    ```bash
    docker compose ps postgres
    ```
 
 2. Check backend logs:
    ```bash
    ./scripts/view_logs.sh backend
    ```
 
 3. Try database reset:
    ```bash
    ./scripts/reset_database.sh
    ./scripts/start_system.sh
    ```
 
 ### Frontend won't start
 
 1. Check if dependencies are installed:
    ```bash
    cd apps/web
    yarn install
    cd ../..
    ```
 
 2. Check frontend logs:
    ```bash
    ./scripts/view_logs.sh frontend
    ```
 
 3. Try manual build:
    ```bash
    cd apps/web
    yarn build
    yarn start
    ```
 
 ### Database migration errors
 
 If you see `DuplicateTableError` or constraint conflicts:
 
 ```bash
 # Option 1: Reset database (loses data)
 ./scripts/reset_database.sh
 
 # Option 2: Run fix migration
 alembic upgrade 005_fix_constraint_conflicts
 ```
 
 ### Port already in use
 
 If ports 3000, 8000, 5432, 6379, or 9090 are in use:
 
 ```bash
 # Find process using port
 lsof -i :8000
 
 # Kill process
 kill -9 <PID>
 
 # Or change port in .env
 nano .env
 ```
 
 ### Docker daemon not running
 
 ```bash
 # macOS
 open -a Docker
 
 # Linux
 sudo systemctl start docker
 ```
 
 ## Development Workflow
 
 ### Making Code Changes
 
 1. **Backend changes**:
    - Edit files in `app/`
    - Backend auto-reloads with uvicorn
    - Check logs: `./scripts/view_logs.sh backend`
 
 2. **Frontend changes**:
    - Edit files in `apps/web/`
    - Rebuild: `cd apps/web && yarn build`
    - Restart: `./scripts/stop_system.sh && ./scripts/start_system.sh`
 
 3. **Database schema changes**:
    ```bash
    # Create new migration
    alembic revision -m "description"
    
    # Edit migration file in alembic/versions/
    
    # Apply migration
    alembic upgrade head
    ```
 
 ### Running Tests
 
 ```bash
 # Backend tests
 pytest tests/
 
 # Frontend tests
 cd apps/web
 npm test
 ```
 
 ## Configuration
 
 Key environment variables in `.env`:
 
 ```bash
 # Database
 POSTGRES_PASSWORD=your_secure_password
 POSTGRES_DB=utcms_rpa
 DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/utcms_rpa
 
 # Redis
 REDIS_PASSWORD=your_redis_password
 REDIS_URL=redis://:password@localhost:6379/0
 
 # Security
 JWT_SECRET=your_jwt_secret_key
 API_KEY=your_api_key
 DRIVER_ENCRYPTION_KEY=your_encryption_key
 
 # UTCMS Credentials
 UTCMS_USERNAME=your_username
 UTCMS_PASSWORD=your_password
 
 # Features
 HEADLESS=true
 ALLOW_LIVE_SUBMIT=false
 LOG_LEVEL=INFO
 ```
 
 ## Production Deployment
 
 For production deployment:
 
 1. Use strong passwords in `.env`
 2. Set `HEADLESS=true`
 3. Set `ALLOW_LIVE_SUBMIT=true` only if needed
 4. Configure proper CORS in `FRONTEND_URL`
 5. Use reverse proxy (nginx) for SSL
 6. Set up database backups
 7. Configure monitoring and alerting
 
 See `deploy/` directory for deployment configurations.
 
 ## Architecture
 
 ```
 ┌─────────────┐
 │   Frontend  │ :3000
 │  (Next.js)  │
 └──────┬──────┘
        │
        ▼
 ┌─────────────┐
 │   Backend   │ :8000
 │  (FastAPI)  │
 └──────┬──────┘
        │
        ├──────► PostgreSQL :5432
        ├──────► Redis :6379
        └──────► Prometheus :9090
 ```
 
 ## Support
 
 - Documentation: See `docs/` directory
 - Issues: Check `FIXES_AND_OPTIMIZATIONS.md`
 - Logs: Use `./scripts/view_logs.sh`
 - Health: Use `./scripts/check_health.sh`
 
 ## License
 
 See LICENSE file for details.
