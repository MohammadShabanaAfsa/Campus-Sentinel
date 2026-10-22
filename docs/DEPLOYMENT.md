# Campus Sentinel — Deployment Guide

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker | 24+ | Container runtime |
| Docker Compose | 2.20+ | Orchestration |
| Python | 3.11+ | Backend (local dev) |
| Node.js | 20+ | Frontend (local dev) |
| Git | 2.40+ | Version control |

---

## Quick Start (Docker)

```bash
cd campus-sentinel

# 1. Create environment file
cp .env.example .env
# Edit .env — change SECRET_KEY, passwords, SMTP settings

# 2. Run setup script
chmod +x scripts/setup.sh
./scripts/setup.sh
```

Access the system:
- Dashboard:   http://localhost:3000
- API Docs:    http://localhost:8000/api/docs
- Grafana:     http://localhost:3001

Default credentials:
- Email: admin@campus-sentinel.local
- Password: Admin@123 (change immediately!)

---

## Local Development Setup

### Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start infrastructure (Postgres + Redis)
docker compose up -d postgres redis

# Run database migrations
alembic upgrade head

# Start FastAPI server
# --reload-dir scopes the watcher to source dirs only — without it, uvicorn
# watches the whole cwd recursively, including backend/.venv, causing
# constant spurious reloads. Omit --reload entirely for production.
uvicorn app.main:app --reload --reload-dir app --reload-dir ../ai-engine --reload-dir ../agents --port 8000

# In another terminal — start Celery worker
celery -A app.core.celery_app worker --loglevel=info -Q ai_tasks,alerts,analytics
```

### Frontend

```bash
cd frontend

npm install
npm run dev
# Access at http://localhost:3000
```

---

## Adding Cameras

### Via API

```bash
curl -X POST http://localhost:8000/api/v1/cameras/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Main Entrance Camera",
    "location_name": "Building A Entrance",
    "rtsp_url": "rtsp://admin:pass@192.168.1.100:554/stream1",
    "latitude": 17.3545464,
    "longitude": 78.5934475,
    "zone_type": "entrance"
  }'
```

### Camera URL Formats

| Camera Type | RTSP URL Format |
|-------------|----------------|
| Generic IP  | `rtsp://user:pass@IP:554/stream` |
| Hikvision   | `rtsp://user:pass@IP:554/Streaming/Channels/101` |
| Dahua       | `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=0` |
| RTSP Stream | `rtsp://IP:PORT/path` |
| Webcam      | `0` or `1` (device index) |

---

## GPU Setup (NVIDIA)

To enable GPU-accelerated inference:

1. Install NVIDIA Docker runtime
2. In `.env`:
   ```
   YOLO_DEVICE=cuda
   ```
3. Update `docker-compose.yml` backend service:
   ```yaml
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: 1
             capabilities: [gpu]
   ```

---

## Production Checklist

- [ ] Change all default passwords in `.env`
- [ ] Set strong `SECRET_KEY` (64+ char random string)
- [ ] Configure SSL/TLS in Nginx (Let's Encrypt recommended)
- [ ] Set up email alerts (SMTP configuration)
- [ ] Configure backup for PostgreSQL volumes
- [ ] Set `DEBUG=false`
- [ ] Restrict CORS origins in `app/main.py`
- [ ] Set up Grafana dashboards
- [ ] Configure Prometheus alerts

---

## Scaling

### Horizontal scaling (multiple backend workers):
```yaml
# docker-compose.yml
backend:
  deploy:
    replicas: 4
```

### Celery worker scaling:
```bash
celery -A app.core.celery_app worker --concurrency=8 -Q ai_tasks
```

### Camera load balancing:
Assign cameras to specific Celery workers using task routing.
