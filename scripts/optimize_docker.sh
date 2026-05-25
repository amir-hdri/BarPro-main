#!/bin/bash

echo "🔧 Optimizing Docker Configuration..."
echo ""

# Create .dockerignore if not exists
cat > .dockerignore << 'DOCKERIGNORE'
# Git
.git
.gitignore
.gitattributes

# Python
__pycache__
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info
dist
build
.pytest_cache
.coverage
htmlcov

# Virtual environments
venv
env
ENV

# IDE
.vscode
.idea
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Documentation
*.md
docs/

# Tests
tests/
tests_backup_*.tar.gz

# CI/CD
.github
.gitlab-ci.yml

# Temporary files
*.tmp
*.log
.cache

# Node modules (for frontend)
node_modules
.next
out

# Environment files (should be mounted)
.env.local
.env.*.local

# Database files
*.db
*.sqlite
*.sqlite3

# Auth state
.auth/
DOCKERIGNORE

echo "✅ Created/Updated .dockerignore"
echo ""
echo "📊 Docker optimization tips:"
echo "  - Use multi-stage builds (already implemented)"
echo "  - Minimize layer count"
echo "  - Use .dockerignore to exclude unnecessary files"
echo "  - Cache dependencies separately from code"
echo ""
