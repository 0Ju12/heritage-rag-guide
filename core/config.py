"""설정 로드 — config.yaml + 환경변수(.env).

API 키는 환경변수로만 읽는다 (NF2003). config.yaml에는 키를 쓰지 않는다.
경로는 모두 프로젝트 폴더 기준으로 풀어 둔다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# utf-8-sig: 윈도우 메모장이 'UTF-8(BOM)'으로 저장해도 첫 줄의 키 이름이 깨지지 않게
load_dotenv(PROJECT_ROOT / ".env", encoding="utf-8-sig")


@dataclass(frozen=True)
class Settings:
    raw: dict[str, Any]
    root: Path

    # ── 경로 ──────────────────────────────────────────
    @property
    def data_dir(self) -> Path:
        return self.root / self.raw["app"]["data_dir"]

    @property
    def items_path(self) -> Path:
        return self.data_dir / "items.json"

    @property
    def official_dir(self) -> Path:
        return self.data_dir / "official"

    @property
    def wiki_dir(self) -> Path:
        return self.data_dir / "wiki"

    @property
    def manifest_path(self) -> Path:
        return self.data_dir / "wiki_manifest.json"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def chroma_dir(self) -> Path:
        return self.root / self.raw["vectorstore"]["persist_dir"]

    # ── 묶음 ──────────────────────────────────────────
    def section(self, name: str) -> dict[str, Any]:
        return self.raw.get(name, {})

    @property
    def title(self) -> str:
        return self.raw["app"]["title"]

    # ── 환경변수 ──────────────────────────────────────
    @property
    def gms_key(self) -> str:
        return os.environ.get("GMS_KEY", "").strip()

    @property
    def wiki_contact(self) -> str:
        return os.environ.get("WIKI_CONTACT", "").strip()


def _config_path() -> Path:
    return Path(os.environ.get("HERITAGE_RAG_CONFIG", PROJECT_ROOT / "config.yaml"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    path = _config_path()
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Settings(raw=raw, root=PROJECT_ROOT)


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
