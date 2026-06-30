import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from rag.retriever import build_rag_trace, get_rag_status, retrieve_agentic_knowledge, retrieve_knowledge


def test_retrieve_knowledge_keyword_fallback():
    results = retrieve_knowledge("裂纹为什么需要重点关注？", top_k=2)

    assert results
    assert results[0]["doc_id"] == "defect_type_crack"
    assert results[0]["retriever"] in {"faiss_bge", "keyword_fallback"}


def test_rag_status_has_chunks():
    status = get_rag_status()

    assert status["chunk_count"] >= 10
    assert status["embedding_model"]


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
    assert trace["retriever"] in {"faiss_bge", "keyword_fallback"}
    first = trace["retrieved_candidates"][0]
    assert "metadata_score" in first
    assert "rerank_score" in first
    assert "rerank_reason" in first
    assert "evidence_budget" in trace


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
