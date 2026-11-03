"""LLM 출력에서 JSON 꺼내기 — 코드블록, 앞뒤 설명이 붙어도 견딘다."""

from __future__ import annotations

import json
import re
from typing import Any


def _strip_fences(text: str) -> str:
    return re.sub(r"```(?:json)?", "", text or "").strip()


def extract_json(text: str, kind: type = list) -> Any | None:
    """처음 나오는 JSON 배열(list) 또는 객체(dict)를 돌려준다. 못 찾으면 None."""
    t = _strip_fences(text)
    open_ch, close_ch = ("[", "]") if kind is list else ("{", "}")
    start = t.find(open_ch)
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(t)):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        val = json.loads(t[start:i + 1])
                        if isinstance(val, kind):
                            return val
                    except ValueError:
                        pass
                    break
        start = t.find(open_ch, start + 1)
    return None


def parse_string_list(text: str) -> list[str]:
    val = extract_json(text, list)
    if val is None:
        return []
    return [str(x).strip() for x in val if isinstance(x, (str, int, float)) and str(x).strip()]


def parse_int_list(text: str) -> list[int] | None:
    """[1, 3] → [1, 3]. 형식이 아예 틀리면 None (빈 배열 []과 구분)."""
    val = extract_json(text, list)
    if val is None:
        nums = re.findall(r"\d+", text or "")
        return [int(n) for n in nums] if nums else None
    out = []
    for x in val:
        if isinstance(x, bool):
            continue
        if isinstance(x, int):
            out.append(x)
        elif isinstance(x, str) and x.strip().isdigit():
            out.append(int(x.strip()))
        elif isinstance(x, dict):
            n = x.get("number") or x.get("index") or x.get("id")
            if isinstance(n, int) or (isinstance(n, str) and n.isdigit()):
                out.append(int(n))
    return out


def parse_object_list(text: str) -> list[dict]:
    val = extract_json(text, list)
    return [x for x in (val or []) if isinstance(x, dict)]
