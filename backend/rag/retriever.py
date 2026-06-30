from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

KB_PATH = Path(__file__).resolve().parent / "knowledge_base.md"
INDEX_DIR = Path(os.getenv("RAG_INDEX_DIR", Path(__file__).resolve().parent / "faiss_index"))
INDEX_PATH = INDEX_DIR / "knowledge.index"
METADATA_PATH = INDEX_DIR / "knowledge_meta.json"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"

DOMAIN_TERMS = [
    "裂纹",
    "开裂",
    "裂缝",
    "划伤",
    "结疤",
    "氧化皮",
    "凹坑",
    "夹渣",
    "麻点",
    "压痕",
    "缺陷",
    "等级",
    "严重",
    "危险",
    "critical",
    "major",
    "minor",
    "标准",
    "判定",
    "规则",
    "原因",
    "建议",
    "报告",
    "模板",
    "复核",
    "人工确认",
    "误检",
    "看错",
    "头部",
    "中部",
    "尾部",
    "边部",
    "中心",
    "表面",
    "炉号",
    "计划号",
    "方坯",
    "NG",
]

DEFECT_TYPE_ALIASES = {
    "裂纹": ["裂纹", "裂缝", "开裂"],
    "划伤": ["划伤", "刮伤", "擦伤"],
    "结疤": ["结疤", "疤痕", "结疤缺陷"],
    "氧化皮": ["氧化皮", "氧化", "氧化铁皮"],
    "凹坑": ["凹坑", "坑", "点坑"],
    "夹渣": ["夹渣", "渣", "夹杂"],
    "麻点": ["麻点", "麻面", "点状"],
    "压痕": ["压痕", "压印", "压伤"],
}

INTENT_KEYWORDS = {
    "explain": ["说明", "解释", "是什么", "为什么", "重点关注", "关注", "怎么理解"],
    "root_cause": ["原因", "为什么", "导致", "可能", "有关", "排查", "检查", "工艺问题"],
    "uncertain_cause": ["一定", "必然", "确认", "导致的吗", "是不是", "能否判定", "能不能判定"],
    "severity": ["等级", "严重", "危险", "critical", "major", "minor", "高风险"],
    "standard": ["标准", "判定", "规则", "依据"],
    "review": ["复核", "闭环", "人工", "确认", "优先", "人工确认", "要不要处理"],
    "false_positive": ["误检", "阈值", "反光", "照明", "看错", "系统看错"],
    "spatial": ["集中", "位置", "头部", "中部", "尾部", "边部", "中心", "空间", "分布"],
    "report": ["报告", "模板", "怎么写", "写进报告"],
    "answer_style": ["回答规范", "注意什么", "不要", "凭空", "审慎"],
    "quality": ["质量", "异常", "炉号", "计划号", "方坯", "NG"],
}

INTENT_CATEGORY_BOOSTS = {
    "explain": {"defect_type"},
    "root_cause": {"root_cause", "defect_type", "review", "answer_rule"},
    "uncertain_cause": {"answer_rule", "root_cause", "review", "defect_type"},
    "severity": {"severity", "review", "answer_rule", "root_cause"},
    "standard": {"standard", "severity", "spatial_rule", "answer_rule"},
    "review": {"review", "root_cause", "answer_rule", "severity"},
    "false_positive": {"defect_type", "review", "answer_rule"},
    "spatial": {"spatial_rule", "standard", "root_cause"},
    "report": {"report_template", "standard", "spatial_rule", "answer_rule"},
    "answer_style": {"answer_rule", "root_cause", "review"},
    "quality": {"standard", "review", "root_cause", "report_template"},
}

INTENT_REWRITE_PHRASES = {
    "explain": ["缺陷说明", "知识解释"],
    "root_cause": ["常见缺陷原因排查清单", "工艺记录", "检测证据"],
    "uncertain_cause": ["因果不确定性", "谨慎表述", "不能直接确认"],
    "severity": ["缺陷等级规则", "critical", "major", "minor", "高风险"],
    "standard": ["方坯表面缺陷判定标准", "规则", "依据"],
    "review": ["缺陷复核闭环建议", "人工复核", "质量风险"],
    "false_positive": ["视觉误检", "检测阈值", "照明反光", "人工复核"],
    "spatial": ["方坯空间分布解释规则", "头部", "边部", "集中"],
    "report": ["缺陷分析报告模板", "报告内容"],
    "answer_style": ["缺陷知识解释回答规范", "审慎表述", "证据约束"],
    "quality": ["质量关注项", "炉号", "计划号", "方坯ID"],
}

REQUIRED_EVIDENCE_BY_INTENT = {
    "root_cause": {"root_cause_checklist"},
    "uncertain_cause": {"root_cause_checklist", "answer_rule", "review_loop"},
    "severity": {"severity_rule"},
    "standard": {"surface_standard"},
    "review": {"review_loop"},
    "false_positive": {"defect_explanation", "answer_rule", "review_loop"},
    "spatial": {"spatial_rule"},
    "report": {"report_template"},
    "answer_style": {"answer_rule"},
    "quality": {"surface_standard", "review_loop"},
}

EVIDENCE_TYPE_FOLLOWUP_QUERIES = {
    "defect_explanation": "缺陷说明 高风险 可能原因",
    "root_cause_checklist": "常见缺陷原因排查清单 工艺记录 复核",
    "answer_rule": "缺陷知识解释回答规范 因果不确定性 谨慎表述",
    "review_loop": "缺陷复核闭环建议 人工复核 质量风险",
    "severity_rule": "缺陷等级规则 critical major minor 优先级",
    "surface_standard": "方坯表面缺陷判定标准 可追溯数据",
    "spatial_rule": "方坯空间分布解释规则 头部 边部 集中",
    "report_template": "缺陷分析报告模板 报告内容",
}

MISSING_ASPECT_LABELS = {
    "defect_explanation": "缺少缺陷类型说明",
    "root_cause_checklist": "缺少原因排查清单",
    "answer_rule": "缺少审慎回答规范",
    "review_loop": "缺少复核闭环建议",
    "severity_rule": "缺少缺陷等级规则",
    "surface_standard": "缺少方坯表面判定标准",
    "spatial_rule": "缺少空间分布解释规则",
    "report_template": "缺少报告模板知识",
}

DEFAULT_EVIDENCE_BUDGET_CHARS = 1800
DEFAULT_EVIDENCE_BUDGET_MAX_ITEMS = 3
MAX_AGENTIC_RAG_ROUNDS = 2

_MODEL_CACHE: Dict[str, Any] = {}


def _embedding_model_name(model_name: Optional[str] = None) -> str:
    return model_name or os.getenv("EMBEDDING_MODEL_NAME", DEFAULT_EMBEDDING_MODEL)


def _load_chunks(kb_path: Path = KB_PATH) -> List[Dict[str, Any]]:
    raw = kb_path.read_text(encoding="utf-8")
    sections: List[str] = []
    current: List[str] = []

    for line in raw.splitlines():
        if line.startswith("id: ") and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())

    chunks: List[Dict[str, Any]] = []
    for section in sections:
        if "\n---\n" not in section:
            continue
        metadata_block, body = section.split("\n---\n", 1)
        meta: Dict[str, str] = {}
        for line in metadata_block.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()
        doc_id = meta.get("id", "").strip()
        content = body.strip()
        if doc_id and content:
            chunk = {
                "doc_id": doc_id,
                "title": meta.get("title", "").strip(),
                "category": meta.get("category", "").strip(),
                "tags": meta.get("tags", "").strip(),
                "content": content,
                "source": kb_path.name,
            }
            for key, value in meta.items():
                if key != "id" and key not in chunk:
                    chunk[key] = value.strip()
            chunks.append(chunk)
    return chunks


def _chunk_text(chunk: Dict[str, Any]) -> str:
    return "\n".join(
        [
            f"标题：{chunk.get('title', '')}",
            f"类别：{chunk.get('category', '')}",
            f"标签：{chunk.get('tags', '')}",
            f"缺陷类型：{chunk.get('defect_types', '')}",
            f"适用意图：{chunk.get('applicable_intents', '')}",
            f"证据类型：{chunk.get('evidence_type', '')}",
            f"风险等级：{chunk.get('risk_level', '')}",
            f"内容：{chunk.get('content', '')}",
        ]
    )


def _fingerprint(chunks: List[Dict[str, Any]], model_name: str) -> str:
    payload = {"model_name": model_name, "chunks": chunks}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _vector_stack_available() -> bool:
    return (
        importlib.util.find_spec("faiss") is not None
        and importlib.util.find_spec("numpy") is not None
        and importlib.util.find_spec("sentence_transformers") is not None
    )


def _get_model(model_name: str) -> Any:
    if model_name in _MODEL_CACHE:
        return _MODEL_CACHE[model_name]

    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # pragma: no cover - optional dependency.
        raise RuntimeError(f"sentence_transformers_unavailable:{exc}") from exc

    errors: List[str] = []
    for local_files_only in (True, False):
        try:
            model = SentenceTransformer(model_name, local_files_only=local_files_only)
            _MODEL_CACHE[model_name] = model
            return model
        except Exception as exc:  # pragma: no cover - depends on local model cache/network.
            mode = "local_cache" if local_files_only else "online"
            errors.append(f"{mode}:{exc}")

    raise RuntimeError("embedding_model_load_failed:" + " | ".join(errors))


def _load_faiss_index(chunks: List[Dict[str, Any]], model_name: str) -> Optional[Tuple[Any, List[Dict[str, Any]]]]:
    if not INDEX_PATH.exists() or not METADATA_PATH.exists():
        return None

    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    if metadata.get("fingerprint") != _fingerprint(chunks, model_name):
        return None

    return _read_faiss_index(INDEX_PATH), metadata.get("chunks", [])


def _write_faiss_index(index: Any, path: Path) -> None:
    """Persist FAISS index through Python IO so Windows Unicode paths work reliably."""
    import faiss  # type: ignore
    import numpy as np  # type: ignore

    serialized = faiss.serialize_index(index)
    data = serialized if isinstance(serialized, bytes) else np.asarray(serialized, dtype="uint8").tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _read_faiss_index(path: Path) -> Any:
    """Load FAISS index through Python IO so Windows Unicode paths work reliably."""
    import faiss  # type: ignore
    import numpy as np  # type: ignore

    data = np.frombuffer(path.read_bytes(), dtype="uint8")
    return faiss.deserialize_index(data)


def build_faiss_index(force_rebuild: bool = False, model_name: Optional[str] = None) -> Dict[str, Any]:
    """Build a local FAISS index over the Markdown knowledge base using a BGE embedding model."""
    model_name = _embedding_model_name(model_name)
    chunks = _load_chunks()
    if not chunks:
        raise RuntimeError("knowledge_base_empty")
    if not _vector_stack_available():
        raise RuntimeError("faiss_bge_dependencies_unavailable")

    if not force_rebuild:
        existing = _load_faiss_index(chunks, model_name)
        if existing is not None:
            return {
                "ok": True,
                "rebuilt": False,
                "chunk_count": len(chunks),
                "embedding_model": model_name,
                "index_path": str(INDEX_PATH),
            }

    import faiss  # type: ignore
    import numpy as np  # type: ignore

    model = _get_model(model_name)
    texts = [_chunk_text(chunk) for chunk in chunks]
    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    vectors = np.asarray(embeddings, dtype="float32")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    _write_faiss_index(index, INDEX_PATH)
    METADATA_PATH.write_text(
        json.dumps(
            {
                "fingerprint": _fingerprint(chunks, model_name),
                "embedding_model": model_name,
                "chunks": chunks,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "rebuilt": True,
        "chunk_count": len(chunks),
        "embedding_model": model_name,
        "index_path": str(INDEX_PATH),
    }


def _with_rank(
    chunk: Dict[str, Any],
    rank: int,
    score: float,
    retriever: str,
    model_name: Optional[str] = None,
    vector_error: Optional[str] = None,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        **chunk,
        "rank": rank,
        "raw_rank": rank,
        "score": round(float(score), 4),
        "retriever": retriever,
        "metadata_score": 0.0,
        "rerank_score": round(float(score), 4),
        "rerank_reason": [],
    }
    if retriever == "faiss_bge":
        item["dense_rank"] = rank
        item["dense_score"] = round(float(score), 4)
    if retriever == "keyword_fallback":
        item["keyword_rank"] = rank
        item["keyword_score"] = round(float(score), 4)
    if model_name:
        item["embedding_model"] = model_name
    if vector_error:
        item["vector_error"] = vector_error
    return item


def _split_tags(raw_tags: Any) -> List[str]:
    if isinstance(raw_tags, list):
        return [str(tag).strip() for tag in raw_tags if str(tag).strip()]
    return [tag.strip() for tag in re.split(r"[,，;；\s]+", str(raw_tags or "")) if tag.strip()]


def _contains_any(text: str, keywords: List[str]) -> bool:
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in keywords)


def analyze_rag_query(query: str) -> Dict[str, Any]:
    """Extract deterministic retrieval hints for business reranking."""
    defect_types: List[str] = []
    for defect_type, aliases in DEFECT_TYPE_ALIASES.items():
        if _contains_any(query, aliases):
            defect_types.append(defect_type)

    intents: List[str] = []
    for intent, keywords in INTENT_KEYWORDS.items():
        if _contains_any(query, keywords):
            intents.append(intent)
    if not intents and defect_types:
        intents.append("explain")

    target_categories: List[str] = []
    for intent in intents:
        for category in INTENT_CATEGORY_BOOSTS.get(intent, set()):
            if category not in target_categories:
                target_categories.append(category)
    if not defect_types:
        target_categories = [category for category in target_categories if category != "defect_type"]

    return {
        "raw_query": query,
        "defect_types": defect_types,
        "intents": intents,
        "target_categories": target_categories,
    }


def _dedupe_keep_order(values: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def rewrite_rag_query(query: str, query_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Rewrite colloquial defect questions into retrieval-friendly domain terms."""
    query_profile = query_profile or analyze_rag_query(query)
    defect_terms = query_profile.get("defect_types", [])
    intents = query_profile.get("intents", [])
    rewritten_terms: List[str] = []

    rewritten_terms.extend(defect_terms)
    for intent in intents:
        rewritten_terms.extend(INTENT_REWRITE_PHRASES.get(intent, []))
    if not rewritten_terms:
        rewritten_terms.append(query)

    rewritten_query = " ".join(_dedupe_keep_order(rewritten_terms))
    rewrite_success = bool(rewritten_query and rewritten_query != query.strip())
    return {
        "original_query": query,
        "rewritten_query": rewritten_query,
        "rewrite_success": rewrite_success,
        "defect_types": defect_terms,
        "intents": intents,
        "target_categories": query_profile.get("target_categories", []),
    }


def _required_evidence_types(query_profile: Dict[str, Any]) -> List[str]:
    required: List[str] = []
    defect_types = query_profile.get("defect_types", [])
    intents = query_profile.get("intents", [])
    raw_query = str(query_profile.get("raw_query", ""))

    if defect_types:
        required.append("defect_explanation")
    for intent in intents:
        required.extend(REQUIRED_EVIDENCE_BY_INTENT.get(intent, set()))
    if not required and intents:
        required.append("answer_rule")
    if "surface_standard" in required and defect_types and any(
        intent in intents for intent in ["severity", "review", "uncertain_cause"]
    ):
        surface_standard_explicit = any(
            token in raw_query
            for token in ["方坯表面", "表面缺陷判定", "表面判定", "判定标准是什么", "质量异常判定"]
        )
        if not surface_standard_explicit:
            required = [item for item in required if item != "surface_standard"]
    return _dedupe_keep_order(required)


def _build_sub_queries(query: str, rewrite: Dict[str, Any], required_evidence_types: List[str]) -> List[Dict[str, str]]:
    sub_queries: List[Dict[str, str]] = [
        {"query": query, "purpose": "original"},
        {"query": rewrite["rewritten_query"], "purpose": "rewrite"},
    ]
    defect_types = rewrite.get("defect_types", [])
    intents = rewrite.get("intents", [])

    for defect_type in defect_types:
        parts = [defect_type, "缺陷说明"]
        if "severity" in intents:
            parts.extend(["critical", "高风险", "缺陷等级规则"])
        if "root_cause" in intents or "uncertain_cause" in intents:
            parts.extend(["原因排查", "工艺记录"])
        if "review" in intents or "uncertain_cause" in intents:
            parts.extend(["人工复核", "质量风险"])
        if "spatial" in intents:
            parts.extend(["空间分布", "头部", "边部"])
        if "false_positive" in intents:
            parts.extend(["视觉误检", "阈值", "照明"])
        sub_queries.append({"query": " ".join(_dedupe_keep_order(parts)), "purpose": "defect_focus"})

    for evidence_type in required_evidence_types:
        followup = EVIDENCE_TYPE_FOLLOWUP_QUERIES.get(evidence_type)
        if followup:
            defect_prefix = " ".join(defect_types)
            sub_queries.append(
                {
                    "query": f"{defect_prefix} {followup}".strip(),
                    "purpose": f"required:{evidence_type}",
                }
            )

    unique: List[Dict[str, str]] = []
    seen = set()
    for item in sub_queries:
        q = item["query"].strip()
        if q and q not in seen:
            seen.add(q)
            unique.append({"query": q, "purpose": item["purpose"]})
    return unique[:8]


def _merge_retrieval_candidates(rounds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for retrieval_round in rounds:
        for query_result in retrieval_round.get("query_results", []):
            query_text = query_result.get("query", "")
            purpose = query_result.get("purpose", "")
            for item in query_result.get("items", []):
                doc_id = str(item.get("doc_id") or "")
                if not doc_id:
                    continue
                current = merged.get(doc_id)
                item_score = float(item.get("rerank_score", item.get("score", 0.0)) or 0.0)
                if current is None or item_score > float(current.get("rerank_score", current.get("score", 0.0)) or 0.0):
                    current = dict(item)
                    current["matched_queries"] = []
                    merged[doc_id] = current
                current.setdefault("matched_queries", []).append({"query": query_text, "purpose": purpose})
    return list(merged.values())


def judge_evidence_sufficiency(items: List[Dict[str, Any]], required_evidence_types: List[str]) -> Dict[str, Any]:
    selected_items = items
    context_items = [item for item in items if item.get("included_in_answer_context", True)] or items[:1]
    covered = _dedupe_keep_order([str(item.get("evidence_type")) for item in selected_items if item.get("evidence_type")])
    context_covered = _dedupe_keep_order(
        [str(item.get("evidence_type")) for item in context_items if item.get("evidence_type")]
    )
    missing = [evidence_type for evidence_type in required_evidence_types if evidence_type not in covered]
    context_missing = [
        evidence_type for evidence_type in required_evidence_types if evidence_type not in context_covered
    ]
    coverage_rate = 1.0 if not required_evidence_types else (
        (len(required_evidence_types) - len(missing)) / len(required_evidence_types)
    )
    context_coverage_rate = 1.0 if not required_evidence_types else (
        (len(required_evidence_types) - len(context_missing)) / len(required_evidence_types)
    )
    return {
        "evidence_sufficient": not missing,
        "context_evidence_sufficient": not context_missing,
        "required_evidence_types": required_evidence_types,
        "covered_evidence_types": covered,
        "covered_context_evidence_types": context_covered,
        "missing_evidence_types": missing,
        "context_missing_evidence_types": context_missing,
        "missing_aspects": [MISSING_ASPECT_LABELS.get(item, item) for item in missing],
        "context_missing_aspects": [MISSING_ASPECT_LABELS.get(item, item) for item in context_missing],
        "coverage_rate": round(float(coverage_rate), 4),
        "context_coverage_rate": round(float(context_coverage_rate), 4),
    }


def _build_followup_queries(missing_evidence_types: List[str], defect_types: List[str]) -> List[Dict[str, str]]:
    followups: List[Dict[str, str]] = []
    prefix = " ".join(defect_types)
    for evidence_type in missing_evidence_types:
        query = EVIDENCE_TYPE_FOLLOWUP_QUERIES.get(evidence_type)
        if query:
            followups.append(
                {
                    "query": f"{prefix} {query}".strip(),
                    "purpose": f"second_round:{evidence_type}",
                }
            )
    return followups[:4]


def _compact_retrieval_rounds(retrieval_rounds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    compact_rounds: List[Dict[str, Any]] = []
    for retrieval_round in retrieval_rounds:
        compact_results: List[Dict[str, Any]] = []
        for query_result in retrieval_round.get("query_results", []):
            compact_results.append(
                {
                    "query": query_result.get("query"),
                    "purpose": query_result.get("purpose"),
                    "doc_ids": query_result.get("doc_ids", []),
                    "top_doc_id": query_result.get("top_doc_id"),
                    "items": [
                        {
                            "rank": item.get("rank"),
                            "doc_id": item.get("doc_id"),
                            "title": item.get("title"),
                            "evidence_type": item.get("evidence_type"),
                            "score": item.get("score"),
                            "dense_score": item.get("dense_score"),
                            "metadata_score": item.get("metadata_score"),
                            "rerank_score": item.get("rerank_score"),
                        }
                        for item in query_result.get("items", [])
                    ],
                }
            )
        compact_rounds.append(
            {
                "round": retrieval_round.get("round"),
                "reason": retrieval_round.get("reason"),
                "queries": retrieval_round.get("queries", []),
                "query_results": compact_results,
                "doc_ids": retrieval_round.get("doc_ids", []),
            }
        )
    return compact_rounds


def build_agentic_rag_trace(
    query: str,
    top_k: int,
    items: List[Dict[str, Any]],
    rewrite: Dict[str, Any],
    sub_queries: List[Dict[str, str]],
    retrieval_rounds: List[Dict[str, Any]],
    evidence_judge: Dict[str, Any],
    second_round_queries: List[Dict[str, str]],
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    trace = build_rag_trace(query=query, top_k=top_k, items=items, warnings=warnings)
    trace.update(
        {
            "rewritten_query": rewrite.get("rewritten_query"),
            "rewrite_success": rewrite.get("rewrite_success", False),
            "sub_queries": sub_queries,
            "retrieval_rounds": _compact_retrieval_rounds(retrieval_rounds),
            "evidence_sufficient": evidence_judge.get("evidence_sufficient", False),
            "context_evidence_sufficient": evidence_judge.get("context_evidence_sufficient", False),
            "required_evidence_types": evidence_judge.get("required_evidence_types", []),
            "covered_evidence_types": evidence_judge.get("covered_evidence_types", []),
            "covered_context_evidence_types": evidence_judge.get("covered_context_evidence_types", []),
            "missing_aspects": evidence_judge.get("missing_aspects", []),
            "context_missing_aspects": evidence_judge.get("context_missing_aspects", []),
            "coverage_rate": evidence_judge.get("coverage_rate", 0.0),
            "context_coverage_rate": evidence_judge.get("context_coverage_rate", 0.0),
            "second_round_queries": second_round_queries,
            "second_round_used": bool(second_round_queries),
        }
    )
    return trace


def _chunk_metadata_values(chunk: Dict[str, Any], key: str) -> List[str]:
    return _split_tags(chunk.get(key, ""))


def _metadata_match_score(query_profile: Dict[str, Any], chunk: Dict[str, Any]) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []
    query_defects = query_profile.get("defect_types", [])
    query_intents = query_profile.get("intents", [])
    raw_query = str(query_profile.get("raw_query", ""))
    target_categories = set(query_profile.get("target_categories", []))
    chunk_defects = _chunk_metadata_values(chunk, "defect_types")
    chunk_intents = _chunk_metadata_values(chunk, "applicable_intents")
    chunk_related = _chunk_metadata_values(chunk, "related_doc_ids")
    category = str(chunk.get("category") or "")
    doc_id = str(chunk.get("doc_id") or "")
    tags = set(_split_tags(chunk.get("tags", "")))

    if query_defects:
        if any(defect in chunk_defects for defect in query_defects):
            if category == "defect_type" or len(chunk_defects) == 1:
                score += 0.38
                reasons.append("缺陷类型匹配")
            else:
                score += 0.12
                reasons.append("通用规则覆盖该缺陷类型")
        elif "all" in chunk_defects:
            score += 0.08
            reasons.append("通用缺陷知识")
        elif category == "defect_type":
            score -= 0.55
            reasons.append("缺陷类型不匹配")

    if category in target_categories:
        score += 0.22
        reasons.append("知识类别匹配")

    broad_rule_intents = {"severity", "standard", "review", "answer_style", "report", "root_cause"}
    if not query_defects and category == "defect_type" and any(intent in query_intents for intent in broad_rule_intents):
        score -= 0.28
        reasons.append("未指定缺陷类型，降低单缺陷说明优先级")

    matched_intents = [intent for intent in query_intents if intent in chunk_intents]
    if matched_intents:
        intent_score = min(0.24, 0.08 * len(matched_intents))
        score += intent_score
        reasons.append("问题意图匹配:" + ",".join(matched_intents[:3]))

    if query_defects and any(defect in tags for defect in query_defects):
        score += 0.08
        reasons.append("标签命中缺陷类型")

    if query_defects and any(related.startswith("defect_type_") for related in chunk_related):
        score += 0.04
        reasons.append("关联缺陷知识")

    if "uncertain_cause" in query_intents and chunk.get("evidence_type") in {"answer_rule", "root_cause_checklist"}:
        score += 0.18
        reasons.append("因果不确定性防护")

    if "root_cause" in query_intents and chunk.get("evidence_type") == "root_cause_checklist":
        score += 0.18
        reasons.append("原因排查清单优先")

    if chunk.get("evidence_type") == "root_cause_checklist" and any(
        token in raw_query for token in ["原因排查清单", "原因排查", "排查清单"]
    ):
        score += 0.12
        reasons.append("显式命中原因排查清单")

    if "review" in query_intents and chunk.get("evidence_type") == "review_loop":
        score += 0.16
        reasons.append("复核闭环优先")

    if chunk.get("evidence_type") == "review_loop" and any(
        token in raw_query for token in ["人工确认", "人工复核", "优先人工", "复核闭环"]
    ):
        score += 0.08
        reasons.append("显式命中复核闭环")

    if "severity" in query_intents and chunk.get("evidence_type") == "severity_rule":
        score += 0.18
        reasons.append("等级规则优先")

    if "report" in query_intents and chunk.get("evidence_type") == "report_template":
        score += 0.18
        reasons.append("报告模板优先")

    if "spatial" in query_intents and chunk.get("evidence_type") == "spatial_rule":
        score += 0.16
        reasons.append("空间解释优先")

    if chunk.get("evidence_type") == "spatial_rule" and any(
        token in raw_query for token in ["空间分布", "头部", "边部", "集中"]
    ):
        score += 0.12
        reasons.append("显式命中空间分布规则")

    if chunk.get("evidence_type") == "answer_rule" and any(
        token in raw_query for token in ["回答规范", "注意什么", "谨慎表述", "不能直接", "不要"]
    ):
        score += 0.16
        reasons.append("显式命中回答规范")

    if doc_id in {"response_style_rule", "review_loop_standard"} and "root_cause" in query_intents:
        score += 0.04
        reasons.append("原因回答审慎约束")

    return round(score, 4), reasons


def _evidence_budget_chars() -> int:
    raw_value = os.getenv("RAG_EVIDENCE_BUDGET_CHARS")
    try:
        value = int(raw_value) if raw_value else DEFAULT_EVIDENCE_BUDGET_CHARS
    except ValueError:
        value = DEFAULT_EVIDENCE_BUDGET_CHARS
    return max(400, min(value, 8000))


def _evidence_budget_max_items() -> int:
    raw_value = os.getenv("RAG_EVIDENCE_BUDGET_MAX_ITEMS")
    try:
        value = int(raw_value) if raw_value else DEFAULT_EVIDENCE_BUDGET_MAX_ITEMS
    except ValueError:
        value = DEFAULT_EVIDENCE_BUDGET_MAX_ITEMS
    return max(1, min(value, 10))


def _apply_evidence_budget(
    items: List[Dict[str, Any]],
    max_chars: Optional[int] = None,
    required_evidence_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    max_chars = max_chars or _evidence_budget_chars()
    max_items = _evidence_budget_max_items()
    used_chars = 0
    output: List[Dict[str, Any]] = []
    required = set(required_evidence_types or [])
    for final_rank, item in enumerate(items, start=1):
        updated = dict(item)
        content_chars = len(str(updated.get("title", ""))) + len(str(updated.get("content", "")))
        must_keep_first = final_rank == 1
        include = must_keep_first or (final_rank <= max_items and used_chars + content_chars <= max_chars)
        if include:
            used_chars += content_chars
            budget_reason = "included"
        elif final_rank > max_items:
            budget_reason = "over_item_budget"
        else:
            budget_reason = "over_budget"
        updated["rank"] = final_rank
        updated["final_rank"] = final_rank
        updated["included_in_answer_context"] = include
        updated["evidence_budget"] = {
            "max_chars": max_chars,
            "max_items": max_items,
            "content_chars": content_chars,
            "used_chars": used_chars,
            "reason": budget_reason,
        }
        output.append(updated)
    if required:
        included_types = {
            str(item.get("evidence_type"))
            for item in output
            if item.get("included_in_answer_context", True) and item.get("evidence_type")
        }
        for item in output:
            evidence_type = str(item.get("evidence_type") or "")
            if (
                not evidence_type
                or evidence_type not in required
                or evidence_type in included_types
                or item.get("included_in_answer_context", True)
            ):
                continue

            content_chars = int(item.get("evidence_budget", {}).get("content_chars", 0) or 0)
            if used_chars + content_chars <= max_chars:
                item["included_in_answer_context"] = True
                item["evidence_budget"]["reason"] = "required_evidence"
                used_chars += content_chars
                included_types.add(evidence_type)
                continue

            replacement = _find_budget_replacement(output, required, keep_rank=1)
            if replacement is None:
                continue
            replacement_chars = int(replacement.get("evidence_budget", {}).get("content_chars", 0) or 0)
            if used_chars - replacement_chars + content_chars > max_chars:
                continue
            replacement["included_in_answer_context"] = False
            replacement["evidence_budget"]["reason"] = "replaced_by_required_evidence"
            item["included_in_answer_context"] = True
            item["evidence_budget"]["reason"] = "required_evidence"
            used_chars = used_chars - replacement_chars + content_chars
            included_types.add(evidence_type)

    for item in output:
        item["evidence_budget"]["used_chars"] = used_chars
    return output


def _find_budget_replacement(
    items: List[Dict[str, Any]],
    required_evidence_types: set[str],
    keep_rank: int = 1,
) -> Optional[Dict[str, Any]]:
    included_type_counts: Dict[str, int] = {}
    for item in items:
        if item.get("included_in_answer_context", True) and item.get("evidence_type"):
            evidence_type = str(item.get("evidence_type"))
            included_type_counts[evidence_type] = included_type_counts.get(evidence_type, 0) + 1

    for item in reversed(items):
        if not item.get("included_in_answer_context", True) or item.get("rank") == keep_rank:
            continue
        evidence_type = str(item.get("evidence_type") or "")
        if evidence_type not in required_evidence_types or included_type_counts.get(evidence_type, 0) > 1:
            return item
    return None


def _rerank_results(
    query: str,
    candidates: List[Dict[str, Any]],
    top_k: int,
    query_profile: Optional[Dict[str, Any]] = None,
    required_evidence_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    query_profile = query_profile or analyze_rag_query(query)
    ranked: List[Dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        base_score = float(item.get("dense_score", item.get("keyword_score", item.get("score", 0.0))) or 0.0)
        metadata_score, reasons = _metadata_match_score(query_profile, item)
        rerank_score = base_score + metadata_score
        item["query_profile"] = query_profile
        item["metadata_score"] = round(metadata_score, 4)
        item["rerank_score"] = round(rerank_score, 4)
        item["score"] = round(rerank_score, 4)
        item["rerank_reason"] = reasons or ["向量相似度排序"]
        ranked.append(item)

    ranked.sort(
        key=lambda item: (
            float(item.get("rerank_score", 0.0)),
            float(item.get("dense_score", item.get("keyword_score", 0.0))),
        ),
        reverse=True,
    )
    return _apply_evidence_budget(ranked[:top_k], required_evidence_types=required_evidence_types)


def build_rag_trace(
    query: str,
    top_k: int,
    items: List[Dict[str, Any]],
    need_rag: Optional[bool] = None,
    tool_name: str = "retrieve_defect_knowledge",
    answer_mode: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a compact retrieval trace for recall, rerank, and evidence-budget debugging."""
    doc_ids = [str(item.get("doc_id", "")) for item in items if item.get("doc_id")]
    trace_hash = hashlib.sha1(f"{query}|{top_k}|{','.join(doc_ids)}".encode("utf-8")).hexdigest()[:8]
    trace_id = f"rag_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{trace_hash}"
    query_profile = analyze_rag_query(query)

    candidates: List[Dict[str, Any]] = []
    categories: List[str] = []
    tags: List[str] = []
    sources: List[str] = []
    scores: Dict[str, float] = {}
    trace_warnings = list(warnings or [])

    for item in items:
        item_tags = _split_tags(item.get("tags", ""))
        doc_id = item.get("doc_id")
        score = item.get("score")
        candidate = {
            "rank": item.get("rank"),
            "raw_rank": item.get("raw_rank"),
            "dense_rank": item.get("dense_rank"),
            "doc_id": doc_id,
            "title": item.get("title"),
            "score": score,
            "dense_score": item.get("dense_score"),
            "keyword_score": item.get("keyword_score"),
            "metadata_score": item.get("metadata_score"),
            "rerank_score": item.get("rerank_score"),
            "rerank_reason": item.get("rerank_reason", []),
            "included_in_answer_context": item.get("included_in_answer_context", True),
            "evidence_budget": item.get("evidence_budget", {}),
            "retriever": item.get("retriever"),
            "embedding_model": item.get("embedding_model"),
            "category": item.get("category"),
            "tags": item_tags,
            "defect_types": _chunk_metadata_values(item, "defect_types"),
            "applicable_intents": _chunk_metadata_values(item, "applicable_intents"),
            "evidence_type": item.get("evidence_type"),
            "risk_level": item.get("risk_level"),
            "source": item.get("source"),
        }
        candidates.append(candidate)

        if doc_id and isinstance(score, (int, float)):
            scores[str(doc_id)] = round(float(score), 4)
        if item.get("category") and item.get("category") not in categories:
            categories.append(str(item.get("category")))
        for tag in item_tags:
            if tag not in tags:
                tags.append(tag)
        if item.get("source") and item.get("source") not in sources:
            sources.append(str(item.get("source")))
        if item.get("vector_error"):
            trace_warnings.append(str(item.get("vector_error")))

    top = candidates[0] if candidates else {}
    return {
        "trace_id": trace_id,
        "original_query": query,
        "retriever": top.get("retriever") or "none",
        "embedding_model": top.get("embedding_model"),
        "top_k": top_k,
        "retrieved_candidates": candidates,
        "selected_doc_ids": doc_ids,
        "scores": scores,
        "categories": categories,
        "tags": tags,
        "source": sources[0] if len(sources) == 1 else sources,
        "query_profile": query_profile,
        "evidence_budget": {
            "max_chars": _evidence_budget_chars(),
            "max_items": _evidence_budget_max_items(),
            "included_doc_ids": [
                str(item.get("doc_id"))
                for item in items
                if item.get("doc_id") and item.get("included_in_answer_context", True)
            ],
            "omitted_doc_ids": [
                str(item.get("doc_id"))
                for item in items
                if item.get("doc_id") and not item.get("included_in_answer_context", True)
            ],
        },
        "need_rag": need_rag,
        "tool_name": tool_name,
        "answer_mode": answer_mode,
        "warnings": trace_warnings,
    }


def _retrieve_with_faiss(query: str, top_k: int, model_name: str) -> List[Dict[str, Any]]:
    if not _vector_stack_available():
        raise RuntimeError("faiss_bge_dependencies_unavailable")

    import numpy as np  # type: ignore

    chunks = _load_chunks()
    existing = _load_faiss_index(chunks, model_name)
    if existing is None:
        build_faiss_index(force_rebuild=True, model_name=model_name)
        existing = _load_faiss_index(chunks, model_name)
    if existing is None:
        raise RuntimeError("faiss_index_load_failed")

    index, indexed_chunks = existing
    model = _get_model(model_name)
    query_embedding = model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    query_vector = np.asarray(query_embedding, dtype="float32")
    scores, indices = index.search(query_vector, top_k)

    results: List[Dict[str, Any]] = []
    for rank, (score, chunk_index) in enumerate(zip(scores[0], indices[0]), start=1):
        if chunk_index < 0 or chunk_index >= len(indexed_chunks):
            continue
        results.append(
            _with_rank(
                indexed_chunks[int(chunk_index)],
                rank=rank,
                score=float(score),
                retriever="faiss_bge",
                model_name=model_name,
            )
        )
    return results


def _query_terms(query: str) -> List[str]:
    terms: List[str] = []
    for term in DOMAIN_TERMS:
        if term.lower() in query.lower():
            terms.append(term)

    for token in re.split(r"[\s,，。；;：:/\\|?？!！()（）\[\]【】\"']+", query):
        token = token.strip()
        if len(token) >= 2 and token not in terms:
            terms.append(token)

    return terms


def _keyword_score(query: str, chunk: Dict[str, Any]) -> float:
    terms = _query_terms(query)
    if not terms:
        return 0.0

    title = chunk.get("title", "").lower()
    tags = chunk.get("tags", "").lower()
    category = chunk.get("category", "").lower()
    content = chunk.get("content", "").lower()
    score = 0.0
    for term in terms:
        lower = term.lower()
        if lower in title:
            score += 5.0
        if lower in tags:
            score += 4.0
        if lower in category:
            score += 2.0
        if lower in content:
            score += 1.5

    if chunk.get("category") == "defect_type" and any(t in query for t in ["原因", "为什么", "建议", "说明", "解释"]):
        score += 0.5
    if chunk.get("category") in {"severity", "standard"} and any(t in query for t in ["等级", "规则", "标准", "判定"]):
        score += 1.0
    return score


def _retrieve_with_keywords(query: str, top_k: int, vector_error: Optional[str] = None) -> List[Dict[str, Any]]:
    chunks = _load_chunks()
    scored = [(_keyword_score(query, chunk), chunk) for chunk in chunks]
    scored = [(score, chunk) for score, chunk in scored if score > 0]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        _with_rank(chunk, rank=index, score=score, retriever="keyword_fallback", vector_error=vector_error)
        for index, (score, chunk) in enumerate(scored[:top_k], start=1)
    ]


def _candidate_pool_size(top_k: int) -> int:
    chunk_count = len(_load_chunks())
    return max(top_k, min(chunk_count, max(12, top_k * 4)))


def retrieve_knowledge(query: str, top_k: int = 3, model_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve defect-domain knowledge. FAISS+BGE is used when available; keyword fallback keeps demos offline."""
    query = (query or "").strip()
    if not query:
        return []

    top_k = max(1, min(int(top_k or 3), 10))
    model_name = _embedding_model_name(model_name)
    candidate_k = _candidate_pool_size(top_k)

    try:
        results = _retrieve_with_faiss(query, candidate_k, model_name)
        if results:
            return _rerank_results(query, results, top_k)
    except Exception as exc:
        results = _retrieve_with_keywords(query, candidate_k, vector_error=str(exc))
        return _rerank_results(query, results, top_k)

    results = _retrieve_with_keywords(query, candidate_k)
    return _rerank_results(query, results, top_k)


def retrieve_agentic_knowledge(query: str, top_k: int = 3, model_name: Optional[str] = None) -> Dict[str, Any]:
    """Plan, retrieve, judge, and optionally repair RAG evidence with deterministic Agentic RAG steps."""
    query = (query or "").strip()
    top_k = max(1, min(int(top_k or 3), 10))
    query_profile = analyze_rag_query(query)
    rewrite = rewrite_rag_query(query, query_profile)
    required_evidence_types = _required_evidence_types(query_profile)
    sub_queries = _build_sub_queries(query, rewrite, required_evidence_types)
    retrieval_rounds: List[Dict[str, Any]] = []
    warnings: List[str] = []

    def run_round(round_index: int, reason: str, queries: List[Dict[str, str]]) -> None:
        query_results: List[Dict[str, Any]] = []
        for planned_query in queries:
            items = retrieve_knowledge(planned_query["query"], top_k=top_k, model_name=model_name)
            query_results.append(
                {
                    "query": planned_query["query"],
                    "purpose": planned_query.get("purpose", ""),
                    "doc_ids": [item.get("doc_id") for item in items if item.get("doc_id")],
                    "top_doc_id": items[0].get("doc_id") if items else None,
                    "items": items,
                }
            )
        retrieval_rounds.append(
            {
                "round": round_index,
                "reason": reason,
                "queries": queries,
                "query_results": query_results,
                "doc_ids": _dedupe_keep_order(
                    [
                        str(doc_id)
                        for result in query_results
                        for doc_id in result.get("doc_ids", [])
                        if doc_id
                    ]
                ),
            }
        )

    run_round(1, "initial_multi_query", sub_queries)
    merged = _merge_retrieval_candidates(retrieval_rounds)
    final_items = _rerank_results(
        rewrite["rewritten_query"],
        merged,
        top_k,
        query_profile=query_profile,
        required_evidence_types=required_evidence_types,
    )
    evidence_judge = judge_evidence_sufficiency(final_items, required_evidence_types)
    second_round_queries: List[Dict[str, str]] = []

    if (
        not evidence_judge.get("evidence_sufficient")
        and MAX_AGENTIC_RAG_ROUNDS >= 2
        and evidence_judge.get("missing_evidence_types")
    ):
        second_round_queries = _build_followup_queries(
            evidence_judge.get("missing_evidence_types", []),
            rewrite.get("defect_types", []),
        )
        already_queried = {item["query"] for item in sub_queries}
        second_round_queries = [item for item in second_round_queries if item["query"] not in already_queried]
        if second_round_queries:
            run_round(2, "evidence_gap_repair", second_round_queries)
            merged = _merge_retrieval_candidates(retrieval_rounds)
            final_items = _rerank_results(
                rewrite["rewritten_query"],
                merged,
                top_k,
                query_profile=query_profile,
                required_evidence_types=required_evidence_types,
            )
            evidence_judge = judge_evidence_sufficiency(final_items, required_evidence_types)

    if not evidence_judge.get("evidence_sufficient"):
        warnings.append("rag_evidence_insufficient:" + ",".join(evidence_judge.get("missing_aspects", [])))

    trace = build_agentic_rag_trace(
        query=query,
        top_k=top_k,
        items=final_items,
        rewrite=rewrite,
        sub_queries=sub_queries,
        retrieval_rounds=retrieval_rounds,
        evidence_judge=evidence_judge,
        second_round_queries=second_round_queries,
        warnings=warnings,
    )
    return {
        "query": query,
        "top_k": top_k,
        "items": final_items,
        "context_items": [item for item in final_items if item.get("included_in_answer_context", True)],
        "trace": trace,
        "rewrite": rewrite,
        "evidence_judge": evidence_judge,
        "second_round_queries": second_round_queries,
        "warnings": warnings,
    }


def get_rag_status() -> Dict[str, Any]:
    chunks = _load_chunks()
    return {
        "knowledge_base_path": str(KB_PATH),
        "index_dir": str(INDEX_DIR),
        "index_exists": INDEX_PATH.exists() and METADATA_PATH.exists(),
        "chunk_count": len(chunks),
        "embedding_model": _embedding_model_name(),
        "faiss_available": importlib.util.find_spec("faiss") is not None,
        "sentence_transformers_available": importlib.util.find_spec("sentence_transformers") is not None,
        "numpy_available": importlib.util.find_spec("numpy") is not None,
    }
