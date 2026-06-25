from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

KB_PATH = Path(__file__).resolve().parent / "knowledge_base.md"
INDEX_DIR = Path(os.getenv("RAG_INDEX_DIR", Path(__file__).resolve().parent / "faiss_index"))
INDEX_PATH = INDEX_DIR / "knowledge.index"
METADATA_PATH = INDEX_DIR / "knowledge_meta.json"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"

DOMAIN_TERMS = [
    "裂纹",
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

_MODEL_CACHE: Dict[str, Any] = {}


def _embedding_model_name(model_name: Optional[str] = None) -> str:
    return model_name or os.getenv("EMBEDDING_MODEL_NAME", DEFAULT_EMBEDDING_MODEL)


def _load_chunks(kb_path: Path = KB_PATH) -> List[Dict[str, str]]:
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

    chunks: List[Dict[str, str]] = []
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
            chunks.append(
                {
                    "doc_id": doc_id,
                    "title": meta.get("title", "").strip(),
                    "category": meta.get("category", "").strip(),
                    "tags": meta.get("tags", "").strip(),
                    "content": content,
                    "source": kb_path.name,
                }
            )
    return chunks


def _chunk_text(chunk: Dict[str, str]) -> str:
    return "\n".join(
        [
            f"标题：{chunk.get('title', '')}",
            f"类别：{chunk.get('category', '')}",
            f"标签：{chunk.get('tags', '')}",
            f"内容：{chunk.get('content', '')}",
        ]
    )


def _fingerprint(chunks: List[Dict[str, str]], model_name: str) -> str:
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


def _load_faiss_index(chunks: List[Dict[str, str]], model_name: str) -> Optional[Tuple[Any, List[Dict[str, str]]]]:
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
    chunk: Dict[str, str],
    rank: int,
    score: float,
    retriever: str,
    model_name: Optional[str] = None,
    vector_error: Optional[str] = None,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        **chunk,
        "rank": rank,
        "score": round(float(score), 4),
        "retriever": retriever,
    }
    if model_name:
        item["embedding_model"] = model_name
    if vector_error:
        item["vector_error"] = vector_error
    return item


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


def _keyword_score(query: str, chunk: Dict[str, str]) -> float:
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


def retrieve_knowledge(query: str, top_k: int = 3, model_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve defect-domain knowledge. FAISS+BGE is used when available; keyword fallback keeps demos offline."""
    query = (query or "").strip()
    if not query:
        return []

    top_k = max(1, min(int(top_k or 3), 10))
    model_name = _embedding_model_name(model_name)

    try:
        results = _retrieve_with_faiss(query, top_k, model_name)
        if results:
            return results
    except Exception as exc:
        return _retrieve_with_keywords(query, top_k, vector_error=str(exc))

    return _retrieve_with_keywords(query, top_k)


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
