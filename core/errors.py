"""사용자에게 보여 줄 오류 문구와 로그.

화면에는 안내 문구만 보이고, 오류 상세(트레이스백)는 로그 파일에만 남긴다 (NF2004).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import get_settings


class AppError(Exception):
    """화면에 그대로 보여 줘도 되는 안내 문구를 가진 오류."""

    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.message = message
        self.kind = kind


class MissingKeyError(AppError):
    def __init__(self):
        super().__init__("GMS_KEY가 설정되지 않았습니다. 프로젝트 폴더의 .env 파일에 GMS_KEY를 넣고 다시 실행해 주세요.", "key")


class IndexEmptyError(AppError):
    def __init__(self, what: str = "국보 메타데이터"):
        super().__init__(
            f"{what} 색인이 비어 있습니다. 터미널에서 `python scripts/collect_items.py` → "
            "`python scripts/index_items.py` 순서로 실행해 주세요.",
            "index",
        )


class ItemNotFoundError(AppError):
    def __init__(self, item_id: str):
        super().__init__(f"선택한 국보({item_id})를 찾지 못했습니다. 목록에서 다시 골라 주세요.", "item")


def friendly_message(exc: BaseException) -> str:
    """예외 → 화면용 한 줄 안내. 내부 정보(키, 프롬프트, 트레이스백)는 넣지 않는다."""
    if isinstance(exc, AppError):
        return exc.message
    name = type(exc).__name__
    if name == "AuthenticationError":
        return "API 키가 올바르지 않습니다. .env의 GMS_KEY를 확인해 주세요."
    if name in ("APIConnectionError", "APITimeoutError", "ConnectionError", "Timeout", "ReadTimeout", "ConnectTimeout"):
        return "외부 서비스에 연결하지 못했습니다. 네트워크를 확인하고 잠시 뒤 다시 시도해 주세요."
    if name == "RateLimitError":
        return "요청이 많아 잠시 제한되었습니다. 잠시 뒤 다시 시도해 주세요."
    return "처리 중 문제가 생겼습니다. 잠시 뒤 다시 시도해 주세요."


_configured = False


def get_logger(name: str = "heritage_rag") -> logging.Logger:
    """data/logs/app.log 에 남기는 로거. 콘솔(화면)에는 오류 상세를 내보내지 않는다."""
    global _configured
    logger = logging.getLogger(name)
    if not _configured:
        log_dir = get_settings().log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_dir / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger("heritage_rag")
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        root.propagate = False
        _configured = True
    return logger
