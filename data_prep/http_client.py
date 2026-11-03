"""외부 API 호출 공통 — 재시도 · 호출 간격 · 식별 정보 (NF2006).

    - User-Agent에 연락처(WIKI_CONTACT)를 넣는다. 위키미디어 정책상 연락처가 있어야 한도가 넉넉하다.
    - 429/5xx는 Retry-After(없으면 지수 간격)만큼 기다렸다 다시 시도한다.
    - 호출 사이에 최소 간격을 둔다.
"""

from __future__ import annotations

import threading
import time

import requests

from core.config import get_settings

APP_NAME = "HeritageGuide-SSAFY/1.0"


class ExternalAPIError(Exception):
    """외부 API를 끝내 호출하지 못함."""


def user_agent() -> str:
    contact = get_settings().wiki_contact
    ua = f"{APP_NAME} ({contact}) python-requests" if contact else f"{APP_NAME} python-requests"
    try:
        ua.encode("latin-1")
    except UnicodeEncodeError:  # HTTP 헤더에는 한글을 쓸 수 없다
        ua = f"{APP_NAME} python-requests"
    return ua


class PoliteClient:
    def __init__(self, min_interval: float = 0.5, max_retries: int = 4, timeout: float = 20):
        self.min_interval = float(min_interval)
        self.max_retries = int(max_retries)
        self.timeout = float(timeout)
        self._last = 0.0
        self._lock = threading.Lock()
        self.session = requests.Session()

    def _wait_turn(self) -> None:
        with self._lock:
            gap = time.monotonic() - self._last
            if gap < self.min_interval:
                time.sleep(self.min_interval - gap)
            self._last = time.monotonic()

    def get(self, url: str, params: dict) -> requests.Response:
        wait = 2.0
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._wait_turn()
            try:
                resp = self.session.get(url, params=params, headers={"User-Agent": user_agent()}, timeout=self.timeout)
            except requests.RequestException as e:
                last_error = e
                time.sleep(wait)
                wait *= 2
                continue
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504):
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else wait
                time.sleep(min(delay, 60))
                wait *= 2
                last_error = requests.HTTPError(f"HTTP {resp.status_code}")
                continue
            raise ExternalAPIError(f"HTTP {resp.status_code}: {url}")
        raise ExternalAPIError(f"요청 실패({self.max_retries}회): {url} — {type(last_error).__name__}")

    def get_json(self, url: str, params: dict) -> dict:
        try:
            return self.get(url, params).json()
        except ValueError as e:
            raise ExternalAPIError(f"JSON 해석 실패: {url}") from e

    def get_bytes(self, url: str, params: dict) -> bytes:
        return self.get(url, params).content

    def get_text(self, url: str, params: dict) -> str:
        resp = self.get(url, params)
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = "utf-8"
        return resp.text
