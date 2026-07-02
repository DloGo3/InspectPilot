import argparse
import csv
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "defects.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
SAMPLE_CSV_PATH = BASE_DIR / "sample_defects.csv"

QUALITY_ROWS = [
    ("B20260614001", "F25061401", "P-A36-001", "2026-06-14T08:29:50", "2026-06-14T08:37:30", 120, 8, 12.0, "头部裂纹已确认"),
    ("B20260614002", "F25061401", "P-A36-001", "2026-06-14T08:40:10", "2026-06-14T08:48:20", 118, 5, 12.0, "底面轻微缺陷"),
    ("B20260614003", "F25061402", "P-A36-002", "2026-06-14T08:49:20", "2026-06-14T09:00:20", 124, 9, 12.0, "右面头部裂纹"),
    ("B20260614004", "F25061402", "P-A36-002", "2026-06-14T09:03:30", "2026-06-14T09:14:30", 126, 18, 12.0, "多面裂纹集中"),
    ("B20260614005", "F25061403", "P-B40-006", "2026-06-14T09:17:20", "2026-06-14T09:26:00", 116, 4, 12.0, "疑似氧化皮误检一条"),
    ("B20260614006", "F25061403", "P-B40-006", "2026-06-14T09:28:30", "2026-06-14T09:38:00", 122, 13, 12.0, "左面边部裂纹"),
    ("B20260614007", "F25061403", "P-B40-006", "2026-06-14T09:38:50", "2026-06-14T09:47:30", 121, 21, 12.0, "右面裂纹连续出现"),
    ("B20260614008", "F25061404", "P-C45-011", "2026-06-14T09:49:20", "2026-06-14T09:56:10", 115, 7, 12.0, "底面结疤与凹坑"),
    ("B20260614009", "F25061404", "P-C45-011", "2026-06-14T09:56:20", "2026-06-14T10:03:10", 117, 15, 12.0, "头部和右面裂纹"),
]

CAMERA2_SCENARIO = "camera2_imaging_abnormal"
QUALITY_WAVE_SCENARIO = "multi_camera_quality_wave"
SPARSE_SCENARIO = "sparse_evidence"


def _diagnostic_defect_events():
    rows = []

    def add(
        event_id,
        scenario_id,
        timestamp,
        billet_id,
        heat_no,
        plan_no,
        defect_type,
        camera_id,
        face,
        segment,
        position_zone,
        confidence,
        grade,
        bbox_x,
        bbox_y,
        bbox_w,
        bbox_h,
    ):
        rows.append(
            (
                event_id,
                scenario_id,
                timestamp,
                billet_id,
                heat_no,
                plan_no,
                defect_type,
                camera_id,
                face,
                segment,
                position_zone,
                confidence,
                grade,
                bbox_x,
                bbox_y,
                bbox_w,
                bbox_h,
            )
        )

    for index, item in enumerate(
        [
            ("2026-06-14T09:12:10", "B20260614020", "CAM01", "top", "middle", "center", 0.86),
            ("2026-06-14T09:36:44", "B20260614021", "CAM03", "bottom", "head", "edge", 0.82),
            ("2026-06-14T09:52:31", "B20260614022", "CAM04", "left", "tail", "center", 0.84),
        ],
        start=1,
    ):
        timestamp, billet_id, camera_id, face, segment, position_zone, confidence = item
        add(
            f"DE-A-B{index:02d}",
            CAMERA2_SCENARIO,
            timestamp,
            billet_id,
            "F25061405",
            "P-DIAG-A",
            "裂纹",
            camera_id,
            face,
            segment,
            position_zone,
            confidence,
            "critical",
            620,
            210,
            165,
            42,
        )

    camera2_target = [
        ("2026-06-14T10:02:11", "B20260614023", "head", "edge", 0.39, 80),
        ("2026-06-14T10:04:28", "B20260614023", "head", "edge", 0.42, 110),
        ("2026-06-14T10:07:02", "B20260614024", "head", "edge", 0.37, 74),
        ("2026-06-14T10:10:43", "B20260614024", "middle", "edge", 0.44, 1820),
        ("2026-06-14T10:14:59", "B20260614025", "head", "edge", 0.41, 95),
        ("2026-06-14T10:18:30", "B20260614025", "middle", "edge", 0.46, 1770),
        ("2026-06-14T10:21:16", "B20260614026", "head", "edge", 0.35, 69),
        ("2026-06-14T10:27:49", "B20260614026", "head", "edge", 0.48, 118),
        ("2026-06-14T10:33:12", "B20260614027", "middle", "edge", 0.43, 1815),
        ("2026-06-14T10:36:40", "B20260614027", "head", "edge", 0.40, 104),
    ]
    for index, item in enumerate(camera2_target, start=1):
        timestamp, billet_id, segment, position_zone, confidence, bbox_x = item
        add(
            f"DE-A-T{index:02d}",
            CAMERA2_SCENARIO,
            timestamp,
            billet_id,
            "F25061405",
            "P-DIAG-A",
            "裂纹",
            "CAM02",
            "right",
            segment,
            position_zone,
            confidence,
            "critical",
            bbox_x,
            220,
            155,
            38,
        )
    for index, item in enumerate(
        [
            ("2026-06-14T10:09:22", "B20260614024", "CAM01", "top", "middle", "center", 0.81),
            ("2026-06-14T10:31:05", "B20260614027", "CAM04", "left", "tail", "center", 0.79),
        ],
        start=1,
    ):
        timestamp, billet_id, camera_id, face, segment, position_zone, confidence = item
        add(
            f"DE-A-O{index:02d}",
            CAMERA2_SCENARIO,
            timestamp,
            billet_id,
            "F25061405",
            "P-DIAG-A",
            "裂纹",
            camera_id,
            face,
            segment,
            position_zone,
            confidence,
            "critical",
            760,
            240,
            160,
            42,
        )

    for index, item in enumerate(
        [
            ("2026-06-14T09:10:15", "B20260614030", "CAM01", "top", "head", "edge", 0.87),
            ("2026-06-14T09:39:27", "B20260614031", "CAM03", "bottom", "middle", "center", 0.84),
            ("2026-06-14T09:55:54", "B20260614032", "CAM04", "left", "tail", "edge", 0.88),
        ],
        start=1,
    ):
        timestamp, billet_id, camera_id, face, segment, position_zone, confidence = item
        add(
            f"DE-B-B{index:02d}",
            QUALITY_WAVE_SCENARIO,
            timestamp,
            billet_id,
            "F25061408",
            "P-DIAG-B",
            "裂纹",
            camera_id,
            face,
            segment,
            position_zone,
            confidence,
            "critical",
            880,
            260,
            180,
            45,
        )

    quality_target = [
        ("2026-06-14T10:01:15", "B20260614033", "CAM01", "top", "head", "edge", 0.91),
        ("2026-06-14T10:03:58", "B20260614033", "CAM02", "right", "middle", "center", 0.88),
        ("2026-06-14T10:06:21", "B20260614034", "CAM03", "bottom", "head", "center", 0.89),
        ("2026-06-14T10:08:33", "B20260614034", "CAM04", "left", "middle", "edge", 0.86),
        ("2026-06-14T10:12:48", "B20260614035", "CAM01", "top", "tail", "edge", 0.93),
        ("2026-06-14T10:16:07", "B20260614035", "CAM02", "right", "head", "edge", 0.90),
        ("2026-06-14T10:20:19", "B20260614036", "CAM03", "bottom", "middle", "center", 0.87),
        ("2026-06-14T10:24:52", "B20260614036", "CAM04", "left", "tail", "center", 0.85),
        ("2026-06-14T10:29:26", "B20260614037", "CAM01", "top", "middle", "edge", 0.92),
        ("2026-06-14T10:34:11", "B20260614037", "CAM02", "right", "tail", "center", 0.89),
        ("2026-06-14T10:36:49", "B20260614038", "CAM03", "bottom", "head", "edge", 0.88),
        ("2026-06-14T10:38:35", "B20260614038", "CAM04", "left", "middle", "center", 0.86),
    ]
    for index, item in enumerate(quality_target, start=1):
        timestamp, billet_id, camera_id, face, segment, position_zone, confidence = item
        add(
            f"DE-B-T{index:02d}",
            QUALITY_WAVE_SCENARIO,
            timestamp,
            billet_id,
            "F25061408",
            "P-DIAG-B",
            "裂纹",
            camera_id,
            face,
            segment,
            position_zone,
            confidence,
            "critical",
            920,
            260,
            175,
            44,
        )

    add(
        "DE-C-T01",
        SPARSE_SCENARIO,
        "2026-06-14T10:12:00",
        "B20260614040",
        "F25061409",
        "P-DIAG-C",
        "裂纹",
        "CAM02",
        "right",
        "head",
        "edge",
        0.58,
        "critical",
        120,
        200,
        160,
        40,
    )
    return rows


def _diagnostic_camera_status_rows():
    rows = []

    def add(status_id, scenario_id, timestamp, camera_id, fps, temperature, brightness, exposure, gain, black_rate, empty_rate, status):
        rows.append(
            (
                status_id,
                scenario_id,
                timestamp,
                camera_id,
                fps,
                temperature,
                brightness,
                exposure,
                gain,
                black_rate,
                empty_rate,
                status,
            )
        )

    for index, timestamp in enumerate(["2026-06-14T09:20:00", "2026-06-14T09:40:00"], start=1):
        for camera_id in ["CAM01", "CAM02", "CAM03", "CAM04"]:
            add(
                f"CS-A-B{index}-{camera_id}",
                CAMERA2_SCENARIO,
                timestamp,
                camera_id,
                18.0,
                42.0,
                0.68,
                5.2,
                1.1,
                0.002,
                0.001,
                "normal",
            )

    for index, timestamp in enumerate(["2026-06-14T10:05:00", "2026-06-14T10:20:00", "2026-06-14T10:35:00"], start=1):
        add(
            f"CS-A-T{index}-CAM02",
            CAMERA2_SCENARIO,
            timestamp,
            "CAM02",
            [8.0, 7.2, 8.5][index - 1],
            [54.0, 56.5, 55.0][index - 1],
            [0.40, 0.36, 0.38][index - 1],
            4.1,
            1.8,
            [0.052, 0.067, 0.058][index - 1],
            [0.028, 0.035, 0.030][index - 1],
            "degraded",
        )
        for camera_id in ["CAM01", "CAM03", "CAM04"]:
            add(
                f"CS-A-T{index}-{camera_id}",
                CAMERA2_SCENARIO,
                timestamp,
                camera_id,
                17.5,
                43.0,
                0.66,
                5.2,
                1.1,
                0.003,
                0.001,
                "normal",
            )

    for scenario_id, prefix in [(QUALITY_WAVE_SCENARIO, "B")]:
        for index, timestamp in enumerate(
            ["2026-06-14T09:20:00", "2026-06-14T09:40:00", "2026-06-14T10:05:00", "2026-06-14T10:20:00", "2026-06-14T10:35:00"],
            start=1,
        ):
            for camera_id in ["CAM01", "CAM02", "CAM03", "CAM04"]:
                add(
                    f"CS-{prefix}-{index}-{camera_id}",
                    scenario_id,
                    timestamp,
                    camera_id,
                    18.0,
                    42.5,
                    0.67,
                    5.2,
                    1.1,
                    0.003,
                    0.001,
                    "normal",
                )
    return rows


def _diagnostic_image_quality_rows():
    rows = []

    def add(metric_id, scenario_id, timestamp, camera_id, billet_id, brightness, blur_score, overexposure, black_ratio, edge_ratio, file_size, status):
        rows.append(
            (
                metric_id,
                scenario_id,
                timestamp,
                camera_id,
                billet_id,
                brightness,
                blur_score,
                overexposure,
                black_ratio,
                edge_ratio,
                file_size,
                status,
            )
        )

    for index, item in enumerate(
        [
            ("2026-06-14T09:28:00", "B20260614020", "CAM02", 0.68, 0.76, 0.011, 0.004, 0.28, 510, "normal"),
            ("2026-06-14T09:48:00", "B20260614022", "CAM02", 0.67, 0.74, 0.012, 0.005, 0.31, 505, "normal"),
            ("2026-06-14T10:04:00", "B20260614023", "CAM02", 0.39, 0.42, 0.006, 0.058, 0.82, 335, "dark_edge"),
            ("2026-06-14T10:12:00", "B20260614024", "CAM02", 0.35, 0.38, 0.005, 0.072, 0.86, 318, "dark_edge"),
            ("2026-06-14T10:24:00", "B20260614026", "CAM02", 0.37, 0.40, 0.006, 0.061, 0.79, 326, "dark_edge"),
            ("2026-06-14T10:35:00", "B20260614027", "CAM02", 0.38, 0.43, 0.007, 0.057, 0.81, 332, "dark_edge"),
        ],
        start=1,
    ):
        timestamp, billet_id, camera_id, brightness, blur, over, black, edge, size, status = item
        add(f"IQ-A-{index:02d}", CAMERA2_SCENARIO, timestamp, camera_id, billet_id, brightness, blur, over, black, edge, size, status)

    for index, item in enumerate(
        [
            ("2026-06-14T10:05:00", "B20260614033", "CAM01"),
            ("2026-06-14T10:08:00", "B20260614034", "CAM02"),
            ("2026-06-14T10:18:00", "B20260614035", "CAM03"),
            ("2026-06-14T10:26:00", "B20260614036", "CAM04"),
            ("2026-06-14T10:34:00", "B20260614037", "CAM01"),
            ("2026-06-14T10:38:00", "B20260614038", "CAM03"),
        ],
        start=1,
    ):
        timestamp, billet_id, camera_id = item
        add(f"IQ-B-{index:02d}", QUALITY_WAVE_SCENARIO, timestamp, camera_id, billet_id, 0.66, 0.73, 0.012, 0.004, 0.36, 508, "normal")

    return rows


def init_database(db_path: Path = DEFAULT_DB_PATH, reset: bool = False) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        if reset:
            conn.execute("DELETE FROM defect_records")
            conn.execute("DELETE FROM billet_quality")
            conn.execute("DELETE FROM defect_events")
            conn.execute("DELETE FROM camera_status")
            conn.execute("DELETE FROM image_quality_metrics")

        with SAMPLE_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO defect_records (
                        defect_id, timestamp, billet_id, furnace_no, plan_no,
                        camera_id, face_id, defect_type, confidence, bbox, image_path,
                        length_pos, width_pos, severity, review_status, frame_no,
                        billet_speed_mps, image_width, image_height, length_region, width_region
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["defect_id"],
                        row["timestamp"],
                        row["billet_id"],
                        row["furnace_no"],
                        row["plan_no"],
                        row["camera_id"],
                        row["face_id"],
                        row["defect_type"],
                        float(row["confidence"]),
                        row["bbox"],
                        row["image_path"],
                        float(row["length_pos"]),
                        float(row["width_pos"]),
                        row["severity"],
                        row["review_status"],
                        int(row["frame_no"]),
                        float(row["billet_speed_mps"]),
                        int(row["image_width"]),
                        int(row["image_height"]),
                        row["length_region"],
                        row["width_region"],
                    ),
                )

        for item in QUALITY_ROWS:
            conn.execute(
                """
                INSERT OR REPLACE INTO billet_quality (
                    billet_id, furnace_no, plan_no, start_time, end_time,
                    inspected_frames, ng_frames, billet_length_m, remark
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                item,
            )

        for item in _diagnostic_defect_events():
            conn.execute(
                """
                INSERT OR REPLACE INTO defect_events (
                    event_id, scenario_id, timestamp, billet_id, heat_no, plan_no,
                    defect_type, camera_id, face, segment, position_zone,
                    confidence, grade, bbox_x, bbox_y, bbox_w, bbox_h
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                item,
            )

        for item in _diagnostic_camera_status_rows():
            conn.execute(
                """
                INSERT OR REPLACE INTO camera_status (
                    status_id, scenario_id, timestamp, camera_id, fps, temperature,
                    brightness, exposure, gain, black_frame_rate, empty_frame_rate, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                item,
            )

        for item in _diagnostic_image_quality_rows():
            conn.execute(
                """
                INSERT OR REPLACE INTO image_quality_metrics (
                    metric_id, scenario_id, timestamp, camera_id, billet_id,
                    avg_brightness, blur_score, overexposure_ratio, black_ratio,
                    edge_box_ratio, file_size_kb, quality_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                item,
            )

        conn.commit()

    return db_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize InspectPilot SQLite database.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite db path")
    parser.add_argument("--reset", action="store_true", help="Clear existing sample data first")
    args = parser.parse_args()
    path = init_database(Path(args.db), reset=args.reset)
    print(f"SQLite database initialized: {path}")
