# Log Rotation Configuration for BarPro

## Overview

This directory contains logrotate configurations for the BarPro application to ensure proper log management and prevent disk space exhaustion.

## Files

- `logrotate.conf` - Main logrotate configuration file
- `docker-logrotate.conf` - Configuration for containerized environments

## Setup

### On Bare Metal / VM Servers

1. **Copy configuration to system logrotate directory:**
   ```bash
   sudo cp infra/logging/logrotate.conf /etc/logrotate.d/barpro
   ```

2. **Create log directories:**
   ```bash
   sudo mkdir -p /var/log/barpro/{backend,frontend,celery,rpa}
   sudo chown -R appuser:appuser /var/log/barpro
   sudo chmod -R 755 /var/log/barpro
   ```

3. **Test configuration:**
   ```bash
   sudo logrotate -d /etc/logrotate.d/barpro
   ```

4. **Run manually (for testing):**
   ```bash
   sudo logrotate -vf /etc/logrotate.d/barpro
   ```

### In Docker Containers

Use the `docker-logrotate.conf` configuration with a Docker volume mount:

```yaml
# docker-compose.yml addition
services:
  backend:
    volumes:
      - /var/log/barpro/backend:/var/log/barpro/backend
      - ./infra/logging/docker-logrotate.conf:/etc/logrotate.d/barpro:ro
```

And install logrotate in your Dockerfile:

```dockerfile
RUN apt-get update && apt-get install -y logrotate && rm -rf /var/lib/apt/lists/*
COPY infra/logging/docker-logrotate.conf /etc/logrotate.d/barpro
```

## Log Rotation Policy

| Log Type | Retention | Rotation Frequency | Compression |
|----------|-----------|---------------------|-------------|
| Application (general) | 30 days | Daily | Yes |
| Backend (FastAPI) | 14 days | Daily | Yes |
| Frontend (Next.js) | 14 days | Daily | Yes |
| Celery Workers | 7 days | Daily | Yes |
| RPA Automation | 7 days | Daily | Yes |
| Nginx | 14 days | Daily | Yes |
| Access Logs | 90 days | Daily | Yes |
| Error Logs | 90 days | Daily | Yes |

## Python Logging Configuration

The application uses Python's `logging` module with JSON formatting. For file-based logging with rotation, see the `app/core/logging.py` configuration.

## Monitoring

Monitor log disk usage with:

```bash
# Check current log sizes
du -sh /var/log/barpro/*

# Check disk usage by logs
du -sh /var/log/barpro/* | sort -hr | head -10

# Set up monitoring alert (cron job)
0 * * * * /usr/local/bin/check-log-size.sh
```

## Troubleshooting

### Logs not rotating
1. Check if logrotate is installed: `which logrotate`
2. Test configuration: `sudo logrotate -d /etc/logrotate.d/barpro`
3. Check for syntax errors in configuration
4. Verify file permissions on log directories

### Permission denied errors
```bash
sudo chown -R appuser:appuser /var/log/barpro
sudo chmod -R 755 /var/log/barpro
```

### Logs growing too large between rotations
Increase rotation frequency to hourly for high-volume logs:
```
hourly
rotate 30
```

## Best Practices

1. **Separate log files** by component (backend, frontend, celery, rpa)
2. **Use different retention periods** based on log importance
3. **Compress old logs** to save disk space
4. **Monitor log directory size** with alerts
5. **Centralize logs** in production (ELK stack, Loki, etc.)
6. **Test rotation** before deploying to production
