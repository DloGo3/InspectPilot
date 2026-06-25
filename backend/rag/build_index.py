from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from rag.retriever import build_faiss_index, get_rag_status


def main() -> int:
    parser = argparse.ArgumentParser(description="Build InspectPilot FAISS/BGE knowledge index.")
    parser.add_argument("--force", action="store_true", help="Rebuild even when metadata fingerprint is unchanged.")
    parser.add_argument("--status", action="store_true", help="Print RAG dependency and index status without building.")
    parser.add_argument("--model", default=None, help="SentenceTransformer/BGE model name.")
    args = parser.parse_args()

    payload = get_rag_status() if args.status else build_faiss_index(force_rebuild=args.force, model_name=args.model)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
