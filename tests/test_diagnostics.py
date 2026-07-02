import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from agent.graph import run_agent
from data.init_db import init_database
from tools.diagnostic_tools import (
    analyze_camera_health,
    analyze_defect_camera_concentration,
    analyze_image_quality,
    detect_defect_spike,
    estimate_false_positive_risk,
)


def _db_path() -> Path:
    path = BACKEND_DIR / "data" / "test_diagnostics_runtime.db"
    init_database(path, reset=True)
    return path


def test_camera2_spike_diagnosis_prefers_imaging_abnormality():
    db_path = _db_path()

    spike = detect_defect_spike(db_path=str(db_path))
    assert spike["status"] == "spike_detected"
    assert spike["key_metrics"]["target_count"] == 12

    concentration = analyze_defect_camera_concentration(db_path=str(db_path))
    assert concentration["status"] == "single_camera_concentrated"
    assert concentration["key_metrics"]["top_camera"] == "CAM02"

    health = analyze_camera_health(camera_id="CAM02", db_path=str(db_path))
    assert health["status"] == "abnormal"
    assert health["key_metrics"]["fps_drop_pct"] > 30

    quality = analyze_image_quality(camera_id="CAM02", db_path=str(db_path))
    assert quality["status"] == "abnormal"
    assert quality["key_metrics"]["edge_box_ratio"] > 0.7

    diagnosis = estimate_false_positive_risk(camera_id="CAM02", db_path=str(db_path))
    assert diagnosis["root_cause"] == "camera_imaging_abnormal"
    assert diagnosis["false_positive_risk"] == "high"


def test_multi_camera_spike_prefers_quality_wave():
    db_path = _db_path()
    diagnosis = estimate_false_positive_risk(
        scenario_id="multi_camera_quality_wave",
        db_path=str(db_path),
    )

    assert diagnosis["root_cause"] == "quality_wave"
    assert diagnosis["false_positive_risk"] == "low"
    assert diagnosis["key_metrics"]["affected_cameras"] == 4


def test_agent_diagnostic_answer_is_structured_offline():
    init_database(BACKEND_DIR / "data" / "defects.db", reset=True)
    state = run_agent("今天 10 点后裂纹突然增多，请判断是真实质量异常，还是检测系统异常。", force_fallback=True)

    assert state["intent"] == "diagnosis"
    assert state["diagnosis"]["root_cause"] == "camera_imaging_abnormal"
    assert "【结论】" in state["answer"]
    assert "【关键证据】" in state["answer"]
    assert "【建议动作】" in state["answer"]
    assert "暂不应直接判定为真实质量事故" in state["answer"]
