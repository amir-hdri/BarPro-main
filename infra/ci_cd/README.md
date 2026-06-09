# CI/CD Pipeline for BarPro

This directory contains CI/CD configuration and documentation for the BarPro application.

## Overview

The BarPro project uses **GitHub Actions** for Continuous Integration and Continuous Deployment. The pipeline includes:

- **Code Quality Checks** - Linting, formatting, type checking
- **Unit & Integration Tests** - Backend and frontend testing
- **Security Scanning** - Dependency auditing, vulnerability scanning
- **Docker Image Building** - Multi-architecture container builds
- **Deployment** - Automated deployment to staging and production
- **Load Testing** - Performance validation

## Directory Structure

```
.github/
└── workflows/
    ├── ci-test.yml          # CI: Tests and validation
    ├── cd-deploy.yml         # CD: Build and deployment
    ├── ci-cd.yml            # Combined CI/CD pipeline
    └── dependency-submission.yml  # Dependency management
```

## Workflows

### 1. CI - Test & Validate (`ci-test.yml`)

**Trigger**: Push or PR to `main` or `develop` branches

**Jobs**:
- ✅ Backend Tests (Python)
- ✅ Frontend Tests (Node.js)
- ✅ Integration Tests
- ✅ Security Scan (Bandit, Safety, pip-audit)

**Features**:
- PostgreSQL and Redis service containers
- Test coverage reporting
- Parallel test execution
- Artifact upload (coverage reports)

### 2. CD - Build & Deploy (`cd-deploy.yml`)

**Trigger**:
- Push to `main` branch
- Tag push (e.g., `v1.0.0`)
- Manual workflow dispatch

**Jobs**:
- 🐳 Build Backend Docker Image
- 🐳 Build Frontend Docker Image
- 🚀 Deploy to Staging
- 🚀 Deploy to Production (manual approval)
- 📧 Deployment Notification

**Features**:
- Docker Buildx with caching
- Multi-tag Docker images
- SSH-based deployment to servers
- Manual approval for production
- Environment-based configuration

### 3. Combined CI/CD (`ci-cd.yml`)

**Trigger**: Push or PR to `main`, `develop`, or `feature/*` branches

**Jobs**:
- ✅ Quality Checks (linting, formatting)
- ✅ Unit Tests
- 🐳 Docker Image Building
- 🚀 Deploy to Staging
- 📊 Load Testing (on staging)

**Features**:
- End-to-end validation
- Load testing after deployment
- Artifact collection (reports)

### 4. Dependency Submission (`dependency-submission.yml`)

**Trigger**: Weekly (Sunday) or on push/PR to `main`

**Jobs**:
- 📦 Generate dependency snapshot
- 🔒 Security audit (pip-audit)
- 📋 Generate SBOM (CycloneDX)

**Features**:
- Dependency tracking
- Vulnerability detection
- SBOM generation for compliance

## Setup

### Prerequisites

1. **GitHub Repository** with Actions enabled
2. **GitHub Secrets** configured (see below)
3. **Docker** installed on build runners
4. **Python 3.11** and **Node.js 20**

### Required GitHub Secrets

Create these secrets in your GitHub repository settings:

| Secret Name | Description | Required |
|-------------|-------------|----------|
| `DOCKER_USERNAME` | Docker Hub username | ✅ For pushing images |
| `DOCKER_PASSWORD` | Docker Hub password/token | ✅ For pushing images |
| `STAGING_HOST` | Staging server hostname/IP | ✅ For deployment |
| `STAGING_USERNAME` | Staging SSH username | ✅ For deployment |
| `STAGING_SSH_KEY` | Staging SSH private key | ✅ For deployment |
| `STAGING_PORT` | Staging SSH port | ❌ (default: 22) |
| `PRODUCTION_HOST` | Production server hostname/IP | ✅ For production |
| `PRODUCTION_USERNAME` | Production SSH username | ✅ For production |
| `PRODUCTION_SSH_KEY` | Production SSH private key | ✅ For production |
| `PRODUCTION_PORT` | Production SSH port | ❌ (default: 22) |
| `SLACK_WEBHOOK` | Slack webhook URL | ❌ For notifications |

### Environment Variables

Configure these in your repository or workflow files:

| Variable | Description | Default |
|----------|-------------|---------|
| `PYTHON_VERSION` | Python version | `3.11` |
| `NODE_VERSION` | Node.js version | `20` |
| `REGISTRY` | Container registry | `ghcr.io` |
| `IMAGE_NAME` | Docker image name | `barpro` |

## Usage

### Trigger CI Tests

```bash
# Push to main/develop triggers CI automatically
 git push origin main

# Or manually trigger via GitHub UI
```

### Trigger Deployment

```bash
# Push to main triggers staging deployment
 git push origin main

# Tag push triggers production deployment (with approval)
 git tag v1.0.0
 git push origin v1.0.0

# Manual dispatch via GitHub Actions UI
```

### View Workflow Results

1. Go to your repository on GitHub
2. Click on "Actions" tab
3. Select the workflow run
4. View logs and artifacts

## Customization

### Modify Test Configuration

Edit `.github/workflows/ci-test.yml`:

```yaml
jobs:
  backend-test:
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
        
  test:
    env:
      DATABASE_URL: postgresql+asyncpg://user:pass@localhost/db
```

### Modify Deployment Configuration

Edit `.github/workflows/cd-deploy.yml`:

```yaml
env:
  REGISTRY: "docker.io"
  IMAGE_NAME: "my-company/barpro"

jobs:
  deploy-production:
    if: github.ref == 'refs/tags/v*'
```

### Add New Test Suites

Add new test jobs to any workflow:

```yaml
api-test:
  name: API Tests
  runs-on: ubuntu-latest
  steps:
    - name: Run API Tests
      run: |
        pytest tests/api/ -v
```

## Best Practices

### 1. Branch Strategy

```
main     → Production ready code
        → Tags: v1.0.0, v2.0.0 (production releases)
        
 develop → Integration branch
        → Feature branches merged here
        
 feature/* → Individual feature development
        → PR to develop for review
```

### 2. Deployment Flow

```
Code → Push to feature branch → PR to develop → Merge to develop → Test → Push to main → Deploy to staging → Manual approval → Deploy to production
```

### 3. Testing Strategy

| Test Type | When | Where | Purpose |
|-----------|------|-------|---------|
| Unit Tests | Every commit | CI | Code correctness |
| Integration Tests | PR to main/develop | CI | Component interaction |
| Security Scan | Every commit | CI | Vulnerability detection |
| Load Tests | After staging deploy | CI/CD | Performance validation |
| Manual Tests | Before production | Manual | User acceptance |

### 4. Rollback Strategy

1. **Automatic Rollback** - Health checks fail, container restarts
2. **Manual Rollback** - SSH to server, revert to previous tag
3. **Database Rollback** - Alembic downgrade migrations

## Monitoring

### Workflow Monitoring

- **GitHub Actions UI** - View real-time workflow execution
- **Workflow Logs** - Debug failed steps
- **Artifacts** - Download test reports, coverage reports

### Deployment Monitoring

Add health checks to your deployment:

```bash
# Check service status
curl -f http://localhost:8000/healthz

# Check database
psql -h localhost -U postgres -c "SELECT 1"

# Check Redis
redis-cli ping

# Check Docker containers
docker-compose ps
```

## Troubleshooting

### Common Issues

#### 1. Workflow Permission Denied

**Solution**: Ensure repository settings allow Actions to run:
```
Settings → Actions → General → Workflow permissions: Read and write
```

#### 2. Docker Build Fails

**Solution**: Check Dockerfile syntax and dependencies:
```bash
# Test Docker build locally
docker build -t barpro-backend .
```

#### 3. Dependency Installation Fails

**Solution**: Update requirements files:
```bash
# Update dependencies
pip install --upgrade -r requirements.txt

# Freeze versions
pip freeze > requirements.txt
```

#### 4. Test Fails in CI but Passes Locally

**Solution**: Check environment differences:
- Python version
- Package versions
- Database connection
- Environment variables

#### 5. Deployment Connection Refused

**Solution**: Verify deployment server:
```bash
# Check if server is accessible
nc -zv <server-ip> 22

# Check SSH access
ssh -i <private-key> <username>@<server-ip>

# Check Docker on server
docker ps
```

## Advanced Configuration

### Matrix Builds

Test across multiple Python/Node.js versions:

```yaml
strategy:
  matrix:
    python-version: ["3.10", "3.11", "3.12"]
    node-version: ["18", "20"]
```

### Caching

Optimize build times with caching:

```yaml
- name: Cache Python dependencies
  uses: actions/cache@v3
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('requirements*.txt') }}
    restore-keys: |
      ${{ runner.os }}-pip-
```

### Self-Hosted Runners

Use self-hosted runners for:
- Large workloads
- Specific hardware requirements
- Private networks

```yaml
runs-on: self-hosted
```

## Security

### Secrets Management

1. **Never hardcode secrets** in workflow files
2. **Use GitHub Secrets** for sensitive data
3. **Rotate secrets** regularly
4. **Limit access** to secrets

### Code Security

1. **Dependency scanning** - Built into CI/CD
2. **SAST scanning** - Use Bandit, Semgrep
3. **Secret scanning** - Use GitHub Secret Scanning
4. **Container scanning** - Use Trivy, Snyk

### Deployment Security

1. **Manual approval** for production
2. **Health checks** before traffic routing
3. **Rollback capability** for failed deployments
4. **Immutable deployments** - New containers, not in-place updates

## Performance Optimization

### Parallel Jobs

Run tests in parallel:

```yaml
jobs:
  backend-test:
    runs-on: ubuntu-latest
  
  frontend-test:
    runs-on: ubuntu-latest
    
  # Both jobs run concurrently
```

### Job Dependencies

Define job dependencies for optimal execution:

```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
    
  test:
    runs-on: ubuntu-latest
    needs: lint  # Wait for lint to finish
    
  build:
    runs-on: ubuntu-latest
    needs: test  # Wait for tests to pass
```

### Artifact Management

Upload and download artifacts:

```yaml
- name: Upload test report
  uses: actions/upload-artifact@v4
  with:
    name: test-report
    path: report.html
    retention-days: 30

- name: Download artifact
  uses: actions/download-artifact@v4
  with:
    name: test-report
```

## Integration with External Services

### Slack Notifications

```yaml
- name: Notify Slack
  uses: rtCamp/action-slack-notify@v2
  env:
    SLACK_WEBHOOK: ${{ secrets.SLACK_WEBHOOK }}
    SLACK_COLOR: ${{ job.status }}
    SLACK_TITLE: "CI/CD ${{ job.status }}"
    SLACK_MESSAGE: "Workflow ${{ github.workflow }} completed"
```

### Discord Notifications

```yaml
- name: Notify Discord
  run: |
    curl -X POST -H 'Content-type: application/json' \
      --data '{"content":"CI/CD ${{ job.status }}: ${{ github.workflow }}"}' \
      ${{ secrets.DISCORD_WEBHOOK }}
```

### Email Notifications

Use GitHub's built-in notifications or third-party services.

## Example: Custom Workflow

Create a new workflow file `.github/workflows/custom.yml`:

```yaml
name: Custom Workflow

on:
  push:
    branches: [ "custom-branch" ]
  workflow_dispatch:

jobs:
  custom-job:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Run custom script
        run: |
          python scripts/custom.py
      
      - name: Upload result
        uses: actions/upload-artifact@v4
        with:
          name: custom-result
          path: output/
```

## Maintenance

### Update Dependencies

Regularly update Actions dependencies:

```yaml
# Update action versions
- uses: actions/checkout@v4  # Latest version
- uses: actions/setup-python@v5  # Latest version
```

### Clean Up Workflows

1. Remove unused workflows
2. Archive old workflow runs
3. Delete unused artifacts

### Monitor Costs

GitHub Actions has free minutes, but monitor usage:
```
Settings → Billing → Actions usage
```

## Documentation

### Workflow Documentation

Each workflow should include:

1. **Name** - Clear, descriptive name
2. **Description** - What it does
3. **Triggers** - When it runs
4. **Jobs** - List of jobs
5. **Environment Variables** - Required configuration
6. **Secrets** - Required secrets
7. **Outputs** - Generated artifacts

### Runbook

Create a deployment runbook for operations team:

| Scenario | Action | Owner |
|----------|--------|-------|
| CI test failure | Check test logs, fix code | Developers |
| Deployment failure | Check deployment logs, rollback | DevOps |
| Security alert | Review vulnerability, patch | Security Team |
| Performance issue | Analyze metrics, optimize | Performance Team |

## Support

### GitHub Actions Documentation

- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Workflow Syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [Marketplace](https://github.com/marketplace?type=actions)

### Community

- [GitHub Community](https://github.com/orgs/community/discussions)
- [Actions Toolkit](https://github.com/actions/toolkit)

## Summary

The BarPro CI/CD pipeline provides:

✅ **Automated Testing** - Unit, integration, security tests
✅ **Quality Gates** - Linting, formatting, type checking
✅ **Automated Deployment** - Staging and production
✅ **Performance Validation** - Load testing
✅ **Security Scanning** - Dependency and code scanning
✅ **Artifact Management** - Reports and build outputs
✅ **Manual Controls** - Approval gates for production

This ensures **high-quality, secure, and performant** deployments with **minimal manual intervention**.
