import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from rag.retriever import (
    _fuse_hybrid_results,
    build_rag_trace,
    get_rag_status,
    retrieve_agentic_knowledge,
    retrieve_knowledge,
)


RETRIEVER_NAMES = {"hybrid_faiss_bm25", "faiss_bge", "bm25", "bm25_fallback", "keyword_fallback"}


def test_retrieve_knowledge_keyword_fallback():
    results = retrieve_knowledge("裂纹为什么需要重点关注？", top_k=2)

    assert results
    assert results[0]["doc_id"] == "defect_type_crack"
    assert results[0]["retriever"] in RETRIEVER_NAMES


def test_rag_status_has_chunks():
    status = get_rag_status()

    assert status["chunk_count"] >= 10
    assert status["embedding_model"]
    assert status["retriever_mode"] in {"hybrid", "faiss", "bm25"}
    assert status["bm25_available"] is True


def test_rag_trace_contains_retrieval_debug_fields():
    results = retrieve_knowledge("裂纹为什么需要重点关注？", top_k=2)
    trace = build_rag_trace(
        query="裂纹为什么需要重点关注？",
        top_k=2,
        items=results,
        need_rag=True,
        answer_mode="fallback",
    )

    assert trace["trace_id"].startswith("rag_")
    assert trace["need_rag"] is True
    assert trace["answer_mode"] == "fallback"
    assert trace["retrieved_candidates"]
    assert trace["selected_doc_ids"][0] == results[0]["doc_id"]
    assert trace["retriever"] in RETRIEVER_NAMES
    first = trace["retrieved_candidates"][0]
    assert "metadata_score" in first
    assert "rerank_score" in first
    assert "rerank_reason" in first
    assert any(key in first for key in ["fusion_score", "dense_score", "bm25_score", "keyword_score"])
    assert "evidence_budget" in trace


def test_bm25_mode_exposes_lexical_scores(monkeypatch):
    monkeypatch.setenv("RAG_RETRIEVER_MODE", "bm25")
    results = retrieve_knowledge("开裂是不是很危险，要不要人工确认？", top_k=5)

    assert results
    assert results[0]["doc_id"] == "defect_type_crack"
    assert results[0]["retriever"] == "bm25"
    assert results[0]["bm25_rank"] >= 1
    assert results[0]["bm25_score"] > 0
    assert "metadata_score" in results[0]


def test_hybrid_rrf_fuses_dense_and_bm25_signals():
    dense_results = [
        {"doc_id": "defect_type_crack", "title": "裂纹缺陷说明", "rank": 1, "dense_rank": 1, "dense_score": 0.91},
        {"doc_id": "severity_rule", "title": "缺陷等级规则", "rank": 2, "dense_rank": 2, "dense_score": 0.82},
    ]
    bm25_results = [
        {"doc_id": "severity_rule", "title": "缺陷等级规则", "rank": 1, "bm25_rank": 1, "bm25_score": 7.2},
        {"doc_id": "review_loop_standard", "title": "缺陷复核闭环建议", "rank": 2, "bm25_rank": 2, "bm25_score": 5.4},
    ]

    fused = _fuse_hybrid_results(dense_results, bm25_results, top_k=3)

    assert fused
    assert fused[0]["retriever"] == "hybrid_faiss_bm25"
    assert fused[0]["fusion_strategy"] == "reciprocal_rank_fusion"
    assert fused[0]["fusion_score"] > 0
    assert "fusion_components" in fused[0]
    assert any(item["doc_id"] == "review_loop_standard" for item in fused)


def test_rag_business_rerank_keeps_defect_context_clean():
    results = retrieve_knowledge("裂纹为什么需要重点关注？", top_k=5)
    doc_ids = [item["doc_id"] for item in results]

    assert doc_ids[0] == "defect_type_crack"
    assert "defect_cause_checklist" in doc_ids
    assert all(
        item["doc_id"] == "defect_type_crack" or item.get("category") != "defect_type"
        for item in results
    )


def test_agentic_rag_rewrites_colloquial_question():
    result = retrieve_agentic_knowledge("开裂是不是很危险，要不要人工确认？", top_k=5)
    trace = result["trace"]
    doc_ids = [item["doc_id"] for item in result["items"]]

    assert trace["rewrite_success"] is True
    assert "裂纹" in trace["rewritten_query"]
    assert trace["evidence_sufficient"] is True
    assert trace["context_evidence_sufficient"] is True
    assert "review_loop" in trace["covered_evidence_types"]
    assert "review_loop" in trace["covered_context_evidence_types"]
    assert doc_ids[0] == "defect_type_crack"


def test_agentic_rag_keeps_surface_standard_optional_for_review_question():
    result = retrieve_agentic_knowledge("开裂危险程度 是否需要人工确认 判定标准", top_k=5)
    trace = result["trace"]

    assert trace["evidence_sufficient"] is True
    assert trace["context_evidence_sufficient"] is True
    assert "surface_standard" not in trace["required_evidence_types"]
    assert "review_loop" in trace["covered_context_evidence_types"]


def test_agentic_rag_exposes_multi_query_trace():
    result = retrieve_agentic_knowledge("裂纹集中在头部和边部是不是工艺问题？", top_k=5)
    trace = result["trace"]

    assert len(trace["sub_queries"]) >= 3
    assert trace["retrieval_rounds"]
    assert "spatial_rule" in trace["required_evidence_types"]
    assert any(item["doc_id"] == "spatial_distribution_rule" for item in result["items"])
