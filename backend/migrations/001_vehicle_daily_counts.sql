-- Additive/idempotent migration. Existing camera and alert records are preserved.
CREATE TABLE IF NOT EXISTS vehicle_daily_counts (
    camera_id UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    count_date DATE NOT NULL,
    in_count BIGINT NOT NULL DEFAULT 0 CHECK (in_count >= 0),
    out_count BIGINT NOT NULL DEFAULT 0 CHECK (out_count >= 0),
    total_count BIGINT NOT NULL DEFAULT 0 CHECK (total_count = in_count + out_count),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (camera_id, count_date)
);
CREATE TABLE IF NOT EXISTS vehicle_crossings (
    event_id UUID PRIMARY KEY,
    camera_id UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    count_date DATE NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('in', 'out'))
);
