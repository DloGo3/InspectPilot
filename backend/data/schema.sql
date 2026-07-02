CREATE TABLE IF NOT EXISTS defect_records (
    defect_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    billet_id TEXT NOT NULL,
    furnace_no TEXT NOT NULL,
    plan_no TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    face_id TEXT NOT NULL,
    defect_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    bbox TEXT NOT NULL,
    image_path TEXT NOT NULL,
    length_pos REAL NOT NULL,
    width_pos REAL NOT NULL,
    severity TEXT NOT NULL,
    review_status TEXT NOT NULL,
    frame_no INTEGER,
    billet_speed_mps REAL,
    image_width INTEGER,
    image_height INTEGER,
    length_region TEXT,
    width_region TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_defect_timestamp ON defect_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_defect_type ON defect_records(defect_type);
CREATE INDEX IF NOT EXISTS idx_defect_face ON defect_records(face_id);
CREATE INDEX IF NOT EXISTS idx_defect_furnace ON defect_records(furnace_no);
CREATE INDEX IF NOT EXISTS idx_defect_plan ON defect_records(plan_no);
CREATE INDEX IF NOT EXISTS idx_defect_billet ON defect_records(billet_id);
CREATE INDEX IF NOT EXISTS idx_defect_position ON defect_records(length_region, width_region);

CREATE TABLE IF NOT EXISTS billet_quality (
    billet_id TEXT PRIMARY KEY,
    furnace_no TEXT NOT NULL,
    plan_no TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    inspected_frames INTEGER NOT NULL,
    ng_frames INTEGER NOT NULL,
    billet_length_m REAL,
    remark TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_quality_furnace ON billet_quality(furnace_no);
CREATE INDEX IF NOT EXISTS idx_quality_plan ON billet_quality(plan_no);
CREATE INDEX IF NOT EXISTS idx_quality_time ON billet_quality(start_time, end_time);

CREATE TABLE IF NOT EXISTS defect_events (
    event_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    billet_id TEXT NOT NULL,
    heat_no TEXT NOT NULL,
    plan_no TEXT NOT NULL,
    defect_type TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    face TEXT NOT NULL,
    segment TEXT NOT NULL,
    position_zone TEXT NOT NULL,
    confidence REAL NOT NULL,
    grade TEXT NOT NULL,
    bbox_x REAL NOT NULL,
    bbox_y REAL NOT NULL,
    bbox_w REAL NOT NULL,
    bbox_h REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_event_scenario_time ON defect_events(scenario_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_event_defect_type ON defect_events(defect_type);
CREATE INDEX IF NOT EXISTS idx_event_camera ON defect_events(camera_id);
CREATE INDEX IF NOT EXISTS idx_event_billet ON defect_events(billet_id);

CREATE TABLE IF NOT EXISTS camera_status (
    status_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    fps REAL NOT NULL,
    temperature REAL NOT NULL,
    brightness REAL NOT NULL,
    exposure REAL NOT NULL,
    gain REAL NOT NULL,
    black_frame_rate REAL NOT NULL,
    empty_frame_rate REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_camera_status_scenario_time ON camera_status(scenario_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_camera_status_camera ON camera_status(camera_id);

CREATE TABLE IF NOT EXISTS image_quality_metrics (
    metric_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    billet_id TEXT NOT NULL,
    avg_brightness REAL NOT NULL,
    blur_score REAL NOT NULL,
    overexposure_ratio REAL NOT NULL,
    black_ratio REAL NOT NULL,
    edge_box_ratio REAL NOT NULL,
    file_size_kb REAL NOT NULL,
    quality_status TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_image_quality_scenario_time ON image_quality_metrics(scenario_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_image_quality_camera ON image_quality_metrics(camera_id);
CREATE INDEX IF NOT EXISTS idx_image_quality_billet ON image_quality_metrics(billet_id);
