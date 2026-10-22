# Campus Sentinel — Complete System Overview

**Version:** 1.0.0  
**Status:** Production-ready, locally deployed  
**Stack:** Python 3.11 + FastAPI · Next.js 14 · PostgreSQL 15 · Redis 7

---

## Table of Contents

1. [System Summary](#1-system-summary)
2. [All Available Features](#2-all-available-features)
3. [Frontend Pages](#3-frontend-pages)
4. [REST API Endpoints](#4-rest-api-endpoints)
5. [Technologies Used & Why](#5-technologies-used--why)
6. [Architecture Diagram](#6-architecture-diagram)
7. [Local Access](#7-local-access)

---

## 1. System Summary

Campus Sentinel is an AI-powered predictive smart campus surveillance system. It ingests live RTSP camera streams, runs real-time computer vision and behavioral analytics, predicts threats before they escalate, explains every alert in plain language, and presents everything through a live web dashboard. It is designed for campus security operations centers where operators need to monitor many cameras simultaneously with AI assistance.

---

## 2. All Available Features

### 2.1 Live Camera Stream Processing

| Feature | Detail |
|---|---|
| RTSP / webcam ingest | Supports any RTSP URL, RTMP, or local webcam (`/dev/video0`, index `0`) |
| YOLOv8 object detection | Detects persons, vehicles, bags, and 80 COCO classes per frame |
| ByteTrack multi-object tracking | Assigns persistent track IDs across frames; survives occlusion |
| Frame skip | Configurable — processes every Nth frame to control CPU load |
| Per-camera JPEG WebSocket stream | Browser receives annotated frames at ~10 fps via WebSocket |
| Bounding box annotation | Each detected object drawn with class label, confidence, and track ID |
| Stream lifecycle management | Start / stop / restart individual cameras via API; singleton StreamManager |
| Up to 16 simultaneous cameras | Configurable via `MAX_CAMERAS` setting |

### 2.2 Behavioral Analytics Engine

| Behavior | How It Works |
|---|---|
| **Loitering detection** | Tracks dwell time per person per zone; fires alert after configurable threshold (default 5 min) |
| **Crowd density monitoring** | Counts persons in defined zones; alerts when count exceeds threshold (default 20) |
| **Abnormal movement / running** | Calculates pixel displacement per frame, converts to speed; flags values above threshold |
| **Zone violation** | Restricted zones defined as polygons; alerts when any person enters |
| **Crowd dispersion** | Detects sudden rapid exit of a large group — unusual crowd dynamics |
| **Stationary object** | Unattended bag/object that hasn't moved for N seconds |
| **Fight / aggression** | Detects tight cluster of persons with rapid crossing bounding boxes |

All behaviors are evaluated per-camera, per-zone, per-track. Each fires a structured `BehaviorEvent` that feeds the alert pipeline.

### 2.3 Adaptive Behavioral DNA (ABD)

Each camera learns what is "normal" for its specific context.

- An **IsolationForest** model is trained per camera, per hour-of-day, per day-of-week.
- Feature vector: person count, loitering count, movement speed, crowd density, zone violations.
- Anomaly score from the model adjusts alert severity dynamically.
- Models retrain periodically via Celery beat (configurable schedule).
- ABD training can be triggered manually from the Agents page or via `POST /admin/train-abd`.

### 2.4 Threat Prediction Engine

Predicts threats **before** they escalate using a three-model ensemble.

| Model | Role |
|---|---|
| **Random Forest** | Primary classifier — fast, interpretable, good on tabular features |
| **Gradient Boosting** | Secondary — catches patterns RF misses; best model selected by F1 |
| **LSTM (PyTorch)** | Sequence model over the last 24 time-steps of behavior data; captures temporal build-up |

Threat types predicted: `crowd_incident`, `security_breach`, `unauthorized_access`, `violence`, `suspicious_behavior`.

Each prediction returns a probability score (0–1) and feeds into the Campus Safety Index.

### 2.5 SHAP Explainability

Every alert includes a human-readable explanation of **why** it was raised.

- SHAP values computed per alert using the trained RF/GB model.
- Feature contributions stored as a dict: `{feature_name: contribution_value}`.
- Displayed in the Alerts page as a horizontal bar chart.
- Color coding: red = major contributor (>0.15), amber = moderate (>0.08), blue = minor.
- Summary text auto-generated: "Loitering duration is the primary driver of this threat score."
- Operators can expand any alert row to see the full explanation panel.

### 2.6 Campus Safety Index (CSI)

A single 0–100 score summarizing overall campus risk at any moment.

| Component | Weight | Source |
|---|---|---|
| Behavioral anomaly rate | 30% | ABD anomaly scores across all cameras |
| Active alert density | 25% | Count and severity of open alerts |
| Threat prediction score | 25% | Ensemble model output |
| Crowd density factor | 10% | Max density across zones |
| Historical incident rate | 10% | 7-day rolling incident frequency |

Risk levels: **Safe** (80–100) · **Moderate** (60–79) · **High Risk** (40–59) · **Critical** (0–39)

CSI is recalculated every 5 minutes via Celery beat and broadcast in real-time over WebSocket.

### 2.7 Alert Management

- Alerts created automatically by behavioral/prediction pipeline or manually.
- Severity levels: `low`, `medium`, `high`, `critical`.
- Statuses: `active` → `acknowledged` → `resolved`.
- Operators can acknowledge and resolve alerts directly from the dashboard.
- Alert cooldown prevents duplicate alerts for same camera/type within N seconds.
- Email notifications sent to all admin users when a high/critical alert fires.
- SHAP explanation attached to every alert record.

### 2.8 Incident Management

A formal incident is a documented security event, distinct from a raw alert.

- Create incidents with title, description, type, and severity.
- Types: `security`, `medical`, `fire`, `environmental`, `technical`, `other`.
- Resolve incidents with one click.
- Incident markers appear on the campus map.
- KPI bar: total / open / resolved / critical counts at a glance.
- Filter by status (all / open / resolved).

### 2.9 Campus Map (GIS)

- Interactive Leaflet.js map centered on campus coordinates.
- **Camera markers** — green (online), gray (offline), red (has active alert) with popup details.
- **Heatmap overlay** — density heatmap built from detection coordinates; time-window filter: 1h / 6h / 12h / 24h / 48h.
- **Behavior heatmap** — risk-score weighted heatmap from behavior logs per camera location.
- **Incident markers** — open incidents plotted by linked camera location.
- Layer toggle sidebar: show/hide Cameras, Heatmap, Incidents independently.
- OpenStreetMap tiles (no API key required).

### 2.10 Multi-Agent System

Five autonomous agents communicate via Redis pub/sub channels.

| Agent | Channel | Responsibility |
|---|---|---|
| **Vision Agent** | `vision_events` | Runs YOLO + ByteTrack; publishes detection events |
| **Behavior Agent** | `behavior_events` | Consumes detections; evaluates all behavior rules |
| **Prediction Agent** | `prediction_events` | Builds feature vectors; runs threat prediction ensemble |
| **Decision Agent** | `decision_events` | Aggregates signals; decides whether to create an alert |
| **Response Agent** | `response_events` | Creates DB records, sends emails, broadcasts WebSocket |

Agents run in separate processes and are fully decoupled — any agent can be restarted independently. Status visible on the Agents dashboard page.

### 2.11 Real-Time WebSocket Feeds

| Endpoint | Payload |
|---|---|
| `ws://localhost:8000/api/v1/ws/alerts` | Alert and CSI update events (JSON) |
| `ws://localhost:8000/api/v1/ws/stream/{camera_id}` | Annotated JPEG frame stream for a specific camera |

### 2.12 System Settings (Runtime Tunable)

All thresholds adjustable from the Settings page without restarting the server. Changes stored in Redis and applied immediately.

| Setting | Default | Description |
|---|---|---|
| Loitering threshold | 300s | Seconds before loitering alert fires |
| Crowd density threshold | 20 | Max persons per zone |
| Running speed threshold | 3.0 m/s | Speed above which movement is "abnormal" |
| Alert cooldown | 60s | Min gap between same-type alerts per camera |
| YOLO confidence | 0.50 | Detection confidence cutoff |
| Frame skip | 3 | Process every Nth frame |
| Max cameras | 16 | Hard limit on simultaneous streams |
| ABD sensitivity | 0.8 | IsolationForest contamination factor |
| CSI recalculation interval | 300s | How often CSI score is recomputed |

### 2.13 Analytics & Reporting

- **CSI timeline** — line chart of score over last 6h / 24h / 2d / 7d.
- **Detections by hour** — bar chart of person detection volume across the day.
- **Behavior distribution** — pie chart of behavior event types (loitering vs crowd vs running, etc.).
- **Daily digest email** — automated summary sent to all admins every 24h via Celery beat.
- **Admin seeding** — `POST /admin/seed-data?days=30` generates realistic synthetic training data.

### 2.14 Authentication & Security

- JWT authentication (access token + refresh token).
- `bcrypt` password hashing.
- Role-based access control: `superadmin`, `admin`, `operator`, `viewer`.
- Redis sliding-window rate limiter middleware:
  - Auth endpoints: 10 requests/min, burst 5.
  - All other API: 200 requests/min, burst 30.
  - WebSocket and health endpoints exempt.
- CORS configured; in production, restricted to `ALLOWED_HOSTS`.

### 2.15 Background Task Queue

All long-running work runs off the HTTP request path.

| Task | Schedule |
|---|---|
| `update_threat_predictions` | Every 5 minutes |
| `send_daily_digest_email` | Every 24 hours |
| `train_abd_models` | On-demand or scheduled |
| `send_email_alert` | Triggered per high/critical alert |
| `compute_csi` | On-demand via admin endpoint |

### 2.16 Monitoring (Production)

- **Prometheus** metrics exposed at `/metrics` (FastAPI instrumentator).
- **10 Prometheus alert rules**: backend down, high error rate, high API latency, Redis down, PostgreSQL down, Celery queue backlog, low disk, high CPU, high memory, camera stream stalled.
- **Grafana dashboard**: 12 panels — API request rate, p95 latency, active alerts, CSI gauge, active streams, detections/sec, WebSocket connections, Redis memory, Celery queues, CPU by container, behavior pie, alert severity pie.
- **GitHub Actions CI/CD**: backend tests → frontend build → security scan → Docker build → SSH deploy (5 jobs).

---

## 3. Frontend Pages

| Route | Page | What It Shows |
|---|---|---|
| `/login` | Login | JWT login form; default credentials shown |
| `/` (dashboard) | Dashboard | Live CSI score, camera grid, alert feed, campus map widget, behavior stats |
| `/alerts` | Alerts | Alert list with expandable SHAP explanation panels; ack/resolve actions |
| `/analytics` | Analytics | CSI timeline, detections-by-hour bar chart, behavior pie chart; time-range toggle |
| `/cameras` | Cameras | Camera list, add/edit/delete camera, view live stream per camera |
| `/map` | Campus Map | Full-screen interactive GIS map with heatmap, camera markers, incident markers |
| `/incidents` | Incidents | Create/resolve/filter incidents; KPI stats bar |
| `/agents` | Agents | Multi-agent status, pipeline visualization, Redis channel indicators, ABD trigger |
| `/settings` | Settings | Slider-based settings editor for all 9 thresholds; save/reset |

---

## 4. REST API Endpoints

### Auth
- `POST /api/v1/auth/login` — obtain JWT token pair
- `POST /api/v1/auth/refresh` — refresh access token
- `GET  /api/v1/auth/me` — current user profile
- `POST /api/v1/auth/register` — create new user

### Cameras
- `GET    /api/v1/cameras/` — list all cameras
- `POST   /api/v1/cameras/` — add camera
- `GET    /api/v1/cameras/{id}` — camera detail
- `PUT    /api/v1/cameras/{id}` — update camera config
- `DELETE /api/v1/cameras/{id}` — remove camera
- `POST   /api/v1/cameras/{id}/start` — start stream
- `POST   /api/v1/cameras/{id}/stop` — stop stream

### Alerts
- `GET  /api/v1/alerts/` — list alerts (filterable by severity/status/camera)
- `POST /api/v1/alerts/` — create manual alert
- `GET  /api/v1/alerts/{id}` — alert detail with SHAP explanation
- `POST /api/v1/alerts/{id}/acknowledge` — acknowledge
- `POST /api/v1/alerts/{id}/resolve` — resolve

### Detections
- `GET /api/v1/detections/` — paginated detection history

### CSI
- `GET /api/v1/csi/current` — current CSI score and components
- `GET /api/v1/csi/history` — CSI over time

### Analytics
- `GET /api/v1/analytics/overview` — detections/behaviors/alerts summary
- `GET /api/v1/analytics/hourly` — detections per hour
- `GET /api/v1/analytics/behaviors` — behavior type distribution

### Predictions
- `GET /api/v1/predictions/` — latest threat predictions per threat type

### Incidents
- `GET    /api/v1/incidents/` — list incidents
- `POST   /api/v1/incidents/` — create incident
- `PUT    /api/v1/incidents/{id}` — update
- `POST   /api/v1/incidents/{id}/resolve` — resolve

### Heatmap
- `GET /api/v1/heatmap/detections` — `[[lat, lng, intensity]]` for detection heatmap
- `GET /api/v1/heatmap/behavior` — behavior risk heatmap points

### Settings
- `GET  /api/v1/settings/` — current system settings
- `PUT  /api/v1/settings/` — update settings (stored in Redis)
- `POST /api/v1/settings/reset` — reset to defaults

### Admin
- `POST /api/v1/admin/train-abd` — trigger ABD model training
- `POST /api/v1/admin/compute-csi` — recompute CSI immediately
- `POST /api/v1/admin/seed-data?days=N` — generate synthetic training data
- `POST /api/v1/admin/send-digest` — trigger daily digest email now

### Stream
- `GET /api/v1/stream/status` — all stream states

### WebSocket
- `WS /api/v1/ws/alerts` — real-time alert + CSI events
- `WS /api/v1/ws/stream/{camera_id}` — live annotated JPEG frames

### Health & Metrics
- `GET /health` — backend health check
- `GET /metrics` — Prometheus metrics

---

## 5. Technologies Used & Why

### Backend

| Technology | Version | Why Used |
|---|---|---|
| **Python 3.11** | 3.11.x | Required for torch, ultralytics (YOLOv8). 3.12+ breaks too many ML libraries; 3.11 is the stable ML-production baseline. |
| **FastAPI** | 0.111.0 | Async-native Python web framework. Chosen for automatic OpenAPI docs, native Pydantic v2 integration, WebSocket support, and async/await throughout — essential for handling concurrent camera streams without blocking. |
| **Uvicorn** | 0.30.1 | ASGI server for FastAPI. Uses uvloop (libuv) for near-Node.js I/O performance. The `[standard]` extras add WebSocket and HTTP/2 support. |
| **SQLAlchemy 2.0** | 2.0.30 | Async ORM with asyncpg driver. Version 2.0's `mapped_column` + type annotations make model definitions cleaner and type-safe. Async sessions allow DB queries without blocking the event loop. |
| **Alembic** | 1.13.1 | Database migration tool for SQLAlchemy. Generates versioned migration scripts so schema changes can be applied and rolled back safely. |
| **asyncpg** | 0.29.0 | Pure-Python async PostgreSQL driver. Fastest Postgres driver available for Python — no C extensions, pure asyncio. Used by SQLAlchemy async engine. |
| **psycopg2-binary** | 2.9.9 | Sync Postgres driver for Alembic migrations and Celery tasks (which are synchronous). |
| **Redis (redis-py)** | 5.0.4 | Client for all Redis operations: frame caching, pub/sub between agents, rate limiter counters, settings storage, Celery broker. Single library handles all Redis use cases. |
| **Celery** | 5.4.0 | Distributed task queue. Used for background jobs (threat prediction every 5 min, daily digest email, ABD training) so they never block the API. Celery Beat provides cron-like scheduling. |
| **Pydantic v2** | 2.7.1 | Data validation and serialization. FastAPI is built on Pydantic. v2 is ~10x faster than v1 for validation, uses Rust core. All request/response schemas validated automatically. |
| **pydantic-settings** | 2.3.0 | Reads `Settings` class from environment variables and `.env` file automatically. Type-safe config with zero boilerplate. |
| **python-jose** | 3.3.0 | JWT encode/decode for auth tokens. Supports RS256 and HS256. Used for access token + refresh token pair. |
| **passlib[bcrypt]** | 1.7.4 | Password hashing. bcrypt is the industry standard for user passwords — intentionally slow, salted, resistant to GPU attacks. |
| **python-dotenv** | 1.0.1 | Loads `.env` file into environment for local development. |
| **loguru** | 0.7.2 | Structured logging with color output, automatic tracebacks, and file rotation. Replaces stdlib `logging` with a one-line import. |
| **tenacity** | 8.3.0 | Retry library with exponential backoff. Used for Redis reconnects and RTSP stream reconnects when cameras drop temporarily. |
| **fastapi-mail** | 1.4.1 | Async email sending via SMTP. Wraps aiosmtplib. Alert emails and daily digest emails sent without blocking the event loop. Gracefully skips send if SMTP is unconfigured. |
| **prometheus-fastapi-instrumentator** | 7.0.0 | Automatically instruments all FastAPI routes with request count, latency histograms, and error rates. Exposes `/metrics` for Prometheus scraping. |

### Computer Vision & AI

| Technology | Version | Why Used |
|---|---|---|
| **YOLOv8 (Ultralytics)** | 8.2.18 | State-of-the-art real-time object detection. YOLOv8n (nano) model runs on CPU at acceptable fps for surveillance use. Detects 80 COCO classes. Pre-trained weights, no custom training needed for persons/vehicles. |
| **OpenCV (headless)** | 4.9.0 | Video capture from RTSP streams, JPEG encoding of annotated frames, image preprocessing. Headless variant — no GUI dependencies, suitable for servers. |
| **ByteTrack** | (built-in) | Multi-object tracking algorithm. Assigns consistent track IDs across frames using Kalman filter + Hungarian matching. Enables per-person behavioral analysis across time. |
| **PyTorch** | 2.12.0 | Deep learning framework. Used for: (1) running YOLOv8 inference, (2) LSTM threat prediction model. CPU inference for development; CUDA-ready for GPU deployment. |
| **scikit-learn** | 1.5.0 | ML library for Random Forest, Gradient Boosting, and IsolationForest (ABD anomaly detection). Mature, well-tested, fast for tabular data. |
| **SHAP** | 0.45.1 | SHapley Additive exPlanations — model-agnostic explainability. Computes how much each feature contributed to a specific prediction. The gold standard for ML interpretability, used for explaining every alert. |
| **NumPy** | 1.26.4 | Array operations for frame processing, feature vectors, and model inputs. Foundation of all numerical computation in the AI pipeline. |
| **Pandas** | (via scipy) | Data manipulation for feature extraction from database time-series during model training. |
| **Pillow** | 10.3.0 | Image encode/decode operations, JPEG compression of annotated frames before WebSocket transmission. |

### Database

| Technology | Version | Why Used |
|---|---|---|
| **PostgreSQL 15** | 15.x | Primary relational database. Chosen for JSONB support (stores SHAP explanations, metadata as queryable JSON), UUID primary keys, strong indexing, and TimescaleDB compatibility. |
| **TimescaleDB** (Docker) | — | Time-series extension for PostgreSQL. Used in Docker/production deployments for `detections` and `behavior_logs` tables — automatic partitioning by time, faster time-range queries, data retention policies. Not available in local Homebrew install; tables fall back to standard PostgreSQL. |
| **Redis 7** | 7.x | In-memory data store serving four roles: (1) Celery message broker, (2) Celery result backend, (3) pub/sub bus between agents, (4) settings/frame/track state storage. Redis pub/sub is the glue of the multi-agent system. |

### Frontend

| Technology | Version | Why Used |
|---|---|---|
| **Next.js 14** | 14.2.3 | React framework with App Router. Provides SSR, file-based routing, API routes, and automatic code splitting. App Router enables React Server Components for static parts and client components for interactive widgets. |
| **React 18** | 18.3.1 | UI library. Concurrent mode, Suspense, and the new `use` hook. Zustand + SWR keep the data layer clean without Redux overhead. |
| **TypeScript** | 5.x | Type safety across the entire frontend. Catches API shape mismatches at compile time, not runtime. All component props typed. |
| **TailwindCSS** | 3.4.3 | Utility-first CSS. Zero custom CSS files — all styling inline with Tailwind classes. Dark theme (`bg-[#0d1117]` style) applied consistently. |
| **Radix UI** | Various | Headless, accessible UI primitives: Dialog, Select, Tabs, Toast, Tooltip, etc. Provides correct keyboard navigation, ARIA labels, and focus management without visual opinion — styled with Tailwind on top. |
| **Recharts** | 2.12.6 | React charting library. Used for CSI timeline (line chart), detections-by-hour (bar chart), behavior distribution (pie chart), and SHAP explanation bars. SVG-based, responsive. |
| **Leaflet.js** | 1.9.4 | Interactive map library. Renders OpenStreetMap tiles, camera markers, incident markers, and the detection heatmap. No API key required. Imported client-side only (SSR disabled) because it needs `window`. |
| **leaflet.heat** | 0.2.0 | Leaflet plugin for heatmap overlay. Renders the detection density and behavior risk heatmaps from `[[lat, lng, intensity]]` point arrays. |
| **Zustand** | 4.5.2 | Minimal global state manager. Stores cameras, alerts, CSI, and WebSocket connection status. Far lighter than Redux — no actions, reducers, or middleware boilerplate. |
| **SWR** | 2.2.5 | Data fetching with stale-while-revalidate strategy. API calls automatically refresh in the background; UI shows cached data immediately while fetching new data. |
| **Framer Motion** | 11.1.9 | Animation library. Used for alert row expand/collapse transitions, page fade-ins, and status indicator pulses. |
| **date-fns** | 3.6.0 | Lightweight date formatting. Used in the Header clock and analytics time labels. Chosen over moment.js for tree-shaking — only the functions used are bundled. |
| **Lucide React** | 0.378.0 | Icon library — consistent icon set used throughout navigation, cards, and status indicators. |
| **axios** | 1.7.2 | HTTP client for API calls. Wraps `fetch` with interceptors for automatic JWT header injection and error handling. |

### Infrastructure & DevOps

| Technology | Why Used |
|---|---|
| **Nginx (production)** | Reverse proxy: TLS 1.3 termination, HTTP→HTTPS redirect, rate limiting zones, CSP headers, gzip, WebSocket upgrade. Backend and frontend both behind a single port 443. |
| **Docker + Docker Compose** | Container orchestration for production. `docker-compose.yml` (base) + `docker-compose.prod.yml` (override) pattern allows local dev and production to share most config. |
| **Prometheus** | Metrics collection. Scrapes FastAPI `/metrics`, Redis exporter, PostgreSQL exporter, Celery, Node Exporter, and cAdvisor. 10 alerting rules defined. |
| **Grafana** | Metrics visualization. Pre-provisioned dashboard with 12 panels auto-loaded on startup. |
| **GitHub Actions** | CI/CD pipeline: runs pytest on every push, builds Docker images, pushes to GHCR, and SSH-deploys to production server. 5 parallel jobs. |
| **Homebrew (local)** | macOS package manager. Used to install PostgreSQL@15 and Redis for local development without Docker. |

---

## 6. Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                        BROWSER                               │
│   Next.js 14 Frontend  (localhost:3000)                      │
│   Dashboard · Alerts · Map · Analytics · Settings            │
└───────────┬─────────────────────────────┬────────────────────┘
            │ REST / HTTP                 │ WebSocket
            ▼                             ▼
┌──────────────────────────────────────────────────────────────┐
│              FastAPI Backend  (localhost:8000)                │
│                                                              │
│  Auth │ Cameras │ Alerts │ Analytics │ Heatmap │ Settings    │
│  Incidents │ CSI │ Predictions │ Admin │ Stream              │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │             Rate Limiter Middleware                  │    │
│  └─────────────────────────────────────────────────────┘    │
└────────┬──────────────┬──────────────────────────────────────┘
         │              │
         ▼              ▼
  ┌──────────┐   ┌─────────────────────────────────────────────┐
  │PostgreSQL│   │              Redis                          │
  │  15      │   │                                             │
  │ 13 tables│   │  Celery broker · Pub/Sub bus                │
  └──────────┘   │  Settings · Frames · Track state           │
                 └───────────────┬─────────────────────────────┘
                                 │  Pub/Sub channels
                 ┌───────────────▼─────────────────────────────┐
                 │           Multi-Agent System                 │
                 │                                             │
                 │  Vision Agent  →  Behavior Agent            │
                 │       ↓                ↓                    │
                 │  Prediction Agent → Decision Agent          │
                 │                        ↓                    │
                 │                  Response Agent             │
                 └───────────────────────────────────────────── ┘
                                 │
                 ┌───────────────▼─────────────────────────────┐
                 │              AI Engine                       │
                 │                                             │
                 │  YOLOv8 + ByteTrack (Vision)               │
                 │  Behavioral Rules Engine                    │
                 │  ABD IsolationForest (per-camera)          │
                 │  RF + GB + LSTM Threat Predictor            │
                 │  SHAP Explainer                             │
                 └─────────────────────────────────────────────┘
```

---

## 7. Local Access

| URL | Purpose |
|---|---|
| [http://localhost:3000](http://localhost:3000) | Dashboard (main UI) |
| [http://localhost:3000/login](http://localhost:3000/login) | Login page |
| [http://localhost:8000/api/docs](http://localhost:8000/api/docs) | Interactive API docs (Swagger UI) |
| [http://localhost:8000/health](http://localhost:8000/health) | Backend health check |
| [http://localhost:8000/metrics](http://localhost:8000/metrics) | Prometheus metrics |

**Default credentials:** `admin@campus-sentinel.local` / `Admin@123`

**Stop all services:**
```bash
./scripts/stop-local.sh
```

**Restart after reboot:**
```bash
./scripts/deploy-local.sh
```

**Seed training data and train models:**
```bash
./scripts/seed_and_train.sh
```
