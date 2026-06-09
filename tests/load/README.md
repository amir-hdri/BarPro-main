# Load Testing for BarPro

This directory contains load testing configurations and scripts for the BarPro application.

## Tools Used

- **[Locust](https://locust.io/)** - Distributed load testing tool
- **Custom Python scripts** - For specialized testing scenarios

## Quick Start

### Install Locust

```bash
# Install globally
pip install locust

# Or in a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install locust
```

### Run Load Tests

#### Web UI Mode (Recommended for Development)

```bash
# Start the web interface at http://localhost:8089
locust -f locustfile.py
```

Open your browser to [http://localhost:8089](http://localhost:8089) to:
- Configure user count and spawn rate
- Start/stop tests
- View real-time statistics
- Download reports

#### Headless Mode (for CI/CD)

```bash
# Basic test with 100 users, spawning 10 users per second, running for 5 minutes
locust -f locustfile.py --headless -u 100 -r 10 --run-time 5m --host=https://staging.barpro.com
```

#### With HTML Report

```bash
# Generate HTML report
locust -f locustfile.py --headless -u 100 -r 10 --run-time 5m --host=https://staging.barpro.com --html=load-test-report.html
```

## Test Scenarios

The `locustfile.py` defines several user types:

| User Type | Description | Wait Time | Typical Usage |
|-----------|-------------|-----------|---------------|
| `NormalUser` | Regular application user | 1-3s | Day-to-day operations |
| `HeavyUser` | Power user with high activity | 0.5-1s | Intensive usage |
| `ReadOnlyUser` | View-only user | 2-5s | Reporting, auditing |
| `AuthUser` | Authentication-focused | 1-2s | Login-heavy scenarios |
| `SmokeTestUser` | Lightweight health checks | 0.5-1s | Quick validation |
| `FullFlowUser` | Complete workflow | 1-3s | End-to-end testing |

## Environment Variables

Configure test behavior with environment variables:

```bash
# Authentication
JWT_TOKEN="your_jwt_token_here" \
API_KEY="your_api_key_here" \
BASE_URL="https://staging.barpro.com" \
locust -f locustfile.py
```

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_TOKEN` | JWT token for authenticated requests | `test-token` |
| `API_KEY` | API key for requests | `test-api-key` |
| `BASE_URL` | Base URL for the API | `http://localhost:8000` |

## Test Configuration

### Recommended Test Profiles

#### 1. Smoke Test (Quick Validation)
```bash
locust -f locustfile.py --headless -u 10 -r 5 --run-time 1m --host=https://staging.barpro.com
```

**Purpose**: Verify basic functionality
**Users**: 10 total, 5 per second
**Duration**: 1 minute
**Expected**: All endpoints respond successfully

#### 2. Light Load Test
```bash
locust -f locustfile.py --headless -u 50 -r 5 --run-time 3m --host=https://staging.barpro.com
```

**Purpose**: Basic performance validation
**Users**: 50 total, 5 per second
**Duration**: 3 minutes
**Expected**: < 500ms average response time

#### 3. Medium Load Test
```bash
locust -f locustfile.py --headless -u 200 -r 20 --run-time 5m --host=https://staging.barpro.com
```

**Purpose**: Simulate moderate traffic
**Users**: 200 total, 20 per second
**Duration**: 5 minutes
**Expected**: < 1000ms average response time, < 1% error rate

#### 4. Heavy Load Test
```bash
locust -f locustfile.py --headless -u 500 -r 50 --run-time 10m --host=https://staging.barpro.com
```

**Purpose**: Stress test the system
**Users**: 500 total, 50 per second
**Duration**: 10 minutes
**Expected**: System remains stable, graceful degradation

#### 5. Soak Test (Long-running)
```bash
locust -f locustfile.py --headless -u 100 -r 5 --run-time 60m --host=https://staging.barpro.com
```

**Purpose**: Identify memory leaks, slow performance degradation
**Users**: 100 total, 5 per second
**Duration**: 60 minutes
**Expected**: Stable performance throughout

## Integration with GitHub Actions

The CI/CD workflow includes load testing:

```yaml
# In .github/workflows/ci-cd.yml
- name: Run Load Test
  run: |
    locust -f tests/load/locustfile.py --headless -u 100 -r 10 --run-time 5m --host=https://staging.barpro.com --html=load-test-report.html
  continue-on-error: true

- name: Upload Load Test Report
  uses: actions/upload-artifact@v4
  with:
    name: load-test-report
    path: load-test-report.html
```

## Custom Test Scripts

### Simple Load Test Script

Create a Python script for programmatic load testing:

```python
# tests/load/simple_test.py
from locust import HttpUser, task, between

class SimpleUser(HttpUser):
    wait_time = between(1, 2)
    
    @task
    def health_check(self):
        self.client.get("/healthz")
    
    @task(3)
    def list_waybills(self):
        self.client.get("/api/v1/waybills", headers={"Authorization": "Bearer YOUR_TOKEN"})
```

Run with:
```bash
locust -f tests/load/simple_test.py
```

## Monitoring & Metrics

Locust provides several metrics:

- **Requests per second (RPS)** - Total requests processed
- **Response times** - Average, median, max, min
- **Error rate** - Percentage of failed requests
- **Number of users** - Current active users

### Key Metrics to Monitor

1. **Average Response Time**
   - Target: < 500ms for API endpoints
   - Warning: > 1000ms
   - Critical: > 5000ms

2. **Error Rate**
   - Target: < 0.1%
   - Warning: > 1%
   - Critical: > 5%

3. **Requests per Second**
   - Baseline: Measure current production RPS
   - Target: Handle 2x baseline
   - Stress: Handle 5x baseline

4. **Memory Usage**
   - Monitor container memory during tests
   - Target: < 80% of available memory

## Troubleshooting

### Common Issues

1. **Connection Errors**
   ```
   Check that the --host parameter points to the correct URL
   Verify the server is running: curl -v http://localhost:8000/healthz
   ```

2. **Authentication Errors**
   ```
   Set valid JWT_TOKEN or API_KEY environment variables
   Verify token hasn't expired
   ```

3. **Slow Performance**
   ```
   Check database connection pool settings
   Verify Redis is available for caching
   Check server resource usage (CPU, memory, disk I/O)
   ```

4. **Timeouts**
   ```
   Increase timeout settings in locust.conf
   Check for slow database queries
   Verify external service integrations
   ```

## Performance Benchmarks

Use these benchmarks as targets for your load tests:

| Endpoint | Target RPS | Target Response Time |
|----------|-----------|---------------------|
| `/healthz` | 1000+ | < 10ms |
| `/api/v1/waybills` (list) | 500 | < 200ms |
| `/api/v1/waybills` (create) | 100 | < 500ms |
| `/api/v1/drivers` | 500 | < 200ms |
| `/api/v1/reports` | 200 | < 500ms |
| `/waybill/calculate-route` | 50 | < 1000ms |

## Best Practices

1. **Start Small** - Begin with low user counts and gradually increase
2. **Monitor Resources** - Watch server CPU, memory, disk I/O during tests
3. **Test Incrementally** - Test one component at a time before full integration
4. **Use Production-Like Data** - Test with realistic data volumes
5. **Test Failure Scenarios** - Simulate errors (network issues, database failures)
6. **Document Results** - Keep records of test configurations and outcomes
7. **Automate Testing** - Integrate load tests into CI/CD pipeline

## Advanced Configuration

### Distributed Load Testing

Run Locust on multiple machines:

```bash
# Master node
locust -f locustfile.py --master --host=https://staging.barpro.com

# Worker nodes
locust -f locustfile.py --worker --master-host=MASTER_IP
```

### Custom Load Shapes

Use different spawn rates over time:

```bash
# Ramp up, sustain, ramp down
locust -f locustfile.py --headless --run-time 10m \
  --step-load --step-users 100 --step-time 2m \
  --step-users 500 --step-time 5m \
  --step-users 100 --step-time 2m \
  --host=https://staging.barpro.com
```

### Weighted User Classes

Specify user class weights:

```bash
locust -f locustfile.py --headless -u 100 -r 10 --run-time 5m \
  --weights NormalUser:5,HeavyUser:2,ReadOnlyUser:3 \
  --host=https://staging.barpro.com
```
