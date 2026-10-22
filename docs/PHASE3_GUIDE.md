# Phase 3 — Behavioral Analytics Engine + Alert System + Explainability

## Overview

Phase 3 completes the intelligence layer of Campus Sentinel:
- **Adaptive Behavioral DNA (ABD)** — IsolationForest anomaly scoring per camera × hour × day-of-week
- **Threat Prediction** — RandomForest + LSTM ensemble threat classifiers
- **Email Dispatch** — FastAPI-Mail with HTML alert + daily digest templates
- **SHAP Explainability** — Feature contribution visualization on every alert
- **Admin API** — Manual trigger for training, CSI computation, data seeding, digest dispatch
- **AI Agents Status Page** — Live view of all 5 agents + Redis channels + ABD controls

---

## Quick Start

### 1. Seed training data + train models (run once after first boot)

```bash
# In Docker
docker compose exec backend ./scripts/seed_and_train.sh

# OR locally
./scripts/seed_and_train.sh --days 30
```

This runs:
1. `ai_engine.abd.data_seeder` → 30 days of synthetic behavior_logs per camera
2. `ABDTrainer.train_all_zones()` → 168 IsolationForest models per camera
3. `model_trainer --model rf` → Global RandomForest threat predictor

### 2. Configure email (optional)

In `.env`:
```
MAIL_USERNAME=info@example.com  # Documentation placeholder; use your own account
MAIL_PASSWORD=your-app-password   # Gmail App Password (not account password)
MAIL_FROM=alerts@campus-sentinel.local
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_STARTTLS=true
FRONTEND_URL=http://your-domain.com
```

Leave `MAIL_USERNAME` blank → emails are logged (mock mode) with no error.

### 3. Verify threat predictions flow

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -F "username=admin@campus-sentinel.local" -F "password=Admin@123" \
  | jq -r .access_token)

# Trigger manual prediction update
curl -X POST http://localhost:8000/api/v1/admin/compute-csi \
  -H "Authorization: Bearer $TOKEN"

# View predictions (last 6 hours)
curl http://localhost:8000/api/v1/predictions/?hours=6 \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## Architecture

### ABD Pipeline

```
behavior_logs table (TimescaleDB)
    ↓ (ABDTrainer.train_all_zones, nightly 2AM)
IsolationForest per camera × hour × day_of_week
    ↓ (saved as .pkl to /app/models/abd/)
ABDScorer.score(feature_vector)
    → anomaly score 0–1 written to Redis camera:ID:behavior_state
    → CSI anomaly_score component updated each minute
```

### Threat Prediction Pipeline

```
Redis camera:ID:behavior_state (every 5 minutes via Celery Beat)
    ↓ (update_threat_predictions task)
ThreatPredictor.predict(feature_vector, behavior_state)
    → RF model (if trained) or rule-based fallback
    → dict: { "crowd_surge": {prob, level, action}, ... }
    ↓
Redis camera:ID:predictions (360s TTL)
Redis publish: csi_updates → { type: "predictions_update" }
    ↓
WebSocket → ThreatPredictions component → dashboard
```

### Alert Explanation (SHAP-style)

Every alert stored in DB contains an `explanation` JSON:
```json
{
  "method": "SHAP",
  "feature_contributions": {
    "duration": 0.42,
    "location_risk": 0.20,
    "crowd_density": 0.18,
    "time_of_day": 0.10,
    "historical_pattern": 0.10
  },
  "base_value": 0.0,
  "predicted_value": 0.78,
  "summary": "Person loitered for 8 minutes in low-traffic zone."
}
```

Frontend `ExplanationPanel` renders this as a horizontal bar chart.
Click the `▶` arrow on any alert row to expand it.

---

## API Reference — Phase 3

### Admin endpoints (require `role: admin`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/admin/train-abd` | Queue ABD model retraining |
| `POST` | `/api/v1/admin/compute-csi` | Trigger immediate CSI computation |
| `POST` | `/api/v1/admin/seed-data?days=30` | Seed synthetic training data |
| `POST` | `/api/v1/admin/send-digest` | Send daily security digest now |

### Predictions

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/v1/predictions/?hours=6` | List recent threat predictions |
| `GET`  | `/api/v1/predictions/?camera_id=&threat_level=high` | Filtered predictions |

---

## Celery Beat Schedule (Phase 3 additions)

| Task | Schedule | Description |
|------|----------|-------------|
| `compute_campus_safety_index` | Every 60s | Pulls Redis → scores all cameras → DB + broadcast |
| `update_threat_predictions` | Every 5min | RF predictions for all online cameras |
| `train_abd_models` | Daily 2AM | Retrain IsolationForest on last 30 days |
| `send_daily_digest_email` | Daily 7AM | Email digest to all admin users |
| `cleanup_old_snapshots` | Hourly | Delete alert snapshots > 7 days old |

---

## Frontend Pages (Phase 3)

| Route | File | Features |
|-------|------|---------|
| `/alerts` | `app/alerts/page.tsx` | Expandable rows with SHAP chart, filter by status/severity, Ack/Resolve |
| `/analytics` | `app/analytics/page.tsx` | CSI over time, detections by hour, behavior pie chart |
| `/agents` | `app/agents/page.tsx` | Agent pipeline view, ABD training control, Redis channel status |
| `/map` | `app/map/page.tsx` | Full-screen Leaflet campus map |
| `/login` | `app/login/page.tsx` | JWT auth, default creds shown for dev |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| ABD models not found | Run `./scripts/seed_and_train.sh` first |
| Predictions always rule-based | RF model not trained — run `python -m ai_engine.prediction.model_trainer --model rf --synthetic` |
| Emails not sending | Set `MAIL_USERNAME` in `.env`; test with `POST /admin/send-digest` |
| `send_daily_digest_email` task missing | Ensure Celery Beat restarted after config change |
| ExplanationPanel empty | Alert created before Phase 3 — older alerts have no `feature_contributions` |
