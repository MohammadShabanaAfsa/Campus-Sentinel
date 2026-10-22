# Campus Sentinel — System Architecture

## System Overview

Campus Sentinel is a production-grade AI-powered surveillance system that ingests live RTSP/IP camera streams, runs multi-model computer vision pipelines, applies behavioral analytics, predicts threats via multi-agent AI, and surfaces everything through a real-time Next.js dashboard.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CAMPUS SENTINEL SYSTEM                             │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────┐     RTSP/HTTP      ┌──────────────────────────────────────┐
  │  IP Cameras │ ──────────────────▶│          AI ENGINE LAYER             │
  │  (N feeds)  │                    │                                      │
  └─────────────┘                    │  ┌────────────┐  ┌────────────────┐  │
                                     │  │ YOLOv8     │  │  ByteTrack     │  │
                                     │  │ Detection  │  │  Multi-Object  │  │
                                     │  │ (persons,  │  │  Tracking      │  │
                                     │  │  objects)  │  └────────────────┘  │
                                     │  └─────┬──────┘                      │
                                     │        │                              │
                                     │  ┌─────▼──────────────────────────┐  │
                                     │  │     BEHAVIORAL ANALYTICS       │  │
                                     │  │  - Loitering Detection         │  │
                                     │  │  - Abnormal Movement           │  │
                                     │  │  - Crowd Density               │  │
                                     │  │  - Restricted Zone Violation   │  │
                                     │  └─────┬──────────────────────────┘  │
                                     │        │                              │
                                     │  ┌─────▼──────────────────────────┐  │
                                     │  │   ADAPTIVE BEHAVIORAL DNA      │  │
                                     │  │  - Isolation Forest            │  │
                                     │  │  - Autoencoder Anomaly         │  │
                                     │  │  - Zone Behavior Profiles      │  │
                                     │  └─────┬──────────────────────────┘  │
                                     └────────┼─────────────────────────────┘
                                              │
                                     ┌────────▼─────────────────────────────┐
                                     │       MULTI-AGENT AI SYSTEM          │
                                     │                                      │
                                     │  ┌──────────┐   ┌────────────────┐  │
                                     │  │  Vision  │   │   Behavior     │  │
                                     │  │  Agent   │──▶│   Agent        │  │
                                     │  └──────────┘   └───────┬────────┘  │
                                     │                          │           │
                                     │  ┌──────────────────────▼─────────┐ │
                                     │  │       Prediction Agent         │ │
                                     │  │  - LSTM Threat Forecasting     │ │
                                     │  │  - Random Forest Classifier    │ │
                                     │  └──────────────┬─────────────────┘ │
                                     │                 │                    │
                                     │  ┌──────────────▼─────────────────┐ │
                                     │  │       Decision Agent           │ │
                                     │  │  - CSI Calculation             │ │
                                     │  │  - Alert Prioritization        │ │
                                     │  └──────────────┬─────────────────┘ │
                                     │                 │                    │
                                     │  ┌──────────────▼─────────────────┐ │
                                     │  │       Response Agent           │ │
                                     │  │  - Alert Generation            │ │
                                     │  │  - Email / SMS / Dashboard     │ │
                                     │  └────────────────────────────────┘ │
                                     └────────┬─────────────────────────────┘
                                              │
                          ┌───────────────────┼───────────────────────┐
                          │                   │                       │
                  ┌───────▼──────┐   ┌────────▼───────┐   ┌─────────▼──────┐
                  │  FastAPI     │   │  PostgreSQL     │   │   Redis        │
                  │  Backend     │   │  Database       │   │   Cache +      │
                  │  REST + WS   │   │  (TimescaleDB)  │   │   Pub/Sub      │
                  └───────┬──────┘   └────────────────┘   └────────────────┘
                          │
                  ┌───────▼──────────────────────────────────────────────┐
                  │               NEXT.JS DASHBOARD                      │
                  │                                                      │
                  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
                  │  │  Live    │ │  Alert   │ │  Campus  │ │  Map   │  │
                  │  │ Cameras  │ │  Panel   │ │  Safety  │ │ (Leaflet│  │
                  │  │          │ │          │ │  Index   │ │ /RTSP) │  │
                  │  └──────────┘ └──────────┘ └──────────┘ └────────┘  │
                  │  ┌──────────┐ ┌──────────┐ ┌──────────┐             │
                  │  │Incident  │ │ Threat   │ │Analytics │             │
                  │  │Timeline  │ │Prediction│ │ Charts   │             │
                  │  └──────────┘ └──────────┘ └──────────┘             │
                  └──────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. AI Engine Layer
| Module | Tech | Purpose |
|--------|------|---------|
| Object Detection | YOLOv8 (Ultralytics) | Detect persons, bags, vehicles |
| Multi-Object Tracking | ByteTrack | Track individuals across frames |
| Behavioral Analytics | Custom Python | Loitering, crowd density, anomaly |
| Adaptive Behavioral DNA | Isolation Forest, Autoencoder | Zone-level normal behavior learning |
| Explainability | SHAP, LIME | Alert explanation generation |

### 2. Multi-Agent System
| Agent | Responsibility |
|-------|---------------|
| Vision Agent | Processes raw frames, runs YOLO + tracking |
| Behavior Agent | Analyzes tracks for behavioral patterns |
| Prediction Agent | Forecasts threats using LSTM / RF models |
| Decision Agent | Calculates CSI, prioritizes alerts |
| Response Agent | Dispatches alerts (dashboard, email, SMS) |

### 3. Backend (FastAPI)
- **REST API**: Camera CRUD, alerts, detections, CSI scores
- **WebSocket**: Real-time frame streaming and event push
- **Celery Workers**: Async AI pipeline processing
- **Background tasks**: Agent orchestration loop

### 4. Database (PostgreSQL + TimescaleDB)
TimescaleDB extends PostgreSQL for time-series data (detections, CSI scores, behavior logs).

### 5. Frontend (Next.js 14 + TailwindCSS + ShadCN)
- App Router architecture
- Real-time WebSocket integration
- Leaflet-based campus map
- Recharts/Chart.js analytics

---

## Data Flow

```
Camera RTSP Feed
    │
    ▼
Frame Extractor (OpenCV, 5-10 FPS)
    │
    ▼
Vision Agent → YOLOv8 Detection → ByteTrack Tracking
    │
    ▼
Behavior Agent → Loitering / Crowd / Zone checks → ABD anomaly scoring
    │
    ▼
Prediction Agent → LSTM / RF → Threat probability + level
    │
    ▼
Decision Agent → CSI score update → Alert creation
    │
    ▼
Response Agent → WebSocket push → DB write → Email/SMS
    │
    ▼
Dashboard → Live update
```

---

## Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Computer Vision | YOLOv8, OpenCV, ByteTrack |
| ML / AI | PyTorch, Scikit-Learn, TensorFlow |
| Explainability | SHAP, LIME |
| Backend API | FastAPI, Python 3.11 |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 15 + TimescaleDB |
| Cache / PubSub | Redis 7 |
| Frontend | Next.js 14, TailwindCSS, ShadCN UI |
| Map | Leaflet.js |
| Charts | Recharts |
| WebSockets | FastAPI WebSocket / Socket.IO |
| Containerization | Docker + Docker Compose |
| Reverse Proxy | Nginx |
| Monitoring | Prometheus + Grafana |
| CI/CD | GitHub Actions |

---

## Deployment Architecture

```
Internet
    │
    ▼
┌──────────────────┐
│    Nginx Proxy   │  (SSL termination, load balancing)
└────────┬─────────┘
         │
    ┌────┴────────────────────────────────────┐
    │                                         │
    ▼                                         ▼
┌──────────┐                          ┌───────────────┐
│ Next.js  │                          │  FastAPI App  │
│ Frontend │                          │  (Uvicorn x4) │
│ :3000    │                          │  :8000        │
└──────────┘                          └───────┬───────┘
                                              │
                          ┌───────────────────┤
                          │                   │
                   ┌──────▼──────┐   ┌────────▼──────┐
                   │  PostgreSQL │   │  Redis Cache  │
                   │  :5432      │   │  :6379        │
                   └─────────────┘   └───────────────┘
                          │
                   ┌──────▼──────┐
                   │   Celery    │
                   │   Workers   │
                   │  (AI tasks) │
                   └─────────────┘
```
