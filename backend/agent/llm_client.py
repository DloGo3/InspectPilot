import json
from typing import Any, Dict, List, Optional

from config import Settings


def _client(settings: Settings):
    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover - depends on optional package install.
        raise RuntimeError(f"openai_package_unavailable:{exc}") from exc

    api_key = settings.openai_api_key or "EMPTY"
    kwargs: Dict[str, Any] = {"api_key": api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**kwargs)


def chat_completion(
    settings: Settings,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    temperature: float = 0.1,
) -> Any:
    client = _client(settings)
    kwargs: Dict[str, Any] = {
        "model": settings.model_name,
        "messages": messages,
        "temperature": temperature,
    }
    if tools is not None:
        kwargs["tools"] = tools
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    return client.chat.completions.create(**kwargs)


def extract_json_object(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}

