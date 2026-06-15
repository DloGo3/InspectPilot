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


def init_database(db_path: Path = DEFAULT_DB_PATH, reset: bool = False) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        if reset:
            conn.execute("DELETE FROM defect_records")
            conn.execute("DELETE FROM billet_quality")

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

        conn.commit()

    return db_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize InspectPilot SQLite database.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite db path")
    parser.add_argument("--reset", action="store_true", help="Clear existing sample data first")
    args = parser.parse_args()
    path = init_database(Path(args.db), reset=args.reset)
    print(f"SQLite database initialized: {path}")

