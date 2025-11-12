# 🚀 Deployment Guide

Complete deployment guide for Flock application to production environments.

---

## 📋 Table of Contents

- [Prerequisites](#prerequisites)
- [Pre-Deployment Checklist](#pre-deployment-checklist)
- [Environment Setup](#environment-setup)
- [Deployment Options](#deployment-options)
  - [DigitalOcean App Platform](#digitalocean-app-platform)
  - [Docker Deployment](#docker-deployment)
  - [Traditional VPS](#traditional-vps)
- [Post-Deployment](#post-deployment)
- [Monitoring & Maintenance](#monitoring--maintenance)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Accounts & Services

Before deploying, ensure you have accounts for:

1. **Database**: PostgreSQL (DigitalOcean Managed Database, AWS RDS, or self-hosted)
2. **Cache/Queue**: Redis (DigitalOcean, AWS ElastiCache, or self-hosted)
3. **Storage**: DigitalOcean Spaces or AWS S3
4. **Vector Database**: Pinecone
5. **Payment**: Stripe
6. **AI**: OpenAI
7. **Email**: SMTP server (Gmail, SendGrid, Mailgun, etc.)

### System Requirements

- **Python**: 3.11 or higher
- **RAM**: Minimum 1GB, recommended 2GB+
- **Disk**: Minimum 10GB, recommended 20GB+ (for logs and temporary files)
- **CPU**: Minimum 1 core, recommended 2+ cores

---

## Pre-Deployment Checklist

### ✅ Security Checklist

- [ ] All secrets are in environment variables (not hardcoded)
- [ ] `.env` file is NOT committed to git
- [ ] Strong, randomly generated `SECRET_KEY` configured
- [ ] Strong encryption keys (`ENCRYPTION_PASSWORD`, `ENCRYPTION_SALT`, `HASH_SALT`)
- [ ] Database uses strong password
- [ ] API keys are production keys (not test keys)
- [ ] Stripe webhooks configured with secret
- [ ] HTTPS is enforced (`FLASK_ENV=production`)
- [ ] Secure cookies enabled (`SESSION_COOKIE_SECURE=True`)

### ✅ Configuration Checklist

- [ ] All required environment variables set (see `.env.example`)
- [ ] Database schema initialized
- [ ] Pinecone index created
- [ ] DigitalOcean Space / S3 bucket created
- [ ] Stripe products and prices configured
- [ ] Email SMTP credentials tested
- [ ] Redis connection tested

### ✅ Code Checklist

- [ ] Latest code merged to main branch
- [ ] All tests passing
- [ ] No debug print statements in production paths
- [ ] `requirements.txt` is up to date
- [ ] Documentation is current

---

## Environment Setup

### 1. Clone Repository

```bash
git clone https://github.com/your-username/flock.git
cd flock
```

### 2. Create Virtual Environment

```bash
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# System dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y poppler-utils tesseract-ocr libmagic1

# System dependencies (macOS)
brew install poppler tesseract libmagic
```

### 4. Configure Environment Variables

```bash
# Copy template
cp .env.example .env

# Edit with your production values
nano .env  # or vim, code, etc.
```

**Critical Variables to Set:**

```bash
# Security (generate strong values!)
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
ENCRYPTION_PASSWORD=<strong-password-min-16-chars>
ENCRYPTION_SALT=<strong-salt-min-16-chars>
HASH_SALT=<run: python -c "import secrets; print(secrets.token_hex(32))">

# Database
DATABASE_URL=postgresql://user:password@host:port/database

# API Keys
OPENAI_API_KEY=sk-...
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
PINECONE_API_KEY=...

# Application
FLASK_ENV=production
APP_URL=https://yourdomain.com
```

### 5. Initialize Database

```bash
# Run database migrations/initialization
python -c "from app import init_database; init_database()"

# Or manually run SQL schema
psql $DATABASE_URL < schema.sql
```

---

## Deployment Options

### Option 1: DigitalOcean App Platform (Recommended)

**Pros**: Managed platform, auto-scaling, built-in monitoring, easy setup
**Cons**: More expensive than VPS, less control

#### Step 1: Prepare Configuration

The `FIXED_APP_SPEC.yaml` file is already configured. Review and update:

```yaml
# Key sections to verify:
databases:
  - name: db
    engine: PG
    version: "15"

envs:
  - key: SECRET_KEY
    value: "your-secret-key-here"
    type: SECRET
```

#### Step 2: Deploy via CLI

```bash
# Install doctl
brew install doctl  # macOS
# or: snap install doctl  # Linux

# Authenticate
doctl auth init

# Create app
doctl apps create --spec FIXED_APP_SPEC.yaml

# Monitor deployment
doctl apps list
doctl apps logs <app-id>
```

#### Step 3: Deploy via Web Console

1. Go to [DigitalOcean Apps](https://cloud.digitalocean.com/apps)
2. Click "Create App"
3. Connect your GitHub repository
4. Select the main branch
5. Upload `FIXED_APP_SPEC.yaml` or configure manually:
   - **Web Service**: `gunicorn wsgi:app`
   - **Worker Service**: `celery -A celery_config.celery_app worker`
6. Set environment variables
7. Click "Create Resources"

#### Step 4: Configure Webhooks

Update Stripe webhook URL to your deployed app:
```
https://your-app.ondigitalocean.app/api/webhooks/stripe
```

---

### Option 2: Docker Deployment

**Pros**: Portable, consistent environments, easy scaling
**Cons**: Requires Docker knowledge, more complex setup

#### Step 1: Create Dockerfile

Create `Dockerfile` in project root:

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Expose port
EXPOSE 8080

# Run gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--timeout", "120", "wsgi:app"]
```

#### Step 2: Create docker-compose.yml

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8080:8080"
    env_file:
      - .env
    depends_on:
      - db
      - redis
    volumes:
      - ./logs:/app/logs

  worker:
    build: .
    command: celery -A celery_config.celery_app worker --loglevel=info
    env_file:
      - .env
    depends_on:
      - redis
      - db

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: flock
      POSTGRES_USER: flock
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

#### Step 3: Build and Run

```bash
# Build images
docker-compose build

# Run services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

---

### Option 3: Traditional VPS (Ubuntu 20.04/22.04)

**Pros**: Full control, cost-effective
**Cons**: More manual configuration, you manage updates

#### Step 1: Server Setup

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python 3.11
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev

# Install system dependencies
sudo apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    libmagic1 \
    postgresql-client \
    redis-tools \
    nginx \
    supervisor
```

#### Step 2: Application Setup

```bash
# Create app user
sudo useradd -m -s /bin/bash flock
sudo su - flock

# Clone repository
git clone https://github.com/your-username/flock.git
cd flock

# Setup virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Add production values
```

#### Step 3: Configure Supervisor (Process Manager)

Create `/etc/supervisor/conf.d/flock.conf`:

```ini
[program:flock-web]
command=/home/flock/flock/venv/bin/gunicorn --bind 127.0.0.1:8080 --workers 4 wsgi:app
directory=/home/flock/flock
user=flock
autostart=true
autorestart=true
stderr_logfile=/var/log/flock/web.err.log
stdout_logfile=/var/log/flock/web.out.log

[program:flock-worker]
command=/home/flock/flock/venv/bin/celery -A celery_config.celery_app worker --loglevel=info
directory=/home/flock/flock
user=flock
autostart=true
autorestart=true
stderr_logfile=/var/log/flock/worker.err.log
stdout_logfile=/var/log/flock/worker.out.log
```

```bash
# Create log directory
sudo mkdir -p /var/log/flock
sudo chown flock:flock /var/log/flock

# Reload supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start all
```

#### Step 4: Configure Nginx (Reverse Proxy)

Create `/etc/nginx/sites-available/flock`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL certificates (use Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Max upload size
    client_max_body_size 10M;

    # Proxy to Flask app
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    # Access log
    access_log /var/log/nginx/flock-access.log;
    error_log /var/log/nginx/flock-error.log;
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/flock /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Setup Let's Encrypt SSL
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

---

## Post-Deployment

### 1. Verify Deployment

```bash
# Check application health
curl https://yourdomain.com/health

# Expected response:
# {"status": "healthy", "database": "connected", "redis": "connected"}
```

### 2. Test Critical Features

- [ ] User registration works
- [ ] User login works
- [ ] Profile creation works
- [ ] Document upload works
- [ ] Payment processing works
- [ ] Webhook handling works
- [ ] Email sending works

### 3. Configure Monitoring

#### Application Monitoring (Sentry)

```bash
# Add to requirements.txt
sentry-sdk[flask]==1.40.0

# In app.py, add:
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn=os.environ.get('SENTRY_DSN'),
    integrations=[FlaskIntegration()],
    traces_sample_rate=1.0
)
```

#### Log Monitoring

Options:
- **Papertrail**: Easy log aggregation
- **Loggly**: Advanced log analysis
- **AWS CloudWatch**: If using AWS
- **DigitalOcean Monitoring**: Built-in if using DO

### 4. Setup Backups

#### Database Backups

```bash
# Automated daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump $DATABASE_URL > /backups/flock_$DATE.sql
gzip /backups/flock_$DATE.sql

# Keep only last 30 days
find /backups -name "flock_*.sql.gz" -mtime +30 -delete
```

Add to crontab:
```bash
0 2 * * * /usr/local/bin/backup-flock.sh
```

#### Document Backups

Documents are in DigitalOcean Spaces/S3 - enable versioning:
```bash
# AWS S3
aws s3api put-bucket-versioning \
    --bucket your-bucket \
    --versioning-configuration Status=Enabled

# Enable lifecycle policy for old versions
```

---

## Monitoring & Maintenance

### Key Metrics to Monitor

1. **Application Health**
   - Response times
   - Error rates
   - Request throughput

2. **Resource Usage**
   - CPU utilization
   - Memory usage
   - Disk space

3. **External Services**
   - Database connections
   - Redis connections
   - API rate limits (OpenAI, Stripe, Pinecone)

4. **Business Metrics**
   - New user signups
   - Subscription conversions
   - Document uploads
   - Active users

### Maintenance Schedule

**Daily:**
- Check error logs
- Monitor resource usage
- Review security alerts

**Weekly:**
- Review application metrics
- Check backup integrity
- Update dependencies (if security patches)

**Monthly:**
- Full dependency updates
- Security audit
- Performance optimization review
- Review and archive old logs

**Quarterly:**
- Comprehensive security review
- Disaster recovery test
- Infrastructure cost review
- Feature usage analysis

---

## Troubleshooting

### Common Issues

#### 1. Application Won't Start

```bash
# Check logs
docker-compose logs web  # Docker
sudo supervisorctl status flock-web  # VPS
sudo journalctl -u flock-web  # Systemd

# Common causes:
# - Missing environment variables
# - Database connection failed
# - Port already in use
```

**Solution:**
```bash
# Verify environment variables
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('SECRET_KEY' in os.environ)"

# Test database connection
psql $DATABASE_URL -c "SELECT version();"

# Check port usage
lsof -i :8080
```

#### 2. Database Connection Errors

```bash
# Error: "could not connect to server"

# Check DATABASE_URL format
echo $DATABASE_URL
# Should be: postgresql://user:password@host:port/database

# Test connection
psql $DATABASE_URL

# Check firewall rules
sudo ufw status  # Ubuntu
```

#### 3. Celery Worker Not Processing

```bash
# Check worker status
celery -A celery_config.celery_app inspect active

# Check Redis connection
redis-cli -u $REDIS_URL ping

# Restart worker
sudo supervisorctl restart flock-worker
```

#### 4. High Memory Usage

```bash
# Check memory
free -h
docker stats  # If using Docker

# Common causes:
# - Too many Gunicorn workers
# - Memory leak in application
# - Large document processing

# Solution: Adjust worker count
gunicorn --workers 2 --worker-class sync wsgi:app
```

#### 5. SSL Certificate Errors

```bash
# Renew Let's Encrypt certificate
sudo certbot renew --dry-run  # Test
sudo certbot renew  # Actual renewal

# Auto-renewal is configured by default
```

### Emergency Procedures

#### Roll Back Deployment

```bash
# Git rollback
git revert HEAD
git push origin main

# Docker rollback
docker-compose down
git checkout <previous-commit>
docker-compose up -d

# VPS rollback
cd /home/flock/flock
git reset --hard <previous-commit>
sudo supervisorctl restart all
```

#### Database Recovery

```bash
# Stop application
docker-compose stop web worker
# or: sudo supervisorctl stop all

# Restore from backup
gunzip -c /backups/flock_YYYYMMDD_HHMMSS.sql.gz | psql $DATABASE_URL

# Start application
docker-compose start web worker
# or: sudo supervisorctl start all
```

---

## Additional Resources

- **Flask Documentation**: https://flask.palletsprojects.com/
- **Gunicorn Documentation**: https://docs.gunicorn.org/
- **Nginx Documentation**: https://nginx.org/en/docs/
- **PostgreSQL Documentation**: https://www.postgresql.org/docs/
- **Celery Documentation**: https://docs.celeryq.dev/
- **Docker Documentation**: https://docs.docker.com/
- **DigitalOcean Tutorials**: https://www.digitalocean.com/community/tutorials

---

## Support

Need help with deployment?

- 📧 **Email**: [INSERT SUPPORT EMAIL]
- 💬 **Discord**: [INSERT DISCORD LINK]
- 📖 **Documentation**: [GitHub Wiki](https://github.com/your-username/flock/wiki)
- 🐛 **Issues**: [GitHub Issues](https://github.com/your-username/flock/issues)

---

**Last Updated**: November 12, 2024
**Version**: 1.0.0
