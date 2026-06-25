import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from rag.retriever import get_rag_status, retrieve_knowledge


def test_retrieve_knowledge_keyword_fallback():
    results = retrieve_knowledge("裂纹为什么需要重点关注？", top_k=2)

    assert results
    assert results[0]["doc_id"] == "defect_type_crack"
    assert results[0]["retriever"] in {"faiss_bge", "keyword_fallback"}


def test_rag_status_has_chunks():
    status = get_rag_status()

    assert status["chunk_count"] >= 10
    assert status["embedding_model"]
