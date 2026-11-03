"""RAG 사용 전후 답변 비교 (F2015) → docs/rag_comparison.md

    python scripts/compare_rag.py
    python scripts/compare_rag.py --questions my_questions.json   # [{"item": "숭례문", "question": "..."}, ...]

같은 질문을 (1) RAG 없이 LLM에게, (2) 근거를 붙여 이 서비스로 물어 나란히 기록한다.
'근거 제시'와 '모름 인정'은 자동으로 채우고, '사실 정확성'은 근거 원문을 보고 직접 채운다.
"""

import _bootstrap  # noqa: F401

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

from core.config import get_settings
from core.errors import friendly_message
from data_prep.items import get_catalog
from services.evaluation import RagComparison, compare_rag, md_cell

# 근거 없이 답하면 틀리기 쉬운 대표 질문 (요구사항 정의서 2.1의 질문과 같다)
DEFAULT_QUESTIONS = [
    {"item": "숭례문", "question": "2008년 화재 뒤 복원하면서 원형과 달라진 부분은 무엇인가?"},
    {"item": "석굴암", "question": "석굴암 본존불을 지금도 공식적으로 '국보 제24호'라고 부르나?"},
    {"item": "반가사유상", "question": "이 반가사유상은 언제 만들어졌고, 어디에 있나?"},
    {"item": "훈민정음", "question": "훈민정음 해례본은 지금 어디에 소장되어 있나?"},
    {"item": "다보탑", "question": "다보탑 기단의 돌사자는 원래 몇 마리였고 지금은 몇 마리 남아 있나?"},
    {"item": "숭례문", "question": "숭례문 복원 공사에 참여한 목수의 이름과 하루 품삯은?"},  # 문서에 없을 질문 — 모름 인정 확인
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questions", help="질문 목록 JSON 파일")
    ap.add_argument("--out", help="결과 파일 (기본 docs/rag_comparison.md)")
    args = ap.parse_args(argv)
    qs = DEFAULT_QUESTIONS
    if args.questions:
        with open(args.questions, encoding="utf-8") as f:
            qs = json.load(f)

    catalog = get_catalog()
    rows: list[RagComparison] = []
    for q in qs:
        item = catalog.find_by_name(q["item"])
        if not item:
            print(f"  - '{q['item']}' 국보가 목록에 없어 건너뜀")
            continue
        print(f"  … {item['name']}: {q['question']}")
        try:
            rows.append(compare_rag(item, q["question"]))
        except Exception as e:
            print("  ✗", friendly_message(e))
            return 1

    lines = [
        f"# RAG 사용 전후 답변 비교 ({datetime.now():%Y-%m-%d %H:%M})",
        "",
        "- RAG 없이: 같은 모델에 질문만 보냄 (근거 없음)",
        "- RAG 사용: 국보 메타데이터 + 위키백과 + 국가유산청 설명에서 근거를 찾아 답함",
        "- 근거 제시: 답변이 인용한 근거 수 / 모름 인정: '확인되지 않는다' 류의 표현 여부 (자동)",
        "- 사실 정확성: 근거 원문과 대조해 직접 기입 (O / △ / X)",
        "",
        "| # | 국보 | 질문 | RAG 없이 | RAG 사용 | 근거 제시 (없이 / 사용) | 모름 인정 (없이 / 사용) | 사실 정확성 (없이 / 사용) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i} | {md_cell(r.item_name)} | {md_cell(r.question)} | {md_cell(r.without_rag)} | {md_cell(r.with_rag)} | "
            f"0건 / {r.rag_cites}건 | {'O' if r.admits_unknown(r.without_rag) else 'X'} / "
            f"{'O' if r.admits_unknown(r.with_rag) else 'X'} |   /   |")
    lines += ["", "## RAG 사용 답변의 근거", ""]
    for i, r in enumerate(rows, 1):
        lines.append(f"**{i}. {r.item_name}** — " + (", ".join(
            f"[근거 {e.number}] {e.source_type} · [{e.title}]({e.url})" for e in r.cited) or "인용 없음"))
        lines.append("")
    lines += ["## 정리 (직접 작성)", "", "- 사실 정확성:", "- 근거 제시:", "- 모르는 것을 모른다고 답하는지:", ""]

    path = Path(args.out) if args.out else get_settings().root / "docs" / "rag_comparison.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n→ {path} ({len(rows)}개 질문)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
