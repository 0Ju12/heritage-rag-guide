"""근거 번호 해석 (F2008).

답변 본문에서 [근거 3], [근거 1, 3], [근거 2·4], [근거2][근거5] 같은 표기를 찾아
실제로 인용한 근거만 남긴다. 근거 목록에 없는 번호는 무시한다.
"""

from __future__ import annotations

import re

from .retriever import Evidence

CITE_PATTERN = re.compile(r"\[근거\s*([\d\s,·、~\-–]+)\]")


def cited_numbers(answer: str) -> list[int]:
    nums: list[int] = []
    for group in CITE_PATTERN.findall(answer or ""):
        for part in re.split(r"[,·、\s]+", group.strip()):
            if not part:
                continue
            rng = re.fullmatch(r"(\d+)\s*[~\-–]\s*(\d+)", part)
            if rng:
                a, b = int(rng.group(1)), int(rng.group(2))
                nums += list(range(min(a, b), max(a, b) + 1))[:20]
            elif part.isdigit():
                nums.append(int(part))
    return list(dict.fromkeys(nums))


def cited_evidence(answer: str, evidence: list[Evidence]) -> list[Evidence]:
    wanted = set(cited_numbers(answer))
    return [e for e in evidence if e.number in wanted]


def unknown_numbers(answer: str, evidence: list[Evidence]) -> list[int]:
    have = {e.number for e in evidence}
    return [n for n in cited_numbers(answer) if n not in have]


def strip_unknown_citations(answer: str, evidence: list[Evidence]) -> str:
    """근거 목록에 없는 번호를 가리키는 표기는 지운다 (화면과 번호가 어긋나지 않게)."""
    have = {e.number for e in evidence}

    def fix(m: re.Match) -> str:
        nums = [n for n in cited_numbers(m.group(0)) if n in have]
        return f"[근거 {', '.join(map(str, nums))}]" if nums else ""

    return CITE_PATTERN.sub(fix, answer or "")
