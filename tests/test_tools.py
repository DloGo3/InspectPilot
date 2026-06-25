import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from data.init_db import init_database
from tools.defect_tools import group_defects_by_type, query_defect_stats


def test_stats_and_grouping():
    db_path = BACKEND_DIR / "data" / "test_defects_runtime.db"
    init_database(db_path, reset=True)

    stats = query_defect_stats(db_path=str(db_path))
    assert stats["total_defects"] == 27
    assert stats["affected_billets"] == 9

    grouped = group_defects_by_type(db_path=str(db_path))
    assert grouped["items"][0]["defect_count"] >= 1
