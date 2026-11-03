"""LLM · 임베딩 클라이언트 (SSAFY GMS, OpenAI 호환).

키는 환경변수 GMS_KEY에서만 읽는다 (NF2003).
테스트에서는 set_overrides()로 가짜 모델을 꽂아 외부 호출 없이 돌린다.
"""

from __future__ import annotations

from typing import Any

from .config import get_settings
from .errors import MissingKeyError

_overrides: dict[str, Any] = {}
_cache: dict[str, Any] = {}


def set_overrides(chat: Any = None, embeddings: Any = None) -> None:
    """테스트용: 가짜 모델로 바꿔 끼운다. None을 넘기면 해제."""
    _cache.clear()
    _overrides.clear()
    if chat is not None:
        _overrides["chat"] = chat
    if embeddings is not None:
        _overrides["embeddings"] = embeddings


def has_api_key() -> bool:
    return bool(_overrides) or bool(get_settings().gms_key)


def get_chat_model():
    if "chat" in _overrides:
        return _overrides["chat"]
    if "chat" not in _cache:
        s = get_settings()
        if not s.gms_key:
            raise MissingKeyError()
        from langchain_openai import ChatOpenAI

        cfg = s.section("llm")
        _cache["chat"] = ChatOpenAI(
            model=cfg["chat_model"],
            api_key=s.gms_key,
            base_url=cfg["base_url"],
            timeout=cfg.get("timeout", 60),
            max_retries=cfg.get("max_retries", 2),
        )
    return _cache["chat"]


def get_embeddings():
    if "embeddings" in _overrides:
        return _overrides["embeddings"]
    if "embeddings" not in _cache:
        s = get_settings()
        if not s.gms_key:
            raise MissingKeyError()
        from langchain_openai import OpenAIEmbeddings

        cfg = s.section("llm")
        _cache["embeddings"] = OpenAIEmbeddings(
            model=cfg["embedding_model"],
            api_key=s.gms_key,
            base_url=cfg["base_url"],
            # 토큰 길이 확인용 tiktoken 파일 다운로드를 피한다 (교육장 네트워크 제한 대비)
            check_embedding_ctx_length=False,
            timeout=cfg.get("timeout", 60),
            max_retries=cfg.get("max_retries", 2),
        )
    return _cache["embeddings"]


def message_text(message: Any) -> str:
    """모델 응답 → 문자열. content가 블록 목록으로 오는 모델도 처리한다."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts).strip()
    return str(content).strip()


def chat(messages: list[tuple[str, str]]) -> str:
    """[("system", ...), ("human", ...)] → 응답 문자열."""
    return message_text(get_chat_model().invoke(messages))
