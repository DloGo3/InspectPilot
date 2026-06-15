from pathlib import Path
from typing import Dict, List

KB_PATH = Path(__file__).resolve().parent / "knowledge_base.md"


def _load_chunks() -> List[Dict[str, str]]:
    raw = KB_PATH.read_text(encoding="utf-8")
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
        if meta.get("id"):
            chunks.append(
                {
                    "doc_id": meta.get("id", ""),
                    "title": meta.get("title", ""),
                    "category": meta.get("category", ""),
                    "tags": meta.get("tags", ""),
                    "content": body,
                }
            )
    return chunks


def retrieve_knowledge(query: str, top_k: int = 3) -> List[Dict[str, str]]:
    """A tiny keyword retriever. Replace with FAISS/Milvus embeddings when the KB grows."""
    chunks = _load_chunks()
    scored = []
    query_terms = {t for t in query.replace("/", " ").replace("，", " ").replace("？", " ").split() if t}

    for chunk in chunks:
        haystack = f"{chunk['title']} {chunk['category']} {chunk['tags']} {chunk['content']}"
        score = 0
        for term in query_terms:
            if term in haystack:
                score += 3
        for keyword in ["裂纹", "结疤", "氧化皮", "等级", "标准", "报告", "原因", "头部", "边部"]:
            if keyword in query and keyword in haystack:
                score += 2
        if score:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_k]]
