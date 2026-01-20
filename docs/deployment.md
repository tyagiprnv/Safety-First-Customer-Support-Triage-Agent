# Deployment Guide

This guide covers deploying the Safety-First Customer Support Triage Agent to production environments.

---

## Prerequisites

- Docker and Docker Compose installed
- OpenAI API key
- Cloud platform account (Render, Fly.io, or similar)
- 1GB RAM minimum, 2GB recommended
- 1 CPU core minimum

---

## Local Development Deployment

### 1. Environment Setup

```bash
# Clone repository
git clone <repository-url>
cd Safety-First-Customer-Support-Triage-Agent

# Copy environment template
cp .env.example .env

# Edit .env with your settings
nano .env
```

**Required Variables:**
```bash
OPENAI_API_KEY=your_api_key_here
```

**Optional Variables (with defaults):**
```bash
LOG_LEVEL=INFO
ENVIRONMENT=development
MIN_CONFIDENCE_THRESHOLD=0.7
HIGH_CONFIDENCE_THRESHOLD=0.85
HIGH_RISK_THRESHOLD=0.7
TEMPLATE_SIMILARITY_THRESHOLD=0.9
MIN_RETRIEVAL_SCORE=0.75
```

### 2. Build and Run

```bash
# Build Docker image
docker-compose build

# Start services
docker-compose up -d

# View logs
docker-compose logs -f triage-agent

# Check health
curl http://localhost:8000/health
```

### 3. Initialize Vector Database

```bash
# Ingest knowledge base (only needed once)
docker-compose exec triage-agent python scripts/ingest_knowledge_base.py
```

### 4. Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Test chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are your business hours?"}'

# Check metrics
curl http://localhost:8000/metrics
```

---

## Cloud Deployment: Render

### 1. Prepare Repository

```bash
# Ensure all files are committed
git add .
git commit -m "Ready for deployment"
git push origin main
```

### 2. Create Render Service

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name:** safety-first-triage-agent
   - **Environment:** Docker
   - **Region:** Choose closest to users
   - **Instance Type:** Starter ($7/month) or higher
   - **Docker Command:** (leave default, uses Dockerfile CMD)

### 3. Configure Environment Variables

Add in Render dashboard under "Environment":

```
OPENAI_API_KEY=your_key_here
LOG_LEVEL=INFO
ENVIRONMENT=production
```

### 4. Add Persistent Disk

1. Go to "Disks" section
2. Add disk:
   - **Name:** vector-db-storage
   - **Mount Path:** /app/data/vector_db
   - **Size:** 1GB

### 5. Deploy

1. Click "Create Web Service"
2. Wait for build and deployment
3. Check logs for startup messages
4. Run ingestion script:

```bash
# Via Render shell
render ssh safety-first-triage-agent
python scripts/ingest_knowledge_base.py
```

### 6. Verify Deployment

```bash
curl https://your-app.onrender.com/health
```

---

## Cloud Deployment: Fly.io

### 1. Install Fly CLI

```bash
# macOS
brew install flyctl

# Linux
curl -L https://fly.io/install.sh | sh

# Windows
iwr https://fly.io/install.ps1 -useb | iex
```

### 2. Authenticate

```bash
flyctl auth login
```

### 3. Create Fly App

```bash
# Initialize (creates fly.toml)
flyctl launch --no-deploy

# Follow prompts:
# - App name: safety-first-triage-agent
# - Region: Choose closest
# - PostgreSQL: No
# - Redis: No
```

### 4. Configure fly.toml

```toml
app = "safety-first-triage-agent"
primary_region = "sjc"

[build]
  dockerfile = "Dockerfile"

[env]
  LOG_LEVEL = "INFO"
  ENVIRONMENT = "production"
  VECTOR_DB_PATH = "/data/vector_db"

[[services]]
  http_checks = []
  internal_port = 8000
  processes = ["app"]
  protocol = "tcp"
  script_checks = []

  [services.concurrency]
    hard_limit = 25
    soft_limit = 20
    type = "connections"

  [[services.ports]]
    force_https = true
    handlers = ["http"]
    port = 80

  [[services.ports]]
    handlers = ["tls", "http"]
    port = 443

  [[services.tcp_checks]]
    grace_period = "10s"
    interval = "15s"
    restart_limit = 0
    timeout = "2s"

[[mounts]]
  source = "vector_db_volume"
  destination = "/data/vector_db"
```

### 5. Create Volume

```bash
flyctl volumes create vector_db_volume --size 1 --region sjc
```

### 6. Set Secrets

```bash
flyctl secrets set OPENAI_API_KEY=your_key_here
```

### 7. Deploy

```bash
flyctl deploy
```

### 8. Initialize Vector DB

```bash
# SSH into container
flyctl ssh console

# Run ingestion
python scripts/ingest_knowledge_base.py
```

### 9. Verify

```bash
curl https://safety-first-triage-agent.fly.dev/health
```

---

## Production Considerations

### Security

1. **API Key Management**
   - Use secrets management (Render/Fly secrets, not .env files)
   - Rotate keys regularly
   - Monitor for unauthorized usage

2. **Rate Limiting**
   - Add rate limiting middleware (e.g., slowapi)
   - Limit: 100 requests/minute per IP
   - Return 429 status when exceeded

3. **Input Validation**
   - Already validated (10-2000 chars)
   - Consider adding additional checks for malicious patterns
   - Log suspicious activity

4. **CORS Configuration**
   - Configure allowed origins
   - Don't use `*` in production

### Monitoring

1. **Application Logs**
   - All logs are JSON-structured
   - Send to log aggregation (Datadog, LogDNA, etc.)
   - Alert on error rates >1%

2. **Metrics to Track**
   - Total requests
   - Action distribution (TEMPLATE/GENERATED/ESCALATE)
   - Average latency by action type
   - Escalation rate
   - Safety metrics (high-risk PII escalations, forbidden intents)

3. **Health Checks**
   - `/health` endpoint monitored every 30s
   - Alert if unhealthy for >2 minutes
   - Restart container on persistent failures

### Scaling

1. **Vertical Scaling** (First Step)
   - Start with 1GB RAM, 1 CPU
   - Scale to 2GB RAM, 2 CPU as needed
   - Monitor memory usage (vector DB in-memory)

2. **Horizontal Scaling** (When Needed)
   - Multiple instances behind load balancer
   - Shared vector DB volume or external DB
   - Stateless design makes this straightforward

3. **Vector DB Scaling**
   - If KB grows >1000 docs, consider:
     - External ChromaDB service
     - Pinecone/Weaviate for managed solution
   - Current embedded mode good for <10K docs

### Costs

**Estimated Monthly Costs:**

| Component | Cost | Notes |
|-----------|------|-------|
| Cloud hosting (Render/Fly) | $7-25 | Depends on instance size |
| OpenAI API | Variable | $0.50-1.50 per 1K requests |
| Storage (vector DB) | <$1 | 1GB persistent disk |
| **Total** | **$8-30/month** | Low-moderate traffic |

**Cost Optimization:**
- Use template responses when possible (no API cost)
- Cache embeddings (don't re-embed same queries)
- Monitor API usage, set spending limits
- Consider GPT-4o-mini for generation (cheaper)

---

## Updating the Knowledge Base

### 1. Update Policy Files

```bash
# Edit files locally
nano data/knowledge_base/policies/billing_policy.md

# Commit changes
git commit -am "Update billing policy"
git push
```

### 2. Re-ingest

```bash
# On deployed instance
flyctl ssh console  # or Render shell

# Reset and re-ingest
python scripts/ingest_knowledge_base.py
# Answer 'y' when prompted to reset
```

### 3. Verify

```bash
# Test query that should use new information
curl -X POST https://your-app.com/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Test question about updated policy"}'
```

---

## Rollback Procedure

### If Deployment Fails

**Render:**
```bash
# Via dashboard: Manual Deploy → Previous Commit
```

**Fly.io:**
```bash
# List releases
flyctl releases

# Rollback to previous
flyctl releases rollback <version>
```

### If Knowledge Base Breaks

```bash
# Restore from backup (if available)
# Or re-run ingestion from git history

git checkout <previous-commit>
docker-compose exec triage-agent python scripts/ingest_knowledge_base.py
git checkout main
```

---

## Backup and Disaster Recovery

### Vector Database Backup

```bash
# Create backup
docker-compose exec triage-agent tar -czf /tmp/vector_db_backup.tar.gz /app/data/vector_db

# Copy to local
docker cp safety-first-triage-agent:/tmp/vector_db_backup.tar.gz ./backups/

# Restore from backup
docker cp ./backups/vector_db_backup.tar.gz safety-first-triage-agent:/tmp/
docker-compose exec triage-agent tar -xzf /tmp/vector_db_backup.tar.gz -C /
docker-compose restart
```

### Automated Backups

**Cron Job (on host):**
```bash
# Add to crontab
0 2 * * * /path/to/backup_script.sh
```

**backup_script.sh:**
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker exec safety-first-triage-agent tar -czf /tmp/backup_$DATE.tar.gz /app/data/vector_db
docker cp safety-first-triage-agent:/tmp/backup_$DATE.tar.gz /backups/
# Optional: Upload to S3/GCS
```

---

## Troubleshooting

### Application Won't Start

**Check logs:**
```bash
docker-compose logs triage-agent
```

**Common issues:**
- Missing `OPENAI_API_KEY`
- Port 8000 already in use
- Insufficient memory

### Vector DB Not Found

**Symptom:** 0 documents in vector store

**Solution:**
```bash
python scripts/ingest_knowledge_base.py
```

### High Latency

**Check:**
- OpenAI API status: status.openai.com
- Network latency to API
- Container resource limits
- Vector DB query performance

**Optimize:**
- Increase template match threshold (prefer templates)
- Reduce `top_k` for retrieval (3 → 2)
- Scale up instance size

### Memory Issues

**Symptom:** Container keeps restarting

**Solution:**
- Increase container memory limit
- Check vector DB size (`du -sh data/vector_db`)
- Consider external vector DB if >1GB

---

## Production Checklist

Before going live:

- [ ] Environment variables set (especially API key)
- [ ] Vector database populated
- [ ] Health check endpoint responding
- [ ] Test with real queries
- [ ] Logging configured
- [ ] Monitoring alerts set up
- [ ] Backup procedure tested
- [ ] Rollback procedure documented
- [ ] Rate limiting configured
- [ ] Security headers added (CORS, CSP)
- [ ] API usage limits set with OpenAI
- [ ] Cost alerts configured

---

## Support

For deployment issues:
1. Check logs first
2. Verify environment variables
3. Test health endpoint
4. Review this troubleshooting guide
5. Open GitHub issue with logs

---

**Deployment is complete when:**
- ✅ `/health` returns healthy
- ✅ `/chat` responds to test queries
- ✅ Logs show successful request processing
- ✅ Metrics show expected action distribution
