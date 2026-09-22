-- Campus Sentinel — PostgreSQL + TimescaleDB Schema
-- Run once on first startup via docker-entrypoint-initdb.d

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ─── USERS ──────────────────────────────────────────────────────────────────
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       VARCHAR(255) UNIQUE NOT NULL,
    username    VARCHAR(100) UNIQUE NOT NULL,
    full_name   VARCHAR(255),
    role        VARCHAR(50) NOT NULL DEFAULT 'operator'
                CHECK (role IN ('superadmin', 'admin', 'operator', 'viewer')),
    hashed_password TEXT NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    last_login  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

-- ─── CAMERAS ────────────────────────────────────────────────────────────────
CREATE TABLE cameras (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    location_name   VARCHAR(255) NOT NULL,
    rtsp_url        TEXT NOT NULL,
    stream_url      TEXT,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    zone_type       VARCHAR(100) DEFAULT 'general'
                    CHECK (zone_type IN ('entrance', 'corridor', 'lab', 'parking',
                                         'cafeteria', 'library', 'admin', 'restricted', 'general',
                                         'classroom')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_recording    BOOLEAN NOT NULL DEFAULT FALSE,
    resolution      VARCHAR(20) DEFAULT '1920x1080',
    fps             INTEGER DEFAULT 25,
    status          VARCHAR(50) NOT NULL DEFAULT 'offline'
                    CHECK (status IN ('online', 'offline', 'error', 'maintenance')),
    last_heartbeat  TIMESTAMPTZ,
    config          JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cameras_status ON cameras(status);
CREATE INDEX idx_cameras_zone ON cameras(zone_type);
CREATE INDEX idx_cameras_location ON cameras(latitude, longitude);

-- ─── CAMERA RESTRICTED ZONES ────────────────────────────────────────────────
CREATE TABLE restricted_zones (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_id   UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    zone_points JSONB NOT NULL,  -- Array of {x, y} polygon points (normalized 0-1)
    alert_level VARCHAR(20) DEFAULT 'high' CHECK (alert_level IN ('low','medium','high','critical')),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_by  UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── DETECTIONS (time-series) ────────────────────────────────────────────────
CREATE TABLE detections (
    id              BIGSERIAL,
    camera_id       UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    object_class    VARCHAR(100) NOT NULL,
    confidence      FLOAT NOT NULL,
    bbox_x          FLOAT,
    bbox_y          FLOAT,
    bbox_w          FLOAT,
    bbox_h          FLOAT,
    track_id        INTEGER,
    frame_number    BIGINT,
    metadata        JSONB DEFAULT '{}',
    PRIMARY KEY (id, detected_at)
);

SELECT create_hypertable('detections', 'detected_at');
CREATE INDEX idx_detections_camera ON detections(camera_id, detected_at DESC);
CREATE INDEX idx_detections_class ON detections(object_class, detected_at DESC);
CREATE INDEX idx_detections_track ON detections(track_id, detected_at DESC);

-- ─── BEHAVIOR LOGS (time-series) ─────────────────────────────────────────────
CREATE TABLE behavior_logs (
    id              BIGSERIAL,
    camera_id       UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    logged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    behavior_type   VARCHAR(100) NOT NULL
                    CHECK (behavior_type IN ('loitering', 'running', 'crowd_surge',
                                              'restricted_access', 'abandoned_object',
                                              'fight_detected', 'abnormal_movement',
                                              'crowd_formation', 'congestion')),
    track_id        INTEGER,
    person_count    INTEGER DEFAULT 0,
    risk_score      FLOAT NOT NULL DEFAULT 0.0,
    duration_secs   FLOAT DEFAULT 0.0,
    location_x      FLOAT,
    location_y      FLOAT,
    details         JSONB DEFAULT '{}',
    PRIMARY KEY (id, logged_at)
);

SELECT create_hypertable('behavior_logs', 'logged_at');
CREATE INDEX idx_behavior_camera ON behavior_logs(camera_id, logged_at DESC);
CREATE INDEX idx_behavior_type ON behavior_logs(behavior_type, logged_at DESC);

-- ─── ALERTS ──────────────────────────────────────────────────────────────────
CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_id       UUID REFERENCES cameras(id) ON DELETE SET NULL,
    alert_type      VARCHAR(100) NOT NULL,
    severity        VARCHAR(20) NOT NULL DEFAULT 'medium'
                    CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    title           VARCHAR(500) NOT NULL,
    description     TEXT,
    status          VARCHAR(50) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'acknowledged', 'resolved', 'false_positive')),
    threat_score    FLOAT DEFAULT 0.0,
    csi_at_alert    FLOAT,
    explanation     JSONB DEFAULT '{}',   -- SHAP/LIME output
    snapshot_path   TEXT,
    acknowledged_by UUID REFERENCES users(id),
    acknowledged_at TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alerts_status ON alerts(status, created_at DESC);
CREATE INDEX idx_alerts_severity ON alerts(severity, created_at DESC);
CREATE INDEX idx_alerts_camera ON alerts(camera_id, created_at DESC);

-- ─── INCIDENTS ───────────────────────────────────────────────────────────────
CREATE TABLE incidents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title           VARCHAR(500) NOT NULL,
    description     TEXT,
    incident_type   VARCHAR(100) NOT NULL,
    severity        VARCHAR(20) NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status          VARCHAR(50) NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'investigating', 'resolved', 'closed')),
    camera_id       UUID REFERENCES cameras(id),
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    alert_ids       UUID[] DEFAULT '{}',
    assigned_to     UUID REFERENCES users(id),
    resolved_by     UUID REFERENCES users(id),
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_incidents_status ON incidents(status, created_at DESC);
CREATE INDEX idx_incidents_severity ON incidents(severity);

-- ─── ADAPTIVE BEHAVIORAL DNA PROFILES ────────────────────────────────────────
CREATE TABLE abd_profiles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_id       UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    zone_type       VARCHAR(100) NOT NULL,
    hour_of_day     SMALLINT NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
    day_of_week     SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    avg_person_count FLOAT DEFAULT 0,
    max_person_count FLOAT DEFAULT 0,
    avg_movement_speed FLOAT DEFAULT 0,
    avg_loiter_duration FLOAT DEFAULT 0,
    normal_behavior_vector FLOAT[] DEFAULT '{}',  -- Feature vector for Isolation Forest
    anomaly_threshold FLOAT DEFAULT 0.5,
    sample_count    INTEGER DEFAULT 0,
    model_path      TEXT,
    last_trained    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (camera_id, hour_of_day, day_of_week)
);

CREATE INDEX idx_abd_camera ON abd_profiles(camera_id);

-- ─── CAMPUS SAFETY INDEX (time-series) ───────────────────────────────────────
CREATE TABLE csi_scores (
    id              BIGSERIAL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    camera_id       UUID REFERENCES cameras(id) ON DELETE CASCADE,
    overall_score   FLOAT NOT NULL DEFAULT 100.0,
    crowd_score     FLOAT DEFAULT 100.0,
    loitering_score FLOAT DEFAULT 100.0,
    access_score    FLOAT DEFAULT 100.0,
    anomaly_score   FLOAT DEFAULT 100.0,
    historical_score FLOAT DEFAULT 100.0,
    risk_level      VARCHAR(20) NOT NULL DEFAULT 'safe'
                    CHECK (risk_level IN ('safe', 'moderate', 'high_risk', 'critical')),
    contributing_factors JSONB DEFAULT '{}',
    PRIMARY KEY (id, recorded_at)
);

SELECT create_hypertable('csi_scores', 'recorded_at');
CREATE INDEX idx_csi_camera ON csi_scores(camera_id, recorded_at DESC);
CREATE INDEX idx_csi_level ON csi_scores(risk_level, recorded_at DESC);

-- ─── THREAT PREDICTIONS (time-series) ────────────────────────────────────────
CREATE TABLE predictions (
    id              BIGSERIAL,
    predicted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    camera_id       UUID REFERENCES cameras(id) ON DELETE CASCADE,
    threat_type     VARCHAR(100) NOT NULL,
    probability     FLOAT NOT NULL,
    threat_level    VARCHAR(20) NOT NULL CHECK (threat_level IN ('low', 'medium', 'high', 'critical')),
    predicted_window_secs INTEGER DEFAULT 300,  -- How far ahead (seconds)
    recommended_action TEXT,
    model_version   VARCHAR(50),
    feature_importance JSONB DEFAULT '{}',
    was_accurate    BOOLEAN,  -- Filled in retrospectively
    PRIMARY KEY (id, predicted_at)
);

SELECT create_hypertable('predictions', 'predicted_at');
CREATE INDEX idx_predictions_camera ON predictions(camera_id, predicted_at DESC);
CREATE INDEX idx_predictions_type ON predictions(threat_type, predicted_at DESC);

-- ─── CLASSROOM MONITORING ─────────────────────────────────────────────────────
CREATE TABLE classroom_configs (
    camera_id               UUID PRIMARY KEY REFERENCES cameras(id) ON DELETE CASCADE,
    expected_students       INTEGER NOT NULL DEFAULT 30,
    teaching_zone           JSONB,   -- polygon points {x,y} normalized 0-1 marking the front-of-class area
    sleeping_secs_threshold FLOAT NOT NULL DEFAULT 15.0,
    talking_secs_threshold  FLOAT NOT NULL DEFAULT 8.0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE classroom_metrics (
    id                       BIGSERIAL,
    recorded_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    camera_id                UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    present_count            INTEGER NOT NULL DEFAULT 0,
    expected_count           INTEGER NOT NULL DEFAULT 0,
    missing_count            INTEGER NOT NULL DEFAULT 0,
    sleeping_count           INTEGER NOT NULL DEFAULT 0,
    talking_count            INTEGER NOT NULL DEFAULT 0,
    attentive_count          INTEGER NOT NULL DEFAULT 0,
    faculty_present          BOOLEAN NOT NULL DEFAULT FALSE,
    faculty_engagement_score FLOAT NOT NULL DEFAULT 0.0,
    attention_index          FLOAT NOT NULL DEFAULT 0.0,
    details                  JSONB DEFAULT '{}',
    PRIMARY KEY (id, recorded_at)
);

SELECT create_hypertable('classroom_metrics', 'recorded_at');
CREATE INDEX idx_classroom_metrics_camera ON classroom_metrics(camera_id, recorded_at DESC);
SELECT add_retention_policy('classroom_metrics', INTERVAL '90 days');

-- ─── TRACK HISTORY ───────────────────────────────────────────────────────────
CREATE TABLE track_history (
    id              BIGSERIAL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    camera_id       UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    track_id        INTEGER NOT NULL,
    position_x      FLOAT NOT NULL,
    position_y      FLOAT NOT NULL,
    velocity_x      FLOAT DEFAULT 0,
    velocity_y      FLOAT DEFAULT 0,
    speed           FLOAT DEFAULT 0,
    PRIMARY KEY (id, recorded_at)
);

SELECT create_hypertable('track_history', 'recorded_at');
CREATE INDEX idx_track_camera ON track_history(camera_id, track_id, recorded_at DESC);

-- ─── NOTIFICATIONS ───────────────────────────────────────────────────────────
CREATE TABLE notifications (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    alert_id    UUID REFERENCES alerts(id) ON DELETE CASCADE,
    channel     VARCHAR(50) NOT NULL CHECK (channel IN ('dashboard', 'email', 'sms')),
    status      VARCHAR(50) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'sent', 'delivered', 'failed')),
    sent_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── SYSTEM EVENTS LOG ───────────────────────────────────────────────────────
CREATE TABLE system_events (
    id          BIGSERIAL PRIMARY KEY,
    event_type  VARCHAR(100) NOT NULL,
    source      VARCHAR(100),
    message     TEXT,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_type ON system_events(event_type, created_at DESC);

-- ─── CONTINUOUS AGGREGATES (TimescaleDB) ─────────────────────────────────────
-- 5-minute detection aggregates per camera
CREATE MATERIALIZED VIEW detections_5min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', detected_at) AS bucket,
    camera_id,
    object_class,
    COUNT(*) AS detection_count,
    AVG(confidence) AS avg_confidence
FROM detections
GROUP BY bucket, camera_id, object_class
WITH NO DATA;

SELECT add_continuous_aggregate_policy('detections_5min',
    start_offset => INTERVAL '1 hour',
    end_offset   => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes');

-- Hourly CSI aggregates
CREATE MATERIALIZED VIEW csi_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', recorded_at) AS bucket,
    camera_id,
    AVG(overall_score) AS avg_score,
    MIN(overall_score) AS min_score,
    MAX(overall_score) AS max_score,
    MODE() WITHIN GROUP (ORDER BY risk_level) AS dominant_risk_level
FROM csi_scores
GROUP BY bucket, camera_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('csi_hourly',
    start_offset => INTERVAL '2 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

-- ─── DATA RETENTION POLICIES ─────────────────────────────────────────────────
SELECT add_retention_policy('detections',    INTERVAL '30 days');
SELECT add_retention_policy('behavior_logs', INTERVAL '90 days');
SELECT add_retention_policy('csi_scores',    INTERVAL '180 days');
SELECT add_retention_policy('predictions',   INTERVAL '30 days');
SELECT add_retention_policy('track_history', INTERVAL '7 days');

-- ─── DEFAULT ADMIN USER ──────────────────────────────────────────────────────
-- Password: Admin@123 (bcrypt hashed — change in production)
INSERT INTO users (email, username, full_name, role, hashed_password) VALUES
(
    'admin@campus-sentinel.local',
    'admin',
    'System Administrator',
    'superadmin',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5dPGZ5RxJSq6C'
);

-- ─── UPDATE TRIGGER ──────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at    BEFORE UPDATE ON users    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_cameras_updated_at  BEFORE UPDATE ON cameras  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_incidents_updated_at BEFORE UPDATE ON incidents FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_abd_updated_at      BEFORE UPDATE ON abd_profiles FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_classroom_configs_updated_at BEFORE UPDATE ON classroom_configs FOR EACH ROW EXECUTE FUNCTION update_updated_at();
