from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from tools.defect_tools import get_connection

DEFAULT_SCENARIO_ID = "camera2_imaging_abnormal"
QUALITY_WAVE_SCENARIO_ID = "multi_camera_quality_wave"
SPARSE_SCENARIO_ID = "sparse_evidence"
DEFAULT_DEFECT_TYPE = "裂纹"
DEFAULT_ANALYSIS_START = "2026-06-14T10:00:00"
DEFAULT_TARGET_END = "2026-06-14T10:40:00"


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _default_baseline_start(analysis_start: str) -> str:
    return (_parse_dt(analysis_start) - timedelta(hours=1)).isoformat(timespec="seconds")


def _window(
    analysis_start: Optional[str],
    baseline_start: Optional[str],
    baseline_end: Optional[str],
    target_end: Optional[str],
) -> Tuple[str, str, str]:
    start = analysis_start or DEFAULT_ANALYSIS_START
    return baseline_start or _default_baseline_start(start), baseline_end or start, target_end or DEFAULT_TARGET_END


def _duration_hours(start_time: str, end_time: str) -> float:
    seconds = max((_parse_dt(end_time) - _parse_dt(start_time)).total_seconds(), 1.0)
    return seconds / 3600.0


def _safe_pct(part: float, total: float) -> float:
    return round(part / total * 100, 2) if total else 0.0


def _round(value: Optional[float], digits: int = 4) -> Optional[float]:
    return round(value, digits) if value is not None else None


def _avg(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return sum(values) / len(values) if values else None


def _defect_rows(
    scenario_id: str,
    defect_type: str,
    start_time: str,
    end_time: str,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM defect_events
            WHERE scenario_id = ?
              AND defect_type = ?
              AND timestamp >= ?
              AND timestamp <= ?
            ORDER BY timestamp ASC
            """,
            (scenario_id, defect_type, start_time, end_time),
        ).fetchall()
    return [dict(row) for row in rows]


def _camera_status_rows(
    scenario_id: str,
    camera_id: str,
    start_time: str,
    end_time: str,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM camera_status
            WHERE scenario_id = ?
              AND camera_id = ?
              AND timestamp >= ?
              AND timestamp <= ?
            ORDER BY timestamp ASC
            """,
            (scenario_id, camera_id, start_time, end_time),
        ).fetchall()
    return [dict(row) for row in rows]


def _image_quality_rows(
    scenario_id: str,
    camera_id: str,
    start_time: str,
    end_time: str,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM image_quality_metrics
            WHERE scenario_id = ?
              AND camera_id = ?
              AND timestamp >= ?
              AND timestamp <= ?
            ORDER BY timestamp ASC
            """,
            (scenario_id, camera_id, start_time, end_time),
        ).fetchall()
    return [dict(row) for row in rows]


def _camera_counts(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total = len(rows)
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        camera_id = row["camera_id"]
        item = grouped.setdefault(
            camera_id,
            {
                "camera_id": camera_id,
                "defect_count": 0,
                "low_confidence_count": 0,
                "edge_count": 0,
                "confidence_sum": 0.0,
                "faces": set(),
                "segments": set(),
                "position_zones": set(),
                "billets": set(),
            },
        )
        item["defect_count"] += 1
        item["confidence_sum"] += float(row["confidence"])
        if float(row["confidence"]) < 0.5:
            item["low_confidence_count"] += 1
        if row["position_zone"] == "edge":
            item["edge_count"] += 1
        item["faces"].add(row["face"])
        item["segments"].add(row["segment"])
        item["position_zones"].add(row["position_zone"])
        item["billets"].add(row["billet_id"])

    output = []
    for item in grouped.values():
        count = item["defect_count"]
        output.append(
            {
                "camera_id": item["camera_id"],
                "defect_count": count,
                "ratio_pct": _safe_pct(count, total),
                "avg_confidence": round(item["confidence_sum"] / count, 4) if count else 0.0,
                "low_confidence_ratio_pct": _safe_pct(item["low_confidence_count"], count),
                "edge_ratio_pct": _safe_pct(item["edge_count"], count),
                "faces": sorted(item["faces"]),
                "segments": sorted(item["segments"]),
                "position_zones": sorted(item["position_zones"]),
                "affected_billets": len(item["billets"]),
            }
        )
    return sorted(output, key=lambda item: (-item["defect_count"], item["camera_id"]))


def _infer_target_camera(
    scenario_id: str,
    defect_type: str,
    analysis_start: str,
    target_end: str,
    db_path: Optional[str] = None,
) -> Optional[str]:
    rows = _defect_rows(scenario_id, defect_type, analysis_start, target_end, db_path)
    counts = _camera_counts(rows)
    return counts[0]["camera_id"] if counts else None


def detect_defect_spike(
    scenario_id: str = DEFAULT_SCENARIO_ID,
    defect_type: str = DEFAULT_DEFECT_TYPE,
    analysis_start: Optional[str] = None,
    baseline_start: Optional[str] = None,
    baseline_end: Optional[str] = None,
    target_end: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    baseline_start, baseline_end, target_end = _window(analysis_start, baseline_start, baseline_end, target_end)
    analysis_start = analysis_start or DEFAULT_ANALYSIS_START
    baseline_rows = _defect_rows(scenario_id, defect_type, baseline_start, baseline_end, db_path)
    target_rows = _defect_rows(scenario_id, defect_type, analysis_start, target_end, db_path)
    baseline_count = len(baseline_rows)
    target_count = len(target_rows)
    baseline_rate = baseline_count / _duration_hours(baseline_start, baseline_end)
    target_rate = target_count / _duration_hours(analysis_start, target_end)
    spike_ratio = None if baseline_rate == 0 else target_rate / baseline_rate
    spike = target_count >= 3 and (baseline_count == 0 or target_rate >= max(3.0, baseline_rate * 2.0))
    status = "spike_detected" if spike else ("no_data" if target_count == 0 else "no_significant_spike")

    if spike_ratio is None and target_count > 0:
        ratio_text = "基线为 0，无法计算稳定倍数"
    else:
        ratio_text = f"增幅约 {round(spike_ratio or 0, 2)} 倍"
    summary = (
        f"{analysis_start} 后 {defect_type} {target_count} 条，"
        f"基线窗口 {baseline_count} 条，{ratio_text}。"
    )
    evidence = [
        f"基线窗口 {baseline_start} 至 {baseline_end}: {baseline_count} 条，速率 {round(baseline_rate, 2)} 条/小时",
        f"目标窗口 {analysis_start} 至 {target_end}: {target_count} 条，速率 {round(target_rate, 2)} 条/小时",
    ]
    if spike:
        evidence.append("目标窗口缺陷速率达到突增阈值，进入异常诊断流程")

    return {
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "key_metrics": {
            "scenario_id": scenario_id,
            "defect_type": defect_type,
            "baseline_count": baseline_count,
            "target_count": target_count,
            "baseline_rate_per_hour": round(baseline_rate, 4),
            "target_rate_per_hour": round(target_rate, 4),
            "spike_ratio": _round(spike_ratio),
            "analysis_start": analysis_start,
            "target_end": target_end,
        },
        "warnings": [] if target_count else ["target_window_has_no_defect_events"],
    }


def analyze_defect_camera_concentration(
    scenario_id: str = DEFAULT_SCENARIO_ID,
    defect_type: str = DEFAULT_DEFECT_TYPE,
    analysis_start: Optional[str] = None,
    baseline_start: Optional[str] = None,
    baseline_end: Optional[str] = None,
    target_end: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    _, _, target_end = _window(analysis_start, baseline_start, baseline_end, target_end)
    analysis_start = analysis_start or DEFAULT_ANALYSIS_START
    rows = _defect_rows(scenario_id, defect_type, analysis_start, target_end, db_path)
    total = len(rows)
    counts = _camera_counts(rows)
    if not counts:
        return {
            "status": "no_data",
            "summary": "目标窗口没有可用于相机集中度分析的缺陷事件。",
            "evidence": [],
            "key_metrics": {"scenario_id": scenario_id, "defect_type": defect_type, "total": 0},
            "warnings": ["no_target_defect_events"],
        }

    top = counts[0]
    affected_cameras = len(counts)
    affected_billets = len({row["billet_id"] for row in rows})
    status = "single_camera_concentrated" if top["ratio_pct"] >= 60 else "multi_camera_distributed"
    summary = (
        f"{defect_type} 共 {total} 条，Top 相机 {top['camera_id']} "
        f"{top['defect_count']} 条，占比 {top['ratio_pct']}%。"
    )
    evidence = [
        f"涉及 {affected_cameras} 台相机、{affected_billets} 支方坯",
        f"{top['camera_id']} 平均置信度 {top['avg_confidence']}，低置信度占比 {top['low_confidence_ratio_pct']}%",
        f"{top['camera_id']} 边部框占比 {top['edge_ratio_pct']}%，表面 {','.join(top['faces'])}",
    ]
    if status == "single_camera_concentrated":
        evidence.append("缺陷高度集中在单相机，需优先排查该相机成像和采集状态")
    else:
        evidence.append("缺陷分布在多台相机，单相机成像异常解释力较弱")

    return {
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "key_metrics": {
            "scenario_id": scenario_id,
            "defect_type": defect_type,
            "total": total,
            "affected_cameras": affected_cameras,
            "affected_billets": affected_billets,
            "top_camera": top["camera_id"],
            "top_camera_ratio_pct": top["ratio_pct"],
            "top_camera_avg_confidence": top["avg_confidence"],
            "top_camera_low_confidence_ratio_pct": top["low_confidence_ratio_pct"],
            "top_camera_edge_ratio_pct": top["edge_ratio_pct"],
            "camera_counts": counts,
        },
        "warnings": [],
    }


def analyze_camera_health(
    scenario_id: str = DEFAULT_SCENARIO_ID,
    camera_id: Optional[str] = None,
    defect_type: str = DEFAULT_DEFECT_TYPE,
    analysis_start: Optional[str] = None,
    baseline_start: Optional[str] = None,
    baseline_end: Optional[str] = None,
    target_end: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    baseline_start, baseline_end, target_end = _window(analysis_start, baseline_start, baseline_end, target_end)
    analysis_start = analysis_start or DEFAULT_ANALYSIS_START
    camera_id = camera_id or _infer_target_camera(scenario_id, defect_type, analysis_start, target_end, db_path)
    if not camera_id:
        return {
            "status": "no_data",
            "summary": "缺少目标相机，无法分析相机健康状态。",
            "evidence": [],
            "key_metrics": {"scenario_id": scenario_id},
            "warnings": ["missing_camera_id"],
        }

    baseline_rows = _camera_status_rows(scenario_id, camera_id, baseline_start, baseline_end, db_path)
    target_rows = _camera_status_rows(scenario_id, camera_id, analysis_start, target_end, db_path)
    if not target_rows:
        return {
            "status": "no_data",
            "summary": f"{camera_id} 在目标窗口缺少相机状态数据。",
            "evidence": [],
            "key_metrics": {"scenario_id": scenario_id, "camera_id": camera_id},
            "warnings": ["missing_target_camera_status"],
        }

    baseline_fps = _avg(baseline_rows, "fps")
    target_fps = _avg(target_rows, "fps")
    baseline_brightness = _avg(baseline_rows, "brightness")
    target_brightness = _avg(target_rows, "brightness")
    target_temperature = _avg(target_rows, "temperature")
    target_black_rate = _avg(target_rows, "black_frame_rate") or 0.0
    target_empty_rate = _avg(target_rows, "empty_frame_rate") or 0.0
    fps_drop_pct = _safe_pct((baseline_fps or target_fps or 0) - (target_fps or 0), baseline_fps or 0)
    brightness_drop_pct = _safe_pct((baseline_brightness or target_brightness or 0) - (target_brightness or 0), baseline_brightness or 0)

    reasons: List[str] = []
    if fps_drop_pct >= 30:
        reasons.append(f"FPS 下降 {round(fps_drop_pct, 2)}%")
    if brightness_drop_pct >= 25:
        reasons.append(f"亮度下降 {round(brightness_drop_pct, 2)}%")
    if target_black_rate >= 0.03:
        reasons.append(f"黑帧比例升至 {round(target_black_rate * 100, 2)}%")
    if target_empty_rate >= 0.02:
        reasons.append(f"空帧比例升至 {round(target_empty_rate * 100, 2)}%")
    if target_temperature and target_temperature >= 52:
        reasons.append(f"温度升至 {round(target_temperature, 2)}")

    status = "abnormal" if reasons else "normal"
    summary = f"{camera_id} 相机状态{('异常：' + '；'.join(reasons)) if reasons else '基本正常'}。"
    evidence = [
        f"基线 FPS={_round(baseline_fps)}，目标 FPS={_round(target_fps)}",
        f"基线亮度={_round(baseline_brightness)}，目标亮度={_round(target_brightness)}",
        f"目标黑帧比例={round(target_black_rate * 100, 2)}%，空帧比例={round(target_empty_rate * 100, 2)}%",
    ]
    if reasons:
        evidence.extend(reasons)

    return {
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "key_metrics": {
            "scenario_id": scenario_id,
            "camera_id": camera_id,
            "baseline_fps": _round(baseline_fps),
            "target_fps": _round(target_fps),
            "fps_drop_pct": round(fps_drop_pct, 2),
            "baseline_brightness": _round(baseline_brightness),
            "target_brightness": _round(target_brightness),
            "brightness_drop_pct": round(brightness_drop_pct, 2),
            "target_temperature": _round(target_temperature),
            "target_black_frame_rate": _round(target_black_rate),
            "target_empty_frame_rate": _round(target_empty_rate),
            "abnormal_reasons": reasons,
        },
        "warnings": [] if baseline_rows else ["missing_baseline_camera_status"],
    }


def analyze_image_quality(
    scenario_id: str = DEFAULT_SCENARIO_ID,
    camera_id: Optional[str] = None,
    defect_type: str = DEFAULT_DEFECT_TYPE,
    analysis_start: Optional[str] = None,
    baseline_start: Optional[str] = None,
    baseline_end: Optional[str] = None,
    target_end: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    _, _, target_end = _window(analysis_start, baseline_start, baseline_end, target_end)
    analysis_start = analysis_start or DEFAULT_ANALYSIS_START
    camera_id = camera_id or _infer_target_camera(scenario_id, defect_type, analysis_start, target_end, db_path)
    if not camera_id:
        return {
            "status": "no_data",
            "summary": "缺少目标相机，无法分析图像质量。",
            "evidence": [],
            "key_metrics": {"scenario_id": scenario_id},
            "warnings": ["missing_camera_id"],
        }

    rows = _image_quality_rows(scenario_id, camera_id, analysis_start, target_end, db_path)
    if not rows:
        return {
            "status": "no_data",
            "summary": f"{camera_id} 在目标窗口缺少图像质量数据。",
            "evidence": [],
            "key_metrics": {"scenario_id": scenario_id, "camera_id": camera_id},
            "warnings": ["missing_image_quality_metrics"],
        }

    avg_brightness = _avg(rows, "avg_brightness") or 0.0
    blur_score = _avg(rows, "blur_score") or 0.0
    overexposure_ratio = _avg(rows, "overexposure_ratio") or 0.0
    black_ratio = _avg(rows, "black_ratio") or 0.0
    edge_box_ratio = _avg(rows, "edge_box_ratio") or 0.0
    low_quality_count = len([row for row in rows if row["quality_status"] != "normal"])
    low_quality_ratio_pct = _safe_pct(low_quality_count, len(rows))

    reasons: List[str] = []
    if avg_brightness < 0.45:
        reasons.append(f"平均亮度偏低 {round(avg_brightness, 4)}")
    if blur_score < 0.5:
        reasons.append(f"清晰度评分偏低 {round(blur_score, 4)}")
    if black_ratio >= 0.04:
        reasons.append(f"黑色区域比例偏高 {round(black_ratio * 100, 2)}%")
    if edge_box_ratio >= 0.7:
        reasons.append(f"检测框边缘占比偏高 {round(edge_box_ratio * 100, 2)}%")
    if low_quality_ratio_pct >= 40:
        reasons.append(f"低质量图像占比 {low_quality_ratio_pct}%")

    status = "abnormal" if reasons else "normal"
    summary = f"{camera_id} 图像质量{('异常：' + '；'.join(reasons)) if reasons else '基本正常'}。"
    evidence = [
        f"平均亮度={round(avg_brightness, 4)}，清晰度评分={round(blur_score, 4)}",
        f"黑色区域比例={round(black_ratio * 100, 2)}%，检测框边缘占比={round(edge_box_ratio * 100, 2)}%",
        f"低质量图像占比={low_quality_ratio_pct}%",
    ]
    if reasons:
        evidence.extend(reasons)

    return {
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "key_metrics": {
            "scenario_id": scenario_id,
            "camera_id": camera_id,
            "avg_brightness": round(avg_brightness, 4),
            "blur_score": round(blur_score, 4),
            "overexposure_ratio": round(overexposure_ratio, 4),
            "black_ratio": round(black_ratio, 4),
            "edge_box_ratio": round(edge_box_ratio, 4),
            "low_quality_ratio_pct": low_quality_ratio_pct,
            "quality_reasons": reasons,
        },
        "warnings": [],
    }


def estimate_false_positive_risk(
    scenario_id: str = DEFAULT_SCENARIO_ID,
    defect_type: str = DEFAULT_DEFECT_TYPE,
    camera_id: Optional[str] = None,
    analysis_start: Optional[str] = None,
    baseline_start: Optional[str] = None,
    baseline_end: Optional[str] = None,
    target_end: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    baseline_start, baseline_end, target_end = _window(analysis_start, baseline_start, baseline_end, target_end)
    analysis_start = analysis_start or DEFAULT_ANALYSIS_START

    spike = detect_defect_spike(
        scenario_id,
        defect_type,
        analysis_start,
        baseline_start,
        baseline_end,
        target_end,
        db_path,
    )
    concentration = analyze_defect_camera_concentration(
        scenario_id,
        defect_type,
        analysis_start,
        baseline_start,
        baseline_end,
        target_end,
        db_path,
    )
    camera_id = camera_id or concentration.get("key_metrics", {}).get("top_camera")
    health = analyze_camera_health(
        scenario_id,
        camera_id,
        defect_type,
        analysis_start,
        baseline_start,
        baseline_end,
        target_end,
        db_path,
    )
    quality = analyze_image_quality(
        scenario_id,
        camera_id,
        defect_type,
        analysis_start,
        baseline_start,
        baseline_end,
        target_end,
        db_path,
    )

    spike_metrics = spike.get("key_metrics", {})
    concentration_metrics = concentration.get("key_metrics", {})
    health_metrics = health.get("key_metrics", {})
    quality_metrics = quality.get("key_metrics", {})
    target_count = int(spike_metrics.get("target_count") or 0)
    affected_cameras = int(concentration_metrics.get("affected_cameras") or 0)
    affected_billets = int(concentration_metrics.get("affected_billets") or 0)
    top_ratio = float(concentration_metrics.get("top_camera_ratio_pct") or 0)
    avg_confidence = float(concentration_metrics.get("top_camera_avg_confidence") or 0)
    low_conf_ratio = float(concentration_metrics.get("top_camera_low_confidence_ratio_pct") or 0)
    edge_ratio = float(concentration_metrics.get("top_camera_edge_ratio_pct") or 0)
    target_camera = camera_id or "unknown"

    if target_count < 3:
        evidence = spike.get("evidence", []) + ["目标窗口有效缺陷数量不足，不能做稳定根因判断"]
        return {
            "status": "insufficient_evidence",
            "diagnosis_intent": "defect_spike_root_cause",
            "summary": "当前证据不足以判断裂纹突增根因。",
            "conclusion": "当前证据不足，无法硬判是真实质量异常或检测系统异常，应先补齐相机状态、图像质量和人工复核结果。",
            "false_positive_risk": "unknown",
            "root_cause": "insufficient_evidence",
            "root_cause_candidates": [
                {
                    "name": "真实质量波动",
                    "likelihood": "unknown",
                    "evidence": ["缺陷事件数量不足"],
                },
                {
                    "name": "检测系统异常/误检",
                    "likelihood": "unknown",
                    "evidence": ["缺少足够相机状态和图像质量证据"],
                },
            ],
            "recommended_actions": ["补齐相机状态、图像质量和原图复核记录", "不要只凭单条缺陷记录判定质量事故或工艺事故"],
            "missing_data": ["更多目标窗口缺陷样本", "相机 FPS/亮度/黑帧记录", "图像质量指标", "人工复核结果"],
            "evidence": evidence,
            "key_metrics": {"scenario_id": scenario_id, "target_count": target_count},
            "warnings": ["insufficient_diagnostic_evidence"],
        }

    false_positive_score = 0
    quality_score = 0
    if concentration.get("status") == "single_camera_concentrated":
        false_positive_score += 3
    if top_ratio >= 75:
        false_positive_score += 1
    if avg_confidence < 0.55:
        false_positive_score += 2
    if low_conf_ratio >= 50:
        false_positive_score += 2
    if health.get("status") == "abnormal":
        false_positive_score += 2
    if quality.get("status") == "abnormal":
        false_positive_score += 2
    if edge_ratio >= 70:
        false_positive_score += 1

    if concentration.get("status") == "multi_camera_distributed":
        quality_score += 3
    if affected_cameras >= 3:
        quality_score += 1
    if affected_billets >= 3:
        quality_score += 1
    if avg_confidence >= 0.75:
        quality_score += 2
    if health.get("status") == "normal":
        quality_score += 1
    if quality.get("status") == "normal":
        quality_score += 1

    if false_positive_score >= 7 and false_positive_score > quality_score:
        false_positive_risk = "high"
        root_cause = "camera_imaging_abnormal"
        conclusion = (
            f"更可能是 {target_camera}/camera2 成像或采集状态异常导致的误检风险升高，"
            "暂不应直接判定为真实质量事故。"
        )
        status = "diagnosed"
        candidates = [
            {
                "name": f"{target_camera} 成像异常/误检风险",
                "likelihood": "high",
                "evidence": [
                    f"单相机占比 {top_ratio}%",
                    f"低置信度占比 {low_conf_ratio}%",
                    "相机状态或图像质量异常",
                ],
            },
            {
                "name": "真实局部质量波动",
                "likelihood": "medium",
                "evidence": ["存在裂纹突增，但缺陷未在多相机同步出现"],
            },
            {
                "name": "整批材料质量事故",
                "likelihood": "low",
                "evidence": ["缺少多相机、多位置、多方坯同步异常证据"],
            },
        ]
        actions = [
            f"抽查 {analysis_start} 至 {target_end} 的 {target_camera} 原图和 bbox",
            f"检查 {target_camera} 光源、曝光、镜头污染、采集 FPS 和网络状态",
            "将该时间段裂纹结果标记为需人工复核",
            "暂不建议直接判废或按批量质量事故处理",
        ]
        missing_data = ["人工复核结果", "同炉号后续方坯趋势", "工艺拉速、冷却和温度记录"]
    elif quality_score >= 6 and false_positive_score <= 4:
        false_positive_risk = "low"
        root_cause = "quality_wave"
        conclusion = "更可能存在真实质量波动，需要升级批次复核，并关联炉号和工艺记录进一步确认。"
        status = "diagnosed"
        candidates = [
            {
                "name": "真实质量波动",
                "likelihood": "high",
                "evidence": [
                    f"涉及 {affected_cameras} 台相机",
                    f"涉及 {affected_billets} 支方坯",
                    "图像质量和相机状态基本正常",
                ],
            },
            {
                "name": "检测系统异常/误检",
                "likelihood": "low",
                "evidence": ["缺陷未集中在单相机，且低置信度与成像异常证据不足"],
            },
        ]
        actions = [
            "按炉号/计划号建立批次质量关注项",
            "优先抽查多相机高置信度裂纹原图",
            "关联拉速、冷却、温度和人工复检结果",
            "不建议自动判废，应由质检和工艺人员确认处置",
        ]
        missing_data = ["工艺拉速和冷却记录", "同炉号上下游方坯复检结果", "人工复核结论"]
    else:
        false_positive_risk = "medium"
        root_cause = "ambiguous"
        conclusion = "当前证据提示异常存在，但无法在真实质量波动和检测系统异常之间做强结论。"
        status = "diagnosed_with_uncertainty"
        candidates = [
            {
                "name": "检测系统异常/误检",
                "likelihood": "medium",
                "evidence": ["存在部分成像或集中度风险"],
            },
            {
                "name": "真实质量波动",
                "likelihood": "medium",
                "evidence": ["存在裂纹突增，但证据链不完整"],
            },
        ]
        actions = ["先抽查原图并复核高风险样本", "补充相机状态和工艺记录后再做根因判断"]
        missing_data = ["人工复核结果", "更多相机/图像质量样本", "工艺上下文"]

    evidence = [
        spike["summary"],
        concentration["summary"],
        f"{target_camera} 边部/边缘区域占比 {edge_ratio}%，低置信度占比 {low_conf_ratio}%",
        health["summary"],
        quality["summary"],
        "不能只根据缺陷数量或空间集中直接判定质量事故/工艺事故",
    ]
    return {
        "status": status,
        "diagnosis_intent": "defect_spike_root_cause",
        "summary": conclusion,
        "conclusion": conclusion,
        "false_positive_risk": false_positive_risk,
        "root_cause": root_cause,
        "root_cause_candidates": candidates,
        "recommended_actions": actions,
        "missing_data": missing_data,
        "evidence": evidence,
        "key_metrics": {
            "scenario_id": scenario_id,
            "defect_type": defect_type,
            "target_camera": target_camera,
            "target_count": target_count,
            "affected_cameras": affected_cameras,
            "affected_billets": affected_billets,
            "top_camera_ratio_pct": top_ratio,
            "top_camera_avg_confidence": avg_confidence,
            "top_camera_low_confidence_ratio_pct": low_conf_ratio,
            "top_camera_edge_ratio_pct": edge_ratio,
            "camera_status": health.get("status"),
            "image_quality_status": quality.get("status"),
            "false_positive_score": false_positive_score,
            "quality_score": quality_score,
            "spike": spike_metrics,
            "camera_health": health_metrics,
            "image_quality": quality_metrics,
        },
        "warnings": [],
    }
