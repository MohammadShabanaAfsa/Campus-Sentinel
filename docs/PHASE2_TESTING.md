# Phase 2 — Testing Guide

## Stream Pipeline Testing

### 1. Start infrastructure

```bash
cd campus-sentinel
cp .env.example .env
docker compose up -d postgres redis
```

### 2. Run unit tests (no camera required)

```bash
cd backend
python -m pytest tests/unit/ -v
```

Expected output:
```
tests/unit/test_behavioral.py::TestLoiteringDetector::test_no_alert_short_duration PASSED
tests/unit/test_behavioral.py::TestLoiteringDetector::test_alert_after_threshold    PASSED
tests/unit/test_behavioral.py::TestLoiteringDetector::test_non_person_ignored       PASSED
tests/unit/test_behavioral.py::TestCrowdAnalyzer::test_no_alert_below_threshold     PASSED
tests/unit/test_behavioral.py::TestCrowdAnalyzer::test_alert_above_threshold        PASSED
tests/unit/test_behavioral.py::TestZoneChecker::test_point_in_polygon               PASSED
tests/unit/test_csi.py::test_score_to_level                                         PASSED
tests/unit/test_tracker.py::test_update_creates_tracks                              PASSED
```

### 3. Run integration tests

```bash
python -m pytest tests/integration/ -v
```

### 4. Test with a real webcam

```python
# In a Python shell
from ai_engine.vision.stream_processor import StreamProcessor
# Use "0" for webcam, or your RTSP URL
processor = StreamProcessor(camera_id="YOUR_CAMERA_UUID_FROM_DB")
processor.run()  # Will process frames until stopped
```

### 5. Test via API

```bash
# Get auth token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -F "username=admin@campus-sentinel.local" \
  -F "password=Admin@123" | jq -r .access_token)

# Add a test camera (webcam)
curl -X POST http://localhost:8000/api/v1/cameras/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Webcam","location_name":"Dev Machine","rtsp_url":"0","zone_type":"general"}'

# Get camera ID from response, then start stream
CAM_ID="<id from above>"
curl -X POST http://localhost:8000/api/v1/streams/$CAM_ID/start \
  -H "Authorization: Bearer $TOKEN"

# Check stream status
curl http://localhost:8000/api/v1/streams/status \
  -H "Authorization: Bearer $TOKEN"

# Get latest snapshot
curl http://localhost:8000/api/v1/streams/$CAM_ID/snapshot \
  -H "Authorization: Bearer $TOKEN" | jq .frame_b64 | head -c 100
```

### 6. WebSocket frame test

Open browser DevTools console on the dashboard and verify frames arrive:

```javascript
const ws = new WebSocket("ws://localhost:8000/api/v1/ws/camera/CAM_ID/stream?token=YOUR_TOKEN");
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  console.log("Frame received:", msg.type, "Tracks:", msg.tracks?.length);
};
```

## Expected Data Flow

```
Webcam / RTSP
    ↓ (OpenCV read)
StreamManager thread
    ↓ (every 3rd frame)
YOLOv8 detection        → Redis camera:ID:latest_frame
ByteTracker update      → Redis camera:ID:tracks
FrameAnnotator draw     → Redis pub: camera_events
    ↓ (every 30th frame)
Celery: analyze_behavior
    ↓
LoiteringDetector + CrowdAnalyzer + MovementAnalyzer + ZoneChecker
    ↓ (if alert triggered)
Celery: create_and_dispatch_alert
    ↓
PostgreSQL: alerts table
Redis: publish alerts_channel
    ↓
FastAPI WebSocket: broadcast to all connected dashboards
    ↓
React dashboard: alert panel updates in real time
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Cannot open stream` | Check RTSP URL, camera credentials, network access |
| `YOLO model not found` | Run `pip install ultralytics` — it auto-downloads `yolov8n.pt` on first use |
| No frames in dashboard | Check WebSocket connection in browser Network tab |
| Redis connection refused | `docker compose up -d redis` |
| DB migrations not applied | `alembic upgrade head` or check init.sql ran on first container start |
