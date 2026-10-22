# Production Deployment Guide

## Prerequisites

- Ubuntu 22.04 LTS server (4 vCPU, 8 GB RAM, 100 GB SSD minimum)
- Docker Engine 25+ and Docker Compose 2.20+
- Domain name pointing to server IP
- Ports 80, 443 open in firewall

---

## 1. Server Setup

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Clone repo
git clone https://github.com/YOUR_ORG/campus-sentinel /opt/campus-sentinel
cd /opt/campus-sentinel
```

## 2. Configure Environment

```bash
cp .env.example .env
nano .env   # Fill in all secrets
```

Key values to set:
```
SECRET_KEY=REPLACE_WITH_YOUR_SECRET_KEY
POSTGRES_PASSWORD=REPLACE_WITH_YOUR_POSTGRES_PASSWORD
REDIS_PASSWORD=REPLACE_WITH_YOUR_REDIS_PASSWORD
MAIL_USERNAME=info@example.com  # Documentation placeholder; use your own account
MAIL_PASSWORD=REPLACE_WITH_YOUR_MAIL_PASSWORD
ALLOWED_HOSTS=your-domain.com
FRONTEND_URL=https://your-domain.com
```

## 3. SSL Certificate

### Option A — Let's Encrypt (recommended)
```bash
sudo apt install certbot
sudo certbot certonly --standalone -d your-domain.com
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem infrastructure/nginx/ssl/certs/campus-sentinel.crt
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem infrastructure/nginx/ssl/private/campus-sentinel.key
```

### Option B — Self-signed (for testing)
```bash
mkdir -p infrastructure/nginx/ssl/{certs,private}
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout infrastructure/nginx/ssl/private/campus-sentinel.key \
  -out infrastructure/nginx/ssl/certs/campus-sentinel.crt \
  -subj "/CN=campus-sentinel.local"
```

## 4. Update Nginx Config

Edit `infrastructure/nginx/nginx.prod.conf`:
```nginx
server_name your-domain.com;   # Line 68
```

## 5. Launch

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Watch logs
docker compose logs -f backend

# Check health
curl https://your-domain.com/health
```

## 6. Initialize Data

```bash
# Apply database schema
docker compose exec backend alembic upgrade head

# Seed training data and train models
docker compose exec backend ./scripts/seed_and_train.sh

# Verify
docker compose exec backend python -c "
from ai_engine.prediction.threat_predictor import ThreatPredictor
p = ThreatPredictor('test')
print('RF model loaded:', p._rf_model is not None)
"
```

## 7. Add Cameras

Visit `https://your-domain.com` → Login → Cameras → Add Camera.

RTSP URL format:
- Hikvision: `rtsp://admin:PASSWORD@192.168.1.100:554/Streaming/Channels/101`
- Dahua: `rtsp://admin:PASSWORD@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0`
- Generic: `rtsp://user:pass@ip:554/stream`

## 8. Monitoring

- Grafana: `https://your-domain.com:3001` (admin / admin — change on first login)
- Flower (Celery): `http://internal-ip:5555`
- Prometheus: `http://internal-ip:9090`

## 9. Maintenance

### Backup database
```bash
docker compose exec postgres pg_dump -U cs_admin campus_sentinel | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Update deployment
```bash
git pull origin main
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans
```

### Renew SSL
```bash
sudo certbot renew
# Copy renewed certs (see step 3)
docker compose restart nginx
```

### View logs
```bash
docker compose logs backend --tail=100 -f
docker compose logs celery_worker --tail=100 -f
```

## 10. Security Checklist

- [ ] `SECRET_KEY` is 64+ character random string
- [ ] `POSTGRES_PASSWORD` is strong and unique
- [ ] `REDIS_PASSWORD` is set
- [ ] `MAIL_USERNAME` / `MAIL_PASSWORD` configured
- [ ] SSL certificate installed and valid
- [ ] Firewall allows only 80, 443, 22 from external
- [ ] Prometheus / Grafana / Flower **NOT** exposed externally
- [ ] Default admin password changed after first login
- [ ] `ENVIRONMENT=production` set in `.env`
- [ ] `DEBUG=false` set in `.env`
- [ ] Regular backups scheduled via cron

---

## Scaling

### More cameras (high camera count)
- Increase `MAX_CAMERAS` in settings
- Add more Celery workers: `docker compose up -d --scale celery_worker=3`
- Use GPU for YOLO: set `YOLO_DEVICE=cuda` and use `--gpus all` in docker run

### Database tuning (TimescaleDB)
```sql
-- Increase chunk interval for high insert rate
SELECT set_chunk_time_interval('detections', INTERVAL '1 day');

-- Tune compression
ALTER TABLE detections SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'camera_id'
);
SELECT add_compression_policy('detections', INTERVAL '7 days');
```
