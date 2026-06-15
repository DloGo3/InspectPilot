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

