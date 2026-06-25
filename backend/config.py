import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - python-dotenv is optional at import time.
    load_dotenv = None


BACKEND_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    openai_api_key: Optional[str]
    openai_base_url: Optional[str]
    model_name: str
    embedding_model_name: str
    rag_top_k: int

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key or self.openai_base_url)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def get_settings() -> Settings:
    if load_dotenv is not None:
        load_dotenv(BACKEND_DIR / ".env")
        load_dotenv(BACKEND_DIR.parent / ".env")

    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
        model_name=os.getenv("MODEL_NAME", "gpt-4o-mini"),
        embedding_model_name=os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh-v1.5"),
        rag_top_k=max(1, min(_env_int("RAG_TOP_K", 3), 10)),
    )
