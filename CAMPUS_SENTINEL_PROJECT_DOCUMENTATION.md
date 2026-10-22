# Campus Sentinel — AI-Based Smart Campus Surveillance and Safety System

Repository inspection date: 2 October 2026.

This document describes the supplied source files, not a certified production deployment. “Implemented” means code exists; it does not mean every service was started or tested against a real camera during this inspection. Source code takes priority over older architecture descriptions. Credentials and private camera addresses are omitted.

## 1. Project title and overview

Campus Sentinel — AI-Based Smart Campus Surveillance and Safety System.

Campus Sentinel reads video from configured cameras.
It detects people and selected everyday objects in the video.
It follows detected objects across frames using temporary tracking IDs.
Rules examine movement, crowds, restricted areas, and classroom activity.
The system stores alerts and lets users record and resolve incidents.
A web dashboard shows camera feeds, alerts, maps, and safety information.
Campus security staff, administrators, and project demonstrators can use it to review events.
Its objective is to help people notice and investigate possible safety problems; its alerts require human judgment.

## 2. Complete technology stack

Versions below are dependency declarations unless marked “lock.” A dependency being installed does not prove its advertised feature is active.

| Technology | Category | Where used | Why it is used in this implementation |
|---|---|---|---|
| Next.js 14.2.3 | Frontend | `frontend/src/app`, Dockerfile | Builds pages and serves the dashboard; forwards relative API requests. |
| React / React DOM ^18.3.1; lock 18.3.1 | Frontend | Pages and components | Builds the interface from reusable parts. |
| TypeScript ^5; lock 5.9.3; JavaScript | Languages | Frontend source, configuration, tests | TypeScript checks data shapes; JavaScript runs configuration and tests. |
| Tailwind CSS ^3.4.3; lock 3.4.19 | Styling | CSS, Tailwind config, components | Provides reusable styling classes. |
| PostCSS ^8, Autoprefixer ^10.0.1 | Build | Frontend build config | Processes CSS. |
| Leaflet ^1.9.4; lock 1.9.4 | Map | Both campus map components | Draws maps and markers. |
| OpenStreetMap | Map data | Tile URL in map components | Supplies background map images. |
| leaflet.heat ^0.2.0 | Map | Enhanced map | Draws a density layer. |
| react-leaflet ^4.2.1; lock 4.2.1 | Declared dependency | `package.json` | Listed React map wrapper; inspected map components use Leaflet directly. |
| Axios ^1.7.2; lock 1.18.1; browser fetch | Networking | `src/lib/api.ts`, pages and map | Calls backend REST endpoints. |
| Native WebSocket; Python websockets 12.0 | Realtime | Realtime hook, camera sockets, backend endpoints | Keeps an open connection for events and camera frames. |
| socket.io-client ^4.7.5 | Declared dependency | `package.json` | Listed, but the inspected connection code uses native WebSocket. |
| Zustand ^4.5.2; lock 4.5.7 | Frontend state | `useAppStore.ts` | Shares cameras, alerts, CSI, and classroom state between components. |
| Recharts ^2.12.6; lock 2.15.4 | Charts | Analytics and classroom components | Draws graphs. |
| Lucide React ^0.378.0, Radix UI packages | Interface | Components and manifest | Icons and interface controls. Radix packages have individual declared versions. |
| date-fns ^3.6.0 | Dates | Timeline and pages | Formats event times. |
| Framer Motion ^11.1.9; lock 11.18.2 | Declared animation dependency | Manifest | Listed animation helper; the inspected CSI gauge uses Recharts. |
| SWR ^2.2.5; lock 2.4.2 | Declared dependency | Manifest | Available data-fetching helper; inspected key dashboard widgets use effects and timed polling. |
| Python 3.11 | Backend language | Python Docker images and local setup | Runs APIs, vision processing, and tasks. |
| FastAPI 0.111.0 / Uvicorn 0.30.1 | Backend server | `backend/app/main.py`, Dockerfile | Provides APIs and serves HTTP/WebSocket connections. |
| Pydantic 2.7.1 / pydantic-settings 2.3.0 | Validation/config | Schemas and `core/config.py` | Checks request data and loads environment settings. |
| SQLAlchemy 2.0.30 | Database access | Models, endpoints, services | Maps Python objects to database rows. |
| Alembic 1.13.1 | Migration setup | `backend/alembic` | Migration tooling is configured, but no migration revision directory was found. |
| asyncpg 0.29.0 / psycopg2-binary 2.9.9 | PostgreSQL drivers | Async API and sync task connections | Lets Python communicate with PostgreSQL. |
| PostgreSQL 15 / TimescaleDB `latest-pg15` | Database | Compose, `init.sql` | Stores permanent records; TimescaleDB organizes time-based data. |
| Redis server 7-alpine / Python redis 5.0.4 | Temporary state/messages | Redis clients, vision, agents, tasks | Stores latest frames and temporary state, distributes messages, and supports queues. |
| Celery 5.4.0 / Flower 2.0.1 | Tasks/monitoring | Worker, Beat, Flower services | Runs queued tasks; Flower shows worker information. |
| Ultralytics 8.2.18 / YOLOv8n | Object detection | `ai-engine/vision/detector.py` | Finds object boxes using an existing detector. |
| OpenCV headless 4.9.0.80 | Video | Camera manager, stream manager, annotation | Opens streams, reads frames, draws boxes, and creates JPEG images. |
| NumPy 1.26.4 / Pillow 10.3.0 | Images/numerical dependency | AI code and requirements | Handles arrays; Pillow is also listed for image support. |
| MediaPipe 0.10.14 | Face/pose AI | Classroom face/pose analyzer | Supplies face landmarks and body pose landmarks. |
| PyTorch 2.3.0 / torchvision 0.18.0 | Deep learning | YOLO dependency and LSTM trainer | Runs neural models; provides the separate LSTM training code. |
| scikit-learn 1.5.0 | Machine learning | ABD and threat trainers | Trains Isolation Forest, Random Forest, and Gradient Boosting models. |
| SciPy 1.13.0 / pandas 2.2.2 | Declared numerical dependencies | Requirements | Listed analytics support; do not imply that tracking uses SciPy assignment. |
| SHAP 0.45.1 / LIME 0.2.0.1 | Declared explanation dependencies | Requirements | Installed, but live alert explanation code builds manual values rather than calling these libraries. |
| python-jose 3.3.0 / passlib 1.7.4 / bcrypt 4.0.1 | Security | `core/security.py` | Signs JWTs and hashes passwords. |
| FastAPI-Mail 1.4.1 | Email | `email_service.py` | Contains SMTP alert and digest sending code with a logging fallback. |
| Prometheus client 0.20.0 / instrumentator 7.0.0 | Monitoring | `/metrics`, infrastructure | Exposes server measurements for collection. |
| Prometheus / Grafana (`latest`) | Monitoring | Compose and provisioning files | Collects and displays measurements; images are not fixed to exact releases. |
| Docker / Docker Compose / Nginx `alpine` | Deployment | Dockerfiles, Compose, proxy configs | Packages services and routes browser/API traffic. |
| FFmpeg | Video system dependency | Backend Docker images | Installs video support tools. |
| Loguru 0.7.2 | Logging | Backend, AI, agents | Records operational messages and errors. |
| python-dotenv 1.0.1, email-validator 2.1.1 | Configuration/validation | Requirements and settings ecosystem | Supports environment and email handling. |
| python-dateutil 2.9.0, pytz 2024.1, tenacity 8.3.0, aiofiles 23.2.1 | Utility dependencies | Requirements | Declared date, retry, and file helpers; presence alone is not a implemented feature. |
| protobuf >=4.25.3,<5 / attrs >=19.1.0 | MediaPipe dependencies | Requirements | Supports the pinned MediaPipe integration. |
| pytest 9.1.1, pytest-asyncio 1.4.0, Playwright 1.63.0, Node test runner | Verification | Development requirements, tests, browser scripts | Checks rules, tracking, CSI, recovery, and browser behavior. |
| GitHub Actions | Automation config | `.github/workflows/ci.yml` | Defines tests, builds, image publishing, and deployment; execution was not verified. |

Version sources: [frontend manifest](frontend/package.json), [frontend lock](frontend/package-lock.json), [Python requirements](backend/requirements.txt), [development requirements](backend/requirements-dev.txt), and Dockerfiles. No project `pyproject.toml`, yarn lock, or pnpm lock was found in the inspected source inventory.

## 3. System architecture

```text
Saved camera source in PostgreSQL
  -> OpenCV CameraManager
  -> StreamManager thread in the FastAPI process
  -> YOLOv8n detection -> simplified IoU tracking -> annotated JPEG
       |                              |
       |                              +-> Redis latest frame -> camera WebSocket
       +-> sampled detections -> PostgreSQL
       +-> periodic tracks -> Celery behavioral rules -> alert task
       +-> Redis agent bus -> Behavior -> Prediction -> Decision -> Response
       +-> classroom camera: MediaPipe -> classroom rules -> metrics/alert task

Alert task -> PostgreSQL alert -> CSI calculation -> Redis messages
User-created incident -> PostgreSQL incident -> CSI calculation -> Redis messages
Redis pub/sub -> FastAPI event WebSocket -> Next.js dashboard
PostgreSQL -> REST APIs -> dashboard polling/history/charts
```

- **Saved source:** Each camera has its own `rtsp_url` field. Despite its name, the field can hold an HTTP video URL or a local device number.
- **OpenCV:** Opens the source and reads images. Failed sources are retried.
- **StreamManager:** Starts one capture thread per camera within each API process. It performs detection and tracking directly, rather than sending every frame to Celery.
- **Detector:** Returns object categories, confidence values, and boxes.
- **Tracker:** Matches overlapping boxes and maintains temporary IDs within one camera.
- **Analysis:** Behavioral tasks evaluate rules; classroom cameras also examine face/pose signals. A separate Redis bus connects the project’s Python agents; these are program modules, not conversational language models.
- **Storage:** PostgreSQL keeps durable records. Redis keeps short-lived frames, state, and messages.
- **Delivery:** WebSockets push events and frames; REST requests load lists and history. Polling helps recover from missed updates.

Sources: `backend/app/main.py`, `ai-engine/vision/stream_manager.py`, `agents/`, and `backend/app/services/tasks/`.

## 4. AI models used

| Item | Actual finding |
|---|---|
| Detection model | YOLOv8n, the nano object-detection variant. |
| Weight files found | `yolov8n.pt` in the root and `backend/yolov8n.pt`. No differently named custom YOLO checkpoint was found. |
| Configuration path | `YOLO_MODEL_PATH=models/weights/yolov8n.pt` in configuration/local environment. |
| Live path | StreamManager calls `YOLODetector.get_instance()` without settings arguments, so its defaults are `yolov8n.pt`, `cpu`, and confidence `0.5`. |
| Confidence | Detections below 0.5 are filtered by the detector’s model call. Environment changes are not automatically passed into this live constructor. |
| Device | CPU by default; detector supports an explicit device argument and calls `model.to(device)`. Changing `YOLO_DEVICE` alone does not change the inspected stream path. |
| Frame skip | `settings.FRAME_SKIP`, default/local value 3: processes every third captured frame. |
| Retained categories | person, bicycle, car, motorcycle, backpack, handbag, suitcase, laptop. Other detections are discarded by `TARGET_CLASSES`. |
| Failure | Model load/inference errors are logged and detection returns an empty list. A live image does not prove the AI model loaded. |

YOLO is used as an existing pretrained detector. There is no evidence here of campus-specific YOLO fine-tuning, YOLOv8s use, or YOLO sleeping/talking classes.

Classroom monitoring also loads MediaPipe Face Mesh and the lite Pose model (`model_complexity=0`) with minimum detection confidence 0.5. These estimate landmarks; Python rules interpret the signals.

Additional trainers exist for Isolation Forest anomaly profiles, Random Forest/Gradient Boosting threat prediction, and a PyTorch LSTM. The live predictor loads RF-style pickle bundles or falls back to rules; it does not load/run the LSTM.

## 5. Dataset and training data

The repository contains no project YOLO `model.train(...)` call, campus image dataset configuration (`data.yaml`/`dataset.yaml`), training notebook, or custom YOLO classes found by source inspection. The `model.train()` call in the LSTM trainer switches a PyTorch network into training mode; it is not YOLO training.

Standard YOLOv8n detection weights are pretrained on COCO, a large collection of images labeled with common object categories, including people. This identifies the standard model’s origin; it is not evidence of a campus data collection or a verified provenance checksum for the two local binaries. See [Ultralytics’ YOLOv8 documentation](https://docs.ultralytics.com/models/yolov8/).

**Training code does exist for other models:**

| Model | Training input | What the repository proves |
|---|---|---|
| ABD Isolation Forest | Aggregated `behavior_logs` over the last 30 days, split by camera/hour/day | Trainer fits and saves models when at least 10 samples exist for a slot. Missing models produce anomaly score 0.0. |
| Random Forest and Gradient Boosting | Nine numeric features from database behavior logs; binary label from future risk >0.5 | Both are trained and one selected model is saved. Empty input uses synthetic random data. |
| LSTM | Sequences of 10 feature vectors; database or synthetic input | Training/saving code exists; inference integration is absent. |
| Synthetic data seeder | Generated behavior records for camera zone types | Development/test data, not observed student behavior or a labeled campus video dataset. |

`scripts/seed_and_train.sh` seeds generated records and invokes the ABD and RF trainers. No project `.pkl` artifacts were found in the inspected inventory, so a completed training run is not established. Container volumes or an external `/app/models` directory may differ from this folder.

YOLO detects a **person**. Movement rules interpret running, acceleration, zigzag motion, and loitering. MediaPipe signals plus timing rules estimate sleeping/talking candidates. None is proof that YOLO was trained on “sleeping students.”

## 6. Behavioral analysis

Thresholds below come from executable analyzer code, not just `.env` names.

| Behavior | How detected / data used | Actual threshold | Severity | Limitations |
|---|---|---|---|---|
| Running | Change in a person’s box center divided by elapsed time | Speed >15 with at least 3 velocity samples | medium | Computation is pixels/second although constant says pixels/frame. Not the configured 3.0 m/s. |
| Sudden acceleration | Recent speed average compared with previous average | Ratio >3; at least 5 speed samples | high | Previous slice may have fewer than 5 values yet is divided by 5. Sensitive to timing and ID errors. |
| Zigzag motion | Counts consecutive direction changes >90 degrees | At least 10 directions and at least 5 large changes | medium | Angles are not wrapped; up to 20 samples remain in the deque. |
| Loitering | Time seen plus spread of remembered person centers | >=300 seconds and movement radius <=0.05 | medium; high if duration-based risk >0.7 | Centers are raw pixels but 0.05 is described as normalized: units do not match. |
| Crowd density | Counts person tracks in camera view | >=20; high if count/20 >1.5 | medium/high | Counts camera tracks, not calibrated persons per square meter or individual zones. |
| Crowd surge | Count growth in recent history | >50% growth in 30 seconds; current count >5; at least 3 samples; initial count nonzero | high | Missed detections and stale tracks can change counts. |
| Tight crowd formation | Average distance from person centers to their common center | >=4 people and average distance <96 pixels (0.05×1920) | high | Fixed pixel scale; clustering is not confirmed fighting. |
| Restricted zone entry | Tests normalized person center inside stored polygon | Inside an active zone; one alert per track entry | configured zone level, default high | No person authorization/identity check; center does not represent feet location. |
| Sleeping candidate | Closed-eye landmark ratio OR head-down pose with no detected face, sustained | Eye aspect ratio <0.20; default duration 15 seconds | low | Bowing/reading can look similar; missing landmarks reset the candidate. |
| Talking candidate | Variation of mouth aspect ratio over up to 30 samples | At least 8 samples; standard deviation >=0.035; default duration 8 seconds | low | No audio analysis. Old mouth samples remain when a new signal is missing. |
| Missing students | Person track count below configured expected count | Shortfall for >=20 seconds; default expected 30 | high if missing >=max(3, expected×0.3), otherwise medium | Caller passes all person tracks before excluding the guessed faculty member; not named attendance. |
| Low faculty engagement | Heuristic teaching-zone, movement, and facing score | Score <30 for >=30 seconds while guessed faculty present | medium | Faculty role is guessed; facing-camera geometry depends on placement. |
| Low class attention | Composite Class Attention Index | Score <40 for >=30 seconds | medium | Rule score based on uncertain counts and face signals, not measured learning. |

Movement rules alert once per tracked person until that state disappears. Crowd density has its own 60-second cooldown. The shared alert task also applies a per-camera/per-alert-type cooldown, default 60 seconds.

Faculty engagement = `100 × (0.45×zone_ratio + 0.30×movement_ratio + 0.25×facing_ratio)`. Without a teaching zone the zone ratio is 0.6; movement uses position spread/400 capped at 1, with 0.5 for too few samples. Missing facing signals contribute 0.5.

Class Attention Index (CAI) = `100 × (0.25×attendance_ratio + 0.50×attentive_ratio + 0.25×faculty_component)`. Attentive count subtracts sleeping+talking counts, capped by the present count. Missing faculty contributes 0.5; an empty room has attentive ratio 1. CAI labels are excellent >=80, good >=60, fair >=40, otherwise poor. CAI is separate from CSI.

Threat fallback rules flag crowd >20, zone violations >0, or anomaly >0.7. A potential-fight rule requires crowd >15 and formation density >0.5, but the inspected BehaviorAgent always supplies formation density 0.0. Therefore that path is not a working fight detector in this integration. Opposite-crowd movement and inactivity are mentioned or plausible extensions, but no active analyzer for them was found.

Sources: `ai-engine/behavioral/`, `ai-engine/classroom/`, `ai-engine/prediction/threat_predictor.py`.

## 7. Student versus faculty

“Currently YOLOv8 detects people but does not inherently know whether a person is a student or faculty member.”

There is a **faculty-selection heuristic**, not a trained role classifier. With a teaching polygon, the person with most accumulated time in it is selected. Without a polygon, tracks seen for more than five seconds are considered and the one nearest the top of the image is selected. Other people are treated as student candidates by classroom logic.

This cannot reliably distinguish a student, faculty member, visitor, or security worker. Temporary track IDs are not college IDs. Reliable identification would need an authorized mapping such as RFID, QR/ID cards, or a college attendance/identity database. Those integrations are future work.

## 8. Camera system

When the cameras table is empty, startup creates these two records:

| Camera | Source | Role |
|---|---|---|
| General Entrance | `str(CAMERA_FALLBACK_INDEX)`, default `0` | Local webcam; general monitoring. |
| Classroom | `IP_CAMERA_URL` | Android IP Webcam HTTP video; classroom pipeline enabled. |

Existing records are preserved; changing the environment does not recreate them. Users can add cameras with their own saved URLs. OpenCV supports the configured HTTP/IP/RTSP sources and numeric local devices.

```text
Android phone camera -> Wi-Fi -> HTTP /video stream
  -> backend OpenCV -> YOLO/tracking -> classroom analysis -> dashboard
```

`CameraManager` supports optional local-webcam fallback, but the active StreamManager passes `enable_fallback=False`. A disconnected classroom phone therefore does not silently switch to the entrance webcam.

`CAMERA_RECONNECT_DELAY_SECS` defaults to 5 seconds inside CameraManager. StreamManager separately waits a hardcoded 10 seconds between reopen attempts. A health thread checks every 30 seconds and restarts a running stream with frames older than 60 seconds.

Closing the dashboard does not stop capture: the backend owns the camera. A running backend/container can keep the webcam light on. Stop sets a thread event; the capture loop releases `VideoCapture` when it exits or reconnects. FastAPI shutdown requests all streams to stop, then closes Redis/database resources. It does not join all capture threads before ending shutdown, so release may wait for a blocked read; restart joins for up to 35 seconds and refuses a duplicate if the old thread remains alive.

## 9. Database

The configured database is PostgreSQL. Docker uses PostgreSQL 15 with TimescaleDB, an extension for time-based tables. Async APIs use asyncpg; synchronous workers use psycopg2 through SQLAlchemy.

| Table / model | Purpose | Important fields |
|---|---|---|
| users / User | Login and application roles | id, email, username, role, hashed_password, is_active, last_login |
| cameras / Camera | Camera configuration/status | id, name, rtsp_url, latitude, longitude, zone_type, status, fps, resolution |
| restricted_zones / RestrictedZone | Camera-view polygons | camera_id, name, zone_points, alert_level, is_active, created_by |
| detections / Detection | Sampled object findings | camera_id, detected_at, object_class, confidence, bbox coordinates, frame_number, optional track_id |
| behavior_logs / BehaviorLog | Behavior history | camera_id, logged_at, behavior_type, person_count, risk_score, duration_secs, details |
| alerts / Alert | Automatic warnings | camera_id, alert_type, severity, status, title, threat_score, explanation, metadata, acknowledgment/resolution |
| incidents / Incident | Manually recorded incidents | title, incident_type, severity, status, camera_id, location, assigned_to, resolved_by |
| abd_profiles / ABDProfile | Normal-pattern model metadata | camera_id, hour_of_day, day_of_week, averages, sample_count, model_path, last_trained |
| csi_scores / CSIScore | Periodic safety history | recorded_at, camera_id, overall/component scores, risk_level, contributing_factors |
| predictions / Prediction | Threat outputs | predicted_at, camera_id, threat_type, probability, threat_level, model_version, was_accurate |
| classroom_configs / ClassroomConfig | Per-camera classroom rules | camera_id, expected_students, teaching_zone, sleeping/talking durations |
| classroom_metrics / ClassroomMetric | Classroom time history | counts, faculty_present, engagement score, attention_index, details |
| track_history (SQL only) | Intended movement history | camera_id, track_id, recorded_at, position, velocity, speed |
| notifications (SQL only) | Intended delivery records | user_id, alert_id, channel, status, sent_at |
| system_events (SQL only) | Intended operational history | event_type, source, message, metadata, created_at |

The last three tables exist in `init.sql`; no corresponding active ORM persistence flow was found. Detection persistence writes object boxes but not the optional detection track ID. Do not claim a complete track-history or notification audit feature.

One camera can have many zones, detections, behaviors, alerts, predictions, and classroom metrics. It has at most one classroom configuration. Users are referenced by acknowledgment, zone creation, and incident assignment/resolution fields. Alerts and incidents have no direct conversion/link relationship in the inspected implementation.

`init.sql` creates Timescale hypertables, detection/CSI materialized summaries, and retention policies: detections/predictions 30 days, behavior/classroom metrics 90 days, CSI 180 days, track history 7 days. These require TimescaleDB. Alembic is configured, but no revision files were found; `alembic upgrade head` alone does not supply this schema.

Important mismatch: SQL’s `csi_scores.risk_level` constraint omits `low_risk`, while the canonical calculation can return it. Periodic score inserts may fail in that band. SQL behavior type restrictions also cause the agent to skip some generated types, including crowd density/restricted zone, when saving behavior logs.

Sources: `backend/app/models/`, `infrastructure/postgres/init.sql`, `backend/alembic/env.py`.

## 10. Redis

Redis is a fast store used for short-lived data and messages. It is actively used here, not merely configured.

| Use | Concrete code behavior |
|---|---|
| Camera images | `camera:{id}:latest_frame`, base64 JPEG, expires in 10 seconds. |
| Tracks / heartbeat | Tracks expire in 10 seconds; heartbeat in 60 seconds. |
| Latest behavior/classroom state | Cached for 120 seconds. |
| CSI / predictions | CSI cache 120 seconds; scheduled prediction cache 360 seconds. |
| Pub/sub | `camera_events`, `alerts_channel`, `csi_updates`, `classroom_updates` forward messages to WebSockets. |
| Agent communication | `bus:tracks`, `bus:behaviors`, `bus:threats`, `bus:decisions`, and related channels. |
| Celery | Redis URL is both task broker and result backend; queues are ai_tasks, alerts, analytics. |
| Alert cooldown | `alert_cooldown:{camera}:{type}` suppresses repeat warning creation. |
| Rate limiting | Redis sorted sets count requests in a sliding time window. |
| Settings | Endpoint intends to save `campus:settings`; currently blocked by a missing Redis helper import. |

Pub/sub is not permanent storage and does not replay messages to disconnected browsers. REST requests load persisted records again; polling frequency depends on the widget.

## 11. Frontend

Next.js App Router supplies these pages. Components render the panels, hooks manage connections, Axios helpers make requests, and Zustand shares state.

| Page | What code provides |
|---|---|
| `/` | Entry page routing into the application. |
| `/login` | Email/password login and session storage. |
| `/dashboard` | CSI, alerts, cameras, map, predictions, timeline, analytics. |
| `/cameras` | Camera list/add/edit/delete, start/stop/restart, live modal, zone drawing. |
| `/classroom` | Classroom overview, configuration, latest metrics, trends, attention gauge. |
| `/alerts` | Warning filters and acknowledgment/resolution; explanation panel. |
| `/incidents` | Record, list, and resolve incidents. |
| `/map` | Enhanced map with camera, heatmap, and incident layers. |
| `/analytics` | API-backed charts and summaries. |
| `/agents` | Agent diagram, static status cards, ABD training trigger. |
| `/settings` | Settings form linked to backend settings endpoints; current backend helper issue limits it. |

Frontend middleware checks the session cookie for protected-page routing. Backend authentication remains necessary; a browser routing check is not API authorization.

## 12. Dashboard: real data versus placeholders

| Component | Data source | What is real / what needs qualification |
|---|---|---|
| Campus Safety Index | `/api/v1/csi/campus`, event messages, 5-second polling | Database alert+incident calculation. Starts loading; retains the last valid score as stale after failure. |
| Active alerts | Active-alert list on mount and `new_alert` events; other views use stats API | Persisted warnings; this widget has no periodic list refresh, and state insertion does not deduplicate. |
| Live cameras | Camera API, stream state, camera WebSocket | Saved camera records and latest JPEGs; actual source/model connectivity must be checked. |
| Campus map | Shared campus config and camera coordinates | Real configured locations; default camera seeding does not supply coordinates. |
| AI Threat Predictions | Predictions API every 30 seconds; realtime handler | Database predictions can be heuristic outputs or trained model outputs. Not validated future-event forecasts. |
| Incident Timeline | First 10 alerts in Zustand | Despite its title, this dashboard widget shows alerts, not the incidents table. |
| 24h Analytics | Analytics summary and behavior-distribution endpoints | Counts database rows, including synthetic rows if seeded. Detection rows are repeated sampled objects, not unique people. |
| AI Agents page | `STATIC_AGENTS` | “Running” labels and channel lights are hardcoded, not live health measurements. “168 models/camera” describes possible slots, not proven trained models. |
| Email digest | DB query plus default | Missing average CSI is replaced with 75.0 in digest code; this is a fallback, not measured safety. |
| Alert explanation | Alert task’s manual contribution dictionary | Marked SHAP in payload, but no SHAP/LIME computation is performed. |

There is no blanket fake-dashboard generator in the inspected core widgets. Empty states/default zero counts and retained old values still need to be distinguished from successful live queries.

## 13. Campus Safety Index (CSI)

Canonical calculation: `backend/app/services/safety_index.py`. It reads both alerts and incidents created within the last 24 hours. Each database record is counted once, but separately recording the same event as an alert and an incident gives two penalties.

```text
Severity base penalty: low=2, medium=5, high=10, critical=20
age_hours = max(0, hours since record creation)
age_factor = max(0, 1 - age_hours/24)
status_factor = 0.25 for resolved/closed/dismissed; otherwise 1.0
record penalty = base penalty × age_factor × status_factor
CSI = clamp(round(100 - sum of penalties), 0, 100)
```

Unknown severities use a medium penalty. Missing timestamps are skipped. Acknowledged records still have full impact. Resolved records retain one quarter of their remaining impact, rather than disappearing immediately. Records aged 24 hours or more contribute nothing.

| Score | Label |
|---|---|
| 90–100 | SAFE (`safe`) |
| 75–89 | LOW RISK (`low_risk`) |
| 60–74 | MODERATE (`moderate`) |
| 40–59 | HIGH RISK (`high_risk`) |
| 0–39 | CRITICAL (`critical`) |

100 means no recent stored penalties; 0 means penalties reach the score floor. This does not prove physical safety or healthy camera coverage.

Example: one newly created high alert gives 90. At 12 hours its impact is 5, giving 95. If resolved at that age, impact becomes 1.25 and the rounded score is 99.

Crowd, loitering, access, and anomaly component scores use the same formula on matching event types. The overall score also includes types outside those component groups. Scheduled tasks save campus/per-camera snapshots; the campus endpoint calculates directly from current records. The history field `historical_score` is set equal to the overall score by the task, not a separate learned measure.

## 14. Alert system

```text
Detections -> tracks -> behavioral/classroom rule
  -> condition sustained/reached -> alert task queued in Celery
  -> Redis cooldown check -> PostgreSQL Alert inserted
  -> canonical CSI recalculated -> Redis alert/CSI messages
  -> FastAPI event WebSocket -> dashboard
```

The prediction branch instead evaluates predicted probability against `THREAT_ALERT_THRESHOLD`, default 0.5, before dispatch. Alert severities are low, medium, high, critical. New alerts default to active; acknowledgment/resolution records are updated through API routes.

`ALERT_COOLDOWN_SECS=60` applies to the same camera and alert type, so different people may share suppression. The existence check and later cooldown write are not one atomic operation; simultaneous task processes can race. Stateful behavioral analyzers also have their own one-shot/cooldown behavior.

SMTP dispatch code exists for administrator recipients. A logging fallback is used if mail cannot initialize; real delivery depends on valid mail configuration and a running worker. No implemented SMS delivery was found.

## 15. Incident system

- **Detection:** An object observation in an image, with a box and confidence.
- **Alert:** An automatically stored warning from a rule or prediction decision.
- **Incident:** A separately recorded issue with type, severity, status, assignment, and optional camera/location.

Incidents are created through `POST /api/v1/incidents/`, not automatically created for every detection/alert. They default to open. Resolve sets the status and records the user/time. Update and delete endpoints also exist. Mutations commit their database change before attempting CSI publication; a publication failure does not undo the record.

Both incident and alert records affect CSI. Resolving an incident reduces its CSI impact to one quarter while its creation time continues to age.

## 16. Realtime communication

| Mechanism | Actual route/behavior |
|---|---|
| Event WebSocket | `ws://localhost:8000/api/v1/ws/events?token=<hidden>` |
| Camera WebSocket | `ws://localhost:8000/api/v1/ws/camera/{camera_id}/stream?token=<hidden>` |
| Browser environment | `NEXT_PUBLIC_WS_URL`, default `ws://localhost:8000`, is the base URL. |
| Event recovery | Reconnect delay 3 seconds; ping every 25 seconds; server receive timeout 30 seconds. |
| CSI polling | Every 5 seconds; backend health every 10 seconds. |
| Camera frames | Server reads Redis and sends latest base64 JPEG approximately every 0.1 seconds. This may resend the same frame. |
| Camera recovery | Browser retries after 3 seconds and caps failed retries at five; manual retry and session cleanup exist. |

Backend event -> Redis publication -> FastAPI listener -> browser WebSocket message -> shared state update -> panel redraw. No Server-Sent Events route was found. REST polling is also used across widgets.

Known mismatch: scheduled `predictions_update` sends a dictionary grouped by camera, while the frontend prediction state/component expects a list. REST polling is the usable recovery path; seamless prediction pushes should not be claimed without fixing/testing the payload.

## 17. REST API

All grouped paths below start with `/api/v1`. `{id}` stands for the named identifier in the source. These are actual registered routes; there is no separate `/dashboard` API group.

| Group | Method | Endpoint | Purpose |
|---|---|---|---|
| Authentication | POST | `/auth/login` | Email/password login; return tokens. |
| Authentication | POST | `/auth/register` | Create account. |
| Authentication | GET | `/auth/me` | Read current account. |
| Cameras | GET, POST | `/cameras/` | List/create cameras. |
| Cameras | GET, PATCH, DELETE | `/cameras/{camera_id}` | Read/update/delete camera. |
| Cameras | GET, POST | `/cameras/{camera_id}/zones` | List/create camera polygons. |
| Alerts | GET | `/alerts/` | Filter/list alerts. |
| Alerts | GET | `/alerts/stats` | Alert counts. |
| Alerts | GET, PATCH, DELETE | `/alerts/{alert_id}` | Read/change status/delete warning. |
| Incidents | GET, POST | `/incidents/` | List/create incident records. |
| Incidents | PATCH | `/incidents/{incident_id}/resolve` | Resolve an incident. |
| Incidents | PATCH, DELETE | `/incidents/{incident_id}` | Edit/delete incident. |
| Dashboard/CSI | GET | `/csi/campus` | Calculate current campus CSI. |
| Dashboard/CSI | GET | `/csi/latest` | Latest stored scores. |
| Dashboard/CSI | GET | `/csi/history` | Stored CSI history. |
| Classroom | GET | `/classroom/` | Classroom overview. |
| Classroom | GET, PUT | `/classroom/{camera_id}/config` | Read/update classroom rules. |
| Classroom | GET | `/classroom/{camera_id}/metrics/latest` | Latest classroom measurement. |
| Classroom | GET | `/classroom/{camera_id}/metrics/history` | Classroom history. |
| Analytics | GET | `/analytics/summary` | Counts within requested hours. |
| Analytics | GET | `/analytics/detections/by-hour` | Hourly detection counts. |
| Analytics | GET | `/analytics/behavior/distribution` | Behavior category counts. |
| Detections | GET | `/detections/` | Query stored detections. |
| Predictions | GET | `/predictions/` | Query stored threat outputs. |
| Map | GET | `/heatmap/detections` | Detection density points. |
| Map | GET | `/heatmap/behavior` | Risk-weighted behavior points. |
| Streams | GET | `/streams/status` | Per-camera process state. |
| Streams | POST | `/streams/{camera_id}/start` | Start capture. |
| Streams | POST | `/streams/{camera_id}/stop` | Request capture stop. |
| Streams | POST | `/streams/{camera_id}/restart` | Stop/reopen capture. |
| Streams | GET | `/streams/{camera_id}/snapshot` | Latest image from Redis. |
| Streams | GET | `/streams/{camera_id}/tracks` | Latest track metadata. |
| Settings | GET, PUT | `/settings/` | Read/update settings (current helper issue). |
| Settings | POST | `/settings/reset` | Reset stored settings. |
| Admin | POST | `/admin/train-abd` | Queue ABD training. |
| Admin | POST | `/admin/compute-csi` | Queue CSI snapshots. |
| Admin | POST | `/admin/seed-data` | Generate development data. |
| Admin | POST | `/admin/send-digest` | Build/send digest email directly in the request. |

Outside the prefix: `GET /health`, `GET /api/docs`, `GET /api/redoc`, `GET /api/openapi.json`; `GET /metrics` when monitoring is enabled. Health returns configured status/version/environment; it does not test database, Redis, or cameras. No token refresh route was found despite issuing refresh tokens.

Source: `backend/app/api/v1/router.py` and every endpoint file in its `endpoints/` directory.

## 18. Campus map

Leaflet loads OpenStreetMap tiles. The campus is named Sreyas Institute of Engineering and Technology in `frontend/src/lib/campus.ts`. Its center uses validated `NEXT_PUBLIC_CAMPUS_LAT`, `NEXT_PUBLIC_CAMPUS_LNG`, and zoom values, with hardcoded defaults there. Exact coordinates are intentionally not repeated in this document.

Camera positions come from database latitude/longitude and can be entered in the add/edit form. Missing, invalid, or out-of-range positions are hidden with a warning instead of moved to the campus center. Default seed records lack positions.

- Green camera markers: status online.
- Gray camera markers: every other status, including error/offline.
- Enhanced map incident pins: red warning markers for open incidents; separate from camera status colors.
- Shared building marker: campus anchor, independent of camera count.
- Heatmap: stored detection density; intensity reflects repeated observations, not named people.

The detection heatmap offsets the camera’s coordinates using normalized image-box centers. This is an approximate display and not a calibrated conversion from pixels to physical ground locations. The map needs internet access for its background tiles.

Sources: `CampusMap.tsx`, `CampusMapEnhanced.tsx`, `campus.ts`, `campusMarker.ts`, and `heatmap.py`.

## 19. Configuration and environment variables

Backend settings read `.env` relative to the process working directory; the root and `backend/.env` both exist and can differ. Compose injects the root file. Next.js configuration reads selected public values from the root `.env`. Values below are safe defaults/meanings, not credentials.

| Variable | Purpose | Example / actual meaning |
|---|---|---|
| APP_NAME / APP_VERSION | Application identity | Campus Sentinel / 1.0.0 defaults. |
| ENVIRONMENT / DEBUG | Runtime behavior | Local files use development; DEBUG=false. |
| HOST / PORT / WORKERS | Server settings | 0.0.0.0 / 8000 / 4 defaults; launch command determines actual process count. |
| SECRET_KEY | JWT signing key | `<secret>`; replace default. |
| ALGORITHM | JWT signing algorithm | HS256. |
| ACCESS_TOKEN_EXPIRE_MINUTES | Access lifetime | 60. |
| REFRESH_TOKEN_EXPIRE_DAYS | Refresh token lifetime | 7; no refresh endpoint found. |
| ALLOWED_HOSTS | Used as CORS origins in production | JSON list of allowed full origins; default wildcard. |
| POSTGRES_HOST | Database host | localhost for native; postgres for containers. |
| POSTGRES_PORT | Database port | Local inspected file 5433; container connection needs 5432. |
| POSTGRES_DB | Database name | campus_sentinel. |
| POSTGRES_USER / POSTGRES_PASSWORD | Database login | `<hidden>` / `<your-password>`. |
| REDIS_HOST / REDIS_PORT / REDIS_DB | Redis connection | localhost or redis / 6379 / 0. |
| REDIS_PASSWORD | Redis login | `<your-password>`; match the server configuration. |
| YOLO_MODEL_PATH | Intended weights path | models/weights/yolov8n.pt; live default constructor uses yolov8n.pt. |
| YOLO_CONFIDENCE_THRESHOLD | Intended object confidence | 0.5; not passed from settings by StreamManager. |
| YOLO_DEVICE | Intended inference device | cpu; not passed from settings by StreamManager. |
| FRAME_SKIP | Process every Nth captured frame | 3, read at capture loop setup. |
| MAX_CAMERAS | Declared camera limit | 16; no enforcement found in camera creation/startup. |
| IP_CAMERA_URL | Phone source for initial classroom seed | `http://<phone-ip>:8080/video`; saved record then controls capture. |
| CAMERA_FALLBACK_INDEX | Local device index | 0; seed uses it for the entrance camera. |
| CAMERA_RECONNECT_DELAY_SECS | CameraManager retry delay | 5.0; StreamManager outer retry is separately 10. |
| LOITERING_THRESHOLD_SECS | Intended loiter duration | 300; active constructors independently use default 300. |
| CROWD_DENSITY_THRESHOLD | Intended person threshold | 20; active constructors independently use default 20. |
| RUNNING_SPEED_THRESHOLD | Declared speed setting | 3.0; active movement code instead compares pixels/second to 15. |
| ALERT_COOLDOWN_SECS | Repeat alert suppression | 60; used by alert task. |
| THREAT_ALERT_THRESHOLD | Prediction dispatch cutoff | 0.5; used by DecisionAgent. |
| MAIL_USERNAME / MAIL_PASSWORD | SMTP login | `<hidden>`. |
| MAIL_FROM / MAIL_SERVER / MAIL_PORT | Email sender/server | Configured sender / SMTP host / 587 default. |
| MAIL_STARTTLS / MAIL_SSL_TLS | Email transport settings | true / false defaults. |
| ALERT_EMAIL_TO | Declared recipient list | List setting; alert task actually queries active admin/superadmin users. |
| FRONTEND_URL | Link target in email | http://localhost:3000 default. |
| PROMETHEUS_ENABLED | Enable metrics endpoint | true default. |
| GRAFANA_PASSWORD | Monitoring admin password | `<your-password>`; Compose-only variable. |
| NEXT_PUBLIC_API_URL | Browser API base | http://localhost:8000. |
| NEXT_PUBLIC_WS_URL | Browser WebSocket base | ws://localhost:8000. |
| NEXT_PUBLIC_CAMPUS_LAT / NEXT_PUBLIC_CAMPUS_LNG | Campus anchor overrides | Set public campus coordinates; validated in campus.ts. |
| NEXT_PUBLIC_CAMPUS_ZOOM | Initial map zoom | 18. |
| DOCKER_BUILD | Select Next.js standalone output | true during Docker build. |
| NEXT_BUILD_DIR | Alternate frontend output directory | .next default; useful for separate verification builds. |

Derived URLs include DATABASE_URL, SYNC_DATABASE_URL, REDIS_URL, CELERY_BROKER_URL, and CELERY_RESULT_BACKEND. They contain connection details and should not be printed with credentials.

The settings API also defines lowercase form fields for CSI interval and ABD contamination. Its `_get_redis()` imports nonexistent `get_redis_client`; reads catch the error and return defaults, while writes/reset fail. Even after repairing that helper, analyzer defaults, existing objects, and separate worker processes would need deliberate settings propagation. Do not present the current settings screen as fully controlling all live rules.

## 20. Docker

Docker packages services into containers. Compose starts the group, connects them, and attaches storage volumes.

| Service / container | Purpose | Host port -> container port |
|---|---|---|
| postgres / cs_postgres | PostgreSQL 15 + TimescaleDB | 5433 -> 5432 |
| redis / cs_redis | Temporary state, pub/sub, task queues | 6379 -> 6379 |
| backend / cs_backend | FastAPI and capture threads | 8000 -> 8000 |
| celery_worker / cs_celery_worker | AI/alert/analytics queues | None published |
| celery_beat / cs_celery_beat | Periodic scheduling | None published |
| flower / cs_flower | Celery monitor | 5555 -> 5555 |
| frontend / cs_frontend | Next.js server | 3000 -> 3000 |
| nginx / cs_nginx | Reverse proxy | 80 -> 80; 443 -> 443 (actual TLS needs configuration) |
| prometheus / cs_prometheus | Metrics collection | 9090 -> 9090 |
| grafana / cs_grafana | Metrics display | 3001 -> 3000 |

```sh
docker compose up -d --build
docker compose down
```

The first builds images and starts services in the background. The second stops/removes this Compose deployment’s containers/network; named volumes normally remain. It does not stop an independently launched native backend.

Deployment gaps visible in configuration:

- Current local `.env` uses localhost/5433. Inside containers, database/Redis hosts must be service names and PostgreSQL port 5432.
- AI is mounted as `/ai_engine`, but imports use `ai_engine`; the images do not add `/` to PYTHONPATH. `agents/` is outside the backend build context and is not mounted into these services. Resolve import packaging before calling full Compose startup complete.
- Backend Docker command launches four API workers; each worker runs its own startup capture/agent logic. This can open the same cameras repeatedly.
- Beat specifies `django_celery_beat.schedulers:DatabaseScheduler`, but Django/django-celery-beat are absent from requirements. The configured periodic tasks therefore need scheduler repair.
- Grafana Compose mounts `infrastructure/grafana/datasources`, while checked-in provisioning is under `infrastructure/grafana/provisioning/`. Verify actual provisioning paths.
- Prometheus names database/Redis/container/host exporters that have no services in Compose. Its alert-rule file is referenced but not mounted by this service definition.
- Default Nginx upgrades `/ws/`, while actual sockets live under `/api/v1/ws/`; the `/api/` location lacks upgrade headers. Direct backend WebSockets bypass this proxy mismatch.
- Host webcam access is not mapped in Compose. A numeric index in a Linux container does not automatically reach the Windows webcam.

The production override adds restart policies, resource limits, Redis persistence, and a TLS-oriented Nginx configuration. Certificates, production configuration, and successful deployment are not established by their presence.

## 21. Project folder structure

```text
CAMPUS-SENTINEL/
|-- frontend/
|   |-- src/app/             pages
|   |-- src/components/      dashboard, cameras, map, classroom, charts
|   |-- src/hooks/           realtime lifecycle
|   |-- src/lib/             API, sessions, campus config, CSI helpers
|   |-- src/store/           shared state
|   `-- tests/               frontend regression tests
|-- backend/
|   |-- app/api/v1/          REST/WebSocket routes
|   |-- app/core/            settings, security, Celery
|   |-- app/db/              database/Redis clients
|   |-- app/models/          stored entities
|   |-- app/schemas/         request/response data shapes
|   |-- app/services/        CSI, email, WebSocket manager, tasks
|   |-- app/middleware/      rate limiting
|   |-- alembic/             migration environment, no revisions found
|   `-- tests/               unit/integration tests
|-- ai-engine/
|   |-- vision/              capture, detector, annotation, stream loop
|   |-- tracking/            overlap-based tracking
|   |-- behavioral/          movement/crowd/zone rules
|   |-- classroom/           face/pose signals and classroom rules
|   |-- abd/                 synthetic data, Isolation Forest training
|   `-- prediction/          threat trainer and runtime fallback
|-- agents/                  Python modules connected by Redis bus
|-- infrastructure/          SQL, Nginx, Prometheus, Grafana
|-- scripts/                 setup, deployment, training, verification
|-- docs/                    existing guides
|-- .github/workflows/       automation configuration
|-- .env.example             configuration template
|-- docker-compose.yml      service definition
|-- docker-compose.prod.yml production overrides
|-- run / terminate         Bash startup/shutdown helpers
`-- yolov8n.pt               detector weights (another copy in backend)
```

Local environments, build output, logs, and PID files are runtime artifacts. They are not training datasets or application modules.

## 22. Complete workflow example

1. A saved classroom camera URL points to the phone’s `/video` stream.
2. Backend startup loads active camera records and starts capture threads.
3. OpenCV opens the phone source and reads frames.
4. Every third captured frame goes through YOLOv8n and object filtering.
5. The tracker matches boxes and assigns temporary IDs after enough hits.
6. The annotated JPEG and current tracks are written to Redis.
7. On captured frame numbers divisible by 30, classroom code crops person boxes and runs MediaPipe.
8. Suppose a non-faculty candidate’s eye ratio stays below 0.20 for at least 15 seconds. The rule produces a low-severity sleeping warning.
9. A running Celery worker receives the alert task and checks the shared cooldown.
10. The task saves an Alert, recalculates CSI using recent alerts plus incidents, and publishes messages.
11. FastAPI forwards the messages to authenticated event WebSocket clients.
12. The dashboard updates its alert state and CSI display; its camera socket reads the latest JPEG. Polling recovers if a message is missed.

This creates an alert, not an automatically linked incident or a named student attendance record. With no prior events a fresh low warning changes CSI from 100 to 98.

## 23. What is implemented

| Status | Functionality | Qualification |
|---|---|---|
| ✅ Implemented | HTTP/IP/numeric camera capture and live JPEG display | Needs reachable hardware/source and working imports/dependencies. |
| ✅ Implemented | Android classroom and local entrance seed | Created only when no cameras exist. |
| ✅ Implemented | Person/selected-object detection | Pretrained detector; errors can leave empty detections. |
| ✅ Implemented | Per-camera tracking | Simplified greedy IoU, not full ByteTrack/Kalman. |
| ✅ Implemented | Behavioral rule modules | Unit/calibration limitations listed above. |
| ✅ Implemented | Classroom face/pose rules and CAI | Estimates, not confirmed actions or identity. |
| ✅ Implemented | Alert storage/status and cooldown | Requires Redis/Celery/PostgreSQL. |
| ✅ Implemented | Incident create/update/resolve/delete | Separate manual records. |
| ✅ Implemented | Canonical CSI and REST/event delivery | Snapshot schema mismatch remains. |
| ✅ Implemented | Dashboard, charts, camera controls, campus maps | API-backed with noted static panels. |
| ✅ Implemented | PostgreSQL entities and active Redis usage | SQL-only tables have limited integration. |
| ✅ Implemented | JWT/password hashing and selected role checks | Security gaps remain. |
| 🟡 Partially implemented | Local-webcam fallback | Supported option, disabled in active stream loop. |
| 🟡 Partially implemented | Named attendance / faculty identification | Headcount plus location heuristic only. |
| 🟡 Partially implemented | Learned anomaly/threat models | Trainers exist; trained artifacts not found; feature mismatch. |
| 🟡 Partially implemented | Runtime settings | Missing helper and incomplete propagation. |
| 🟡 Partially implemented | SMTP notifications | Sending code exists; credentials/delivery unverified; fallback logging. |
| 🟡 Partially implemented | Docker deployment and monitoring | Service definitions exist with packaging/scheduler/path gaps. |
| 🟡 Partially implemented | Automatic periodic tasks | Schedule exists; current Compose Beat scheduler dependency is missing. |
| ❌ Not implemented / Future work | Custom campus YOLO training | No custom dataset/trainer found. |
| ❌ Not implemented / Future work | Reliable student/faculty/visitor identity | No role-classification or identity integration. |
| ❌ Not implemented / Future work | Live LSTM inference | Trainer only. |
| ❌ Not implemented / Future work | Confirmed fight/abandoned-object action recognition | Names in SQL/UI do not prove a detector. |
| ❌ Not implemented / Future work | RFID/QR roster mapping, cross-camera identity, SMS | No active implementation found. |

## 24. Rule-based versus AI-based

| Feature | AI model | Rule-based | Explanation |
|---|---|---|---|
| Object/person detection | Yes | Category/confidence filtering | YOLOv8n predicts boxes. |
| Tracking | No separate learned model | Yes | Greedy overlap matching and track lifetime. |
| Running/loitering/crowd/zone alerts | AI supplies detections | Yes | Thresholds on positions, counts, time, or polygons. |
| Face/pose landmarks | Yes | Geometry calculations | MediaPipe supplies landmarks. |
| Sleeping/talking estimates | AI supplies landmarks | Yes | Eye/mouth/head conditions sustained over time. |
| Attendance | AI supplies person boxes | Yes | Headcount compared with expected count. |
| Faculty selection/engagement | Pose model may supply signals | Yes | Teaching-zone/position heuristic, weighted score. |
| CAI / CSI | No learned scoring model | Yes | Explicit weighted/penalty formulas. |
| ABD anomaly | Conditional | Threshold/normalization | Isolation Forest only if a saved slot model exists; otherwise 0. |
| Threat prediction | Conditional | Yes fallback | Loads a compatible RF bundle or uses crowd/zone/anomaly rules. LSTM is unused live. |
| Alert explanation | No active SHAP/LIME call | Yes | Hand-built contribution values labeled SHAP. |
| Reliable role identification | No | No reliable implementation | Role guesses should not be presented as identity recognition. |

## 25. Known limitations

- Camera lighting, angle, quality, obstruction, and network interruptions affect boxes and face signals.
- Greedy box overlap can change IDs or match across classes; tracks persist for up to 30 updates and confirmed stale tracks can still be counted. No Hungarian assignment/Kalman filter is executed despite the module header.
- Motion is measured in pixels, not calibrated meters; loitering compares inconsistent units. False warnings are possible.
- Stateful rules run in both agent/API and Celery paths; multiple workers/processes keep separate histories. This can split timing history or duplicate analyses.
- Expected student count defaults to 30; teacher/visitor inclusion and hidden faces make headcount unreliable as attendance.
- Mouth/eye rules cannot prove talking/sleeping. No audio or labeled classroom evaluation was found.
- ABI/package imports need attention: folder is `ai-engine`, imports request `ai_engine`, and no alias directory/package was found in the supplied tree. Simply adding the hyphenated folder to PYTHONPATH does not rename it.
- Trainer uses nine RF features and binary classes; live agent predictor builds eight features and expects threat names. Loading its training output can therefore fail or produce incompatible outputs. Scheduled tasks use nine features but retain the binary-class/name mismatch.
- ABD training uses hourly aggregate features, while live scoring supplies person count plus four zeros. PostgreSQL day-of-week numbering and Python weekday numbering also differ; time slots can be mismatched.
- Generated behavior history is not real campus training evidence. No demonstrated custom YOLO training or project accuracy/FPS benchmark was found.
- Settings, Beat scheduling, model imports, CSI snapshot constraint, prediction push shape, and monitoring mount issues limit full integration.
- A score of 100 can coexist with unavailable cameras or failed detection. `/health` does not measure dependency health.
- There are database fields for recording/snapshots and SQL names for abandoned objects/fights; fields/names alone are not a continuous recording or action-recognition implementation.

## 26. Future improvements — future work

1. Fix package imports, Compose service configuration, scheduler dependencies, settings propagation, and SQL constraints.
2. Normalize image positions consistently and calibrate movement to actual scene distances.
3. Align training/inference feature order, dimensions, class names, and time slots; evaluate on withheld real observations.
4. Collect an authorized campus dataset and fine-tune detection/action models with measured accuracy. This is future custom training.
5. Improve the existing MediaPipe pose/face integration and validate sleeping/talking estimates rather than claiming guaranteed actions.
6. Integrate authorized RFID/QR or roster mapping for reliable attendance and roles.
7. Add tested GPU inference wiring, camera ownership across processes, stronger tracking, and cross-camera identity if required.
8. Improve alert verification, notification delivery/auditing, historical analytics, and live agent health indicators.
9. Strengthen registration, permissions, token handling, TLS, and operational security.

## 27. Security

Authentication uses email/password login, bcrypt password hashing, and HS256 JWT access/refresh tokens. Protected REST dependencies decode access tokens, require type `access`, look up the user, and check that the account is active. Admin endpoints/settings mutations include role checks; many other mutations require only a signed-in user.

Actual weaknesses visible in code/configuration:

- Public registration accepts the caller’s `role` and does not require administrator authorization. This can permit privileged-role creation; the database’s role list is not an authorization defense.
- Login does not check `is_active` before issuing tokens, although protected REST requests do.
- WebSocket handlers only check that a token decodes. They do not enforce token type or query current user/active status.
- Browser tokens are stored in localStorage and session-related cookies. WebSocket tokens travel in query strings and may appear in URL logs.
- Development CORS allows all origins; production uses `ALLOWED_HOSTS` as origins rather than host-header filtering. Production override should provide a correctly formatted list of full origins.
- Default credentials/signing placeholders exist in setup/config/SQL. Replace them; this document deliberately omits their values.
- Redis/PostgreSQL/Flower/Grafana ports are published in Compose. Restrict access appropriately for deployment.
- Rate limiting is implemented (200 requests/60 seconds generally; login 10/60), but it trusts `X-Forwarded-For` and errors allow requests through.
- HTTP/ws local defaults have no transport encryption. TLS proxy configuration exists, but installed certificates and production enforcement were not verified.
- Map popup HTML interpolates camera-provided text; sanitize it before accepting untrusted names.

No password, hash, token, or signing key is reproduced here. Application user roles are separate from the guessed roles of people in video.

## 28. Performance

The source selects the nano YOLO variant and defaults to CPU. It reuses detector instances within a process and skips frames to reduce detection calls; actual FPS is not measured in this inspection.

At FRAME_SKIP=3, detection persistence additionally requires captured frame number divisible by 10, so both conditions coincide every 30 captured frames. Behavioral/classroom passes require divisibility by 30. Changing frame skip changes these intersections; this is not a fixed analysis interval in seconds.

Classroom analysis runs MediaPipe for each person crop at that reduced cadence. Frames are JPEG-encoded at quality 72, base64-encoded, then stored in Redis. CPU cost and message size rise with people/cameras. MAX_CAMERAS=16 is a declared value, not an enforced or benchmarked capacity.

GPU support exists as a detector argument, but environment-to-live-detector wiring is incomplete and Compose has no GPU reservation. Multiple API processes can multiply capture/model load. Reconnect pauses and a stalled-read restart reduce repeated connection attempts but may delay recovery.

## 29. Software requirements

- Docker Desktop with Compose for the container method and the supplied Windows helper’s database/Redis services.
- Python 3.11, matching Dockerfiles and setup script. Other versions were not established as compatible.
- Node.js 20 and npm, matching frontend Dockerfile/lock and workflow configuration.
- A modern browser supporting WebSocket and JavaScript.
- PostgreSQL 15 with TimescaleDB for the supplied SQL initialization; Redis 7 for service parity.
- Android IP Webcam app and phone/network access when demonstrating that classroom source.
- Webcam access when using local index 0; the native backend is the practical host-device path in the current configuration.
- Bash for `run`, `terminate`, and `.sh` helpers. The macOS deployment script explicitly requires macOS/Homebrew and an Apple Silicon Python path.

## 30. How to run the project

These commands reflect the supplied repository. Current integration gaps are listed so a fresh checkout is not mistaken for a verified one-command deployment. This inspection did not start cameras, seed a database, or train models.

### A. Docker method

1. Create `.env` from the example only if it does not already exist. In PowerShell:

   ```powershell
   if (!(Test-Path .env)) { Copy-Item .env.example .env }
   ```

2. Set your secret/passwords. For backend containers set POSTGRES_HOST=postgres, POSTGRES_PORT=5432, REDIS_HOST=redis. Keep browser-facing API/WS URLs reachable from the browser.
3. Start the Android IP Webcam server and verify `http://<phone-ip>:8080/video` from the backend’s network. Configure IP_CAMERA_URL before initial seeding; edit existing camera records through the UI/API afterward.
4. Resolve the documented `ai_engine`/`agents` packaging and Beat scheduler issues before expecting all services to work. Host webcam index 0 additionally needs platform-specific access that Compose does not provide.
5. Start Docker Desktop, then run the repository’s deployment command:

   ```sh
   docker compose up -d --build
   docker compose ps
   docker compose logs backend celery_worker celery_beat
   ```

6. A fresh PostgreSQL volume runs `infrastructure/postgres/init.sql` automatically. Existing volumes do not rerun it; do not delete data just to rerun setup. No Alembic revisions were supplied as an alternative schema.
7. Open `http://localhost:3000`, health `http://localhost:8000/health`, and API docs `http://localhost:8000/api/docs`. Use your configured account; credentials are omitted here. Confirm actual API/camera/worker behavior in addition to the health response.
8. Stop with `docker compose down` when finished.

`bash scripts/setup.sh` implements build/infrastructure/start steps. The production command is `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`; its configuration still needs deployment-specific review.

### B. Native backend/frontend with Docker database and Redis

The supplied `run` Bash helper follows this hybrid method and uses a Windows virtual-environment path. It expects `backend/.venv/Scripts/python.exe`; that exact environment directory was not present in the inspected inventory. The source also needs an importable `ai_engine` package and access to `agents` before these processes can run; the supplied hyphenated folder is not sufficient on its own.

Prepare the environment using the helper’s instructions, with Python 3.11:

```sh
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

Set `backend/.env` for native localhost connections (PostgreSQL host port 5433), and set root public frontend URLs. Once package imports are repaired, the actual process commands used by `run` are:

```sh
# From repository root
docker compose up -d postgres redis

# From backend, in separate terminals
.venv/Scripts/python -m celery -A app.core.celery_app worker --loglevel=info --pool=solo -Q ai_tasks,alerts,analytics
.venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# From frontend
npm ci
npm run build
npm run start
```

`--pool=solo` is used for the Windows worker. `run` does not launch Beat, so scheduled snapshots/retraining/digests do not automatically run by this path. Alternatively use `bash run` after its prerequisites, and `bash terminate` to stop its managed processes; the helper also sweeps matching process names, so inspect it before sharing a machine with another project.

`npm run dev` exists, but the supplied Windows helper prefers build/start because its comments document OneDrive/build-chunk interference. `bash scripts/deploy-local.sh` is a separate macOS-only local-services method, not a Windows installer.

### Verification supplied by the repository

Backend tests cover tracking, behavioral rules, CSI, stream restart, and pipeline components. Frontend tests cover CSI/map/session/reconnect behavior. Scripts include campus safety/map/browser verification. Tests often use fake or patched dependencies and do not establish real-camera accuracy.

```sh
# From frontend
npm test
npm run type-check

# From a configured backend environment
python -m pytest tests
```

No claim is made here that these checks passed during documentation creation. Import/environment gaps may prevent fresh execution.

## 31. Troubleshooting

| Problem | Checks / response |
|---|---|
| Camera shows Error | Test saved source, not just .env. Confirm phone server/Wi-Fi and `/video`; check backend reachability and stream logs/status. Phone fallback is disabled. |
| Webcam unavailable in Docker | Numeric index is inside the container. Current Compose does not pass through the Windows camera; use the native capture path or implement tested device access. |
| 0/0 cameras | Check sign-in, GET `/api/v1/cameras/`, database schema/connectivity, and backend startup logs. Empty-table seeding can fail if DB is missing. |
| Dashboard Offline | Check API URL, `/health`, event WebSocket route/base URL, token/session, and CORS/proxy settings. API health and socket connectivity are separate. |
| CSI Loading / stale | Request `/api/v1/csi/campus`; check authentication and database errors. Failed refresh retains an existing valid score; do not substitute a fake score. |
| Webcam light remains on | Stop the owning stream or backend; stop native processes as well as containers. Allow capture loop to release; check other camera apps if it remains active. |
| Map location wrong / missing | Check campus.ts/public env overrides and each camera’s saved coordinates. Rebuild frontend after public variable changes. Invalid positions are deliberately hidden. |
| Missing ai_engine / agents import | Repair package layout/PYTHONPATH/container inclusion. `ai-engine` is not importable under the underscore name merely because its directory is on the path. |
| Frames visible but no objects | Check YOLO load errors and active default `yolov8n.pt` path. Empty detections can be a model failure, not an empty scene. |
| No automatic alerts | Check worker consumes ai_tasks/alerts/analytics, Redis connectivity, rule thresholds/history, and cooldown. Queued tasks need a worker. |
| Beat fails | Current command requests absent Django scheduler dependency; use a correctly configured Celery scheduler or supply its full dependencies. |
| CSI history missing | Check Beat/manual snapshot task and SQL risk-level constraint (`low_risk` missing). Campus live endpoint calculates separately. |
| Settings save fails | Missing `get_redis_client` import in settings endpoint; reads hide the issue by returning defaults. Fix helper and process propagation. |
| RF prediction errors | Check artifact feature dimensions/order and binary versus named class mismatch. Current trainer and live agent input differ. |
| Threat widget fails after push | Scheduled message is a dictionary while widget expects list; normalize payload. REST polling may reload a proper list. |
| Frontend missing chunk/module | Avoid simultaneous dev/start/build processes using one output directory. Comments in `run` document OneDrive locking; use a separate verification build directory when appropriate. |
| Container database unreachable | Inside Docker use postgres:5432; native host uses localhost:5433. Match Redis password and host too. |
| Login denied | Inspect configured user/password hashing and account setup without printing secrets. A commented default password is not verification that a stored hash matches it. |

## 32. Simple viva / presentation explanation

### How to explain Campus Sentinel in 2 minutes

“Campus Sentinel is a campus monitoring project. It reads video from a webcam or a phone/IP camera and shows the results in a web dashboard. The aim is to help campus staff notice possible problems and investigate them.

We use OpenCV to read video and a pretrained YOLOv8n model to find people and selected objects. A simple tracker matches boxes across images and gives temporary IDs. Then rules check things such as crowd count, movement speed, time spent in an area, and restricted-zone entry.

For classroom cameras, MediaPipe estimates face and body landmarks. Timing rules use those signals to estimate closed eyes, mouth activity, and classroom attention. These are estimates: the system does not prove that someone is sleeping or talking, and it does not reliably identify a student or faculty member. Faculty selection currently uses position in the classroom.

FastAPI supplies the backend APIs. PostgreSQL stores cameras, alerts, incidents, and measurement history. Redis keeps recent frames and carries messages and queued tasks. WebSockets and periodic requests keep the Next.js dashboard updated.

The Campus Safety Index starts at 100 and subtracts penalties for recent alerts and incidents. Severe events subtract more, old events gradually lose impact, and resolved events have a reduced penalty. Separate machine-learning training scripts exist for behavior patterns and threats, but there is no custom campus YOLO training evidence in this repository. The project still needs integration fixes, calibration, and real-world evaluation before reliable deployment.”

| Question | Simple explanation |
|---|---|
| What is YOLOv8? | A model that finds objects in images and draws boxes around them. This project selects the nano detector and filters eight object categories. |
| What is OpenCV? | A video/image processing library. Here it opens camera streams, reads frames, draws annotations, and creates JPEG images. |
| What is FastAPI? | A Python framework for backend routes. It lets the dashboard request records and open realtime connections. |
| What is PostgreSQL? | A database that keeps structured records after the application stops. Here it stores users, cameras, alerts, incidents, and histories. |
| What is Redis? | A fast store for temporary data and messages. It holds latest frames, cooldowns, and task/realtime communication. |
| What is Docker? | A way to package software services with their runtime dependencies. Compose defines how the project’s services start and connect. |
| What is WebSocket? | An open connection allowing ongoing messages between server and browser. Here it carries event updates and camera JPEGs. |
| What is behavioral analysis? | Examining tracked positions, counts, timing, and face signals for configured conditions. Most behavior labels here come from rules using AI-generated observations. |
| What is Campus Safety Index? | A 0–100 rule score based on recent stored alerts and incidents. A higher number means fewer remaining penalties, not guaranteed physical safety. |

## 33. Twenty examiner questions and short answers

1. **Why YOLOv8n?** The repository selects its small nano variant for object detection and CPU defaults. No project speed/accuracy benchmark proves a particular FPS.
2. **Which dataset is the detector from?** Standard YOLOv8n detection weights are COCO-pretrained; COCO includes common objects and the person category.
3. **Did you train the detector yourself?** No campus YOLO training evidence was found. Separate ABD/RF/Gradient Boosting/LSTM trainers do exist, which is a different claim.
4. **How do you detect sleeping?** MediaPipe eye/head signals feed a rule: eye ratio <0.20 or head-down with no visible face, sustained for 15 seconds by default. It is an estimate.
5. **How do you detect talking?** A rule checks mouth-shape variability >=0.035, using at least eight samples, sustained for eight seconds by default. It does not analyze audio.
6. **How do you detect running?** Track-center distance divided by elapsed time is compared with 15 pixels/second after three velocity samples. The environment’s 3.0 setting is not wired into this code.
7. **Can YOLO distinguish faculty/student?** No. A teaching-zone or top-of-frame heuristic guesses faculty; reliable identity mapping is absent.
8. **What is confidence threshold?** The minimum score used to accept an object box. The active default is 0.5; it is not a probability that a behavior is true.
9. **Why PostgreSQL?** This implementation needs linked, permanent records and time queries. Compose additionally uses TimescaleDB for histories.
10. **Why Redis?** The code actively uses it for latest frames, pub/sub, agent communication, task queues, cooldowns, and rate limits.
11. **Why Docker?** It groups services with their dependencies. Current packaging, host-camera, and scheduler gaps mean the files alone do not prove deployment success.
12. **What happens if a camera disconnects?** The backend marks an error/reconnecting state and retries. It preserves that camera’s source rather than substituting another camera.
13. **How does CSI work?** Subtract severity penalties 2/5/10/20 with linear 24-hour decay; resolved/closed/dismissed impact is multiplied by 0.25. Round and clamp to 0–100.
14. **How do realtime updates work?** Redis publications reach FastAPI’s event WebSocket and update browser state. REST polling restores lists and CSI after missed messages.
15. **Does every alert become an incident?** No. Alerts are automatic warnings; incidents are separate user-recorded issues. Both affect CSI.
16. **Which tracking algorithm is implemented?** A simplified tracker called ByteTracker uses greedy box-overlap matching. It does not execute full ByteTrack, Hungarian assignment, or Kalman filtering.
17. **Are predictions fully learned AI?** Not always. Missing RF files cause heuristic predictions; the trainer/live feature and class mismatch needs fixing. LSTM training is not wired into inference.
18. **Is dashboard data real?** Main widgets query backend records, but seeded records are synthetic, agent status cards are static, and alert explanations are manual values labeled SHAP.
19. **What are the main limitations?** Camera/face quality, tracking errors, uncalibrated motion, role guesses, incomplete settings/deployment/model integration, and no real-campus accuracy evaluation.
20. **What is future work?** Repair integration, evaluate/calibrate with authorized campus data, improve existing pose/action logic, integrate roster/ID mapping, and strengthen security/notifications.

## 34. Final project summary table

| Component | Technology/model | Purpose |
|---|---|---|
| Frontend | Next.js 14.2.3, React, TypeScript, Tailwind | Dashboard and management pages. |
| Backend | Python 3.11, FastAPI, Uvicorn | API/business logic and capture orchestration. |
| Detection | Pretrained YOLOv8n / Ultralytics | People and seven other retained object categories. |
| Video | OpenCV | Source capture, frame processing, JPEGs. |
| Tracking | Simplified greedy IoU ByteTracker | Temporary per-camera IDs. |
| Behavioral safety | Python rules | Motion, loitering, crowd, restricted-zone conditions. |
| Classroom signals | MediaPipe Face Mesh/Pose plus rules | Sleeping/talking candidates, engagement, CAI/headcount. |
| Persistent database | PostgreSQL 15 / TimescaleDB in Compose | Users, cameras, events, histories, model metadata. |
| Temporary/realtime state | Redis 7 | Frame/state caches, pub/sub, cooldowns, queues. |
| Background work | Celery / Beat configuration | Alerts, analytics, training, digest tasks; scheduler gap noted. |
| Anomaly training | Isolation Forest | Camera/time-slot normal-pattern models, conditional on artifacts. |
| Threat training/runtime | RF/Gradient Boosting trainer; RF loader or rules | Prototype prediction; training/inference mismatch noted. |
| LSTM | PyTorch trainer only | Future inference integration. |
| Safety scoring | Canonical Python CSI formula | Recent alert/incident penalty score. |
| Campus map | Leaflet / OpenStreetMap / leaflet.heat | Camera/incident markers and approximate density view. |
| Phone streaming | Android IP Webcam HTTP /video | Classroom video source. |
| Realtime | Native WebSocket plus REST polling | Event updates, latest JPEG display, recovery. |
| Security | JWT / bcrypt / selected role checks | Account access with documented gaps. |
| Notifications | FastAPI-Mail SMTP code and logging fallback | Optional alert/digest email, delivery unverified. |
| Deployment/monitoring | Docker Compose, Nginx, Prometheus, Grafana, Flower | Service packaging/proxy/monitoring definitions with noted gaps. |
