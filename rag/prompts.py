"""프롬프트 — 역할과 출력 형식 (요구사항정의서 2.4).

    프롬프트 1  검색어 추출   (F2003)  도메인 전문가 역할, JSON 문자열 배열
    프롬프트 2  후보 문서 선별 (F2004)  제목·요약만 보고 고름, JSON 정수 배열
    프롬프트 3  답변 생성     (F2007)  근거만 사용, [근거 N] 표기, 없으면 "확인되지 않습니다"
    + 특화 기능(관람 해설·통설 판정, F2010), 조건 탐색 선별(F2011), RAG 없는 답변(F2015 비교용)

각 시스템 프롬프트의 "[작업] …" 줄은 로그와 테스트에서 어떤 프롬프트인지 구분하는 표지다.
"""

from __future__ import annotations

from data_prep.domain import DOMAIN, EXPERT_ROLE, FACTCHECK_LABELS

NOT_FOUND = "제공된 문서에서 확인되지 않습니다."

Messages = list[tuple[str, str]]


# ── 프롬프트 1: 검색어 추출 ───────────────────────────────────

def query_extraction(item_text: str, own_query: str, question: str, max_queries: int) -> Messages:
    system = f"""{EXPERT_ROLE}
[작업] 검색어 추출
사용자가 고른 {DOMAIN}과 질문을 보고, 한국어 위키백과에서 답의 근거가 될 문서를 찾을 검색어를 고른다.

규칙
1. 첫 번째 검색어는 반드시 {DOMAIN} 자체 문서인 "{own_query}" 이다.
2. 나머지는 질문에 답하는 데 필요한 관련 문서 제목처럼 짧은 명사구로 쓴다.
   (관련 사건, 소속 사찰·궁궐·건축물, 시대, 제작 기법, 관련 인물, 비교 대상 {DOMAIN})
3. 질문과 상관없는 일반어(예: "역사", "문화재")는 쓰지 않는다.
4. 모두 {max_queries}개 이하, 중복 없이.
5. 출력은 JSON 문자열 배열 하나만. 설명이나 코드블록을 붙이지 않는다.

출력 예: ["숭례문", "숭례문 방화 사건", "한양도성"]"""
    human = f"[{DOMAIN}]\n{item_text}\n\n[질문]\n{question}"
    return [("system", system), ("human", human)]


# ── 프롬프트 2: 후보 문서 선별 ────────────────────────────────

def candidate_selection(item_name: str, question: str, candidates: list[dict], max_selected: int) -> Messages:
    system = f"""{EXPERT_ROLE}
[작업] 후보 문서 선별
아래 후보는 위키백과 검색 결과의 제목과 요약이다. 본문을 받기 전에, 질문에 답하는 근거가 될 문서만 고른다.

고르는 기준
- 선택한 {DOMAIN}, 그것이 속한 장소·시대·사건·제작 기법, 질문이 직접 묻는 대상을 다룬 문서
버리는 기준
- 이름만 같은 다른 대상(동명이인, 다른 지역의 같은 이름 유산), 동음이의·목록 문서, 질문과 무관한 문서

출력은 고른 후보 번호의 JSON 정수 배열 하나만. 최대 {max_selected}개. 고를 것이 없으면 [].
출력 예: [1, 3]"""
    lines = [f"{i}. {c['title']} — {c.get('snippet', '')[:160]}" for i, c in enumerate(candidates, 1)]
    human = f"[선택한 {DOMAIN}]\n{item_name}\n\n[질문]\n{question}\n\n[후보]\n" + "\n".join(lines)
    return [("system", system), ("human", human)]


# ── 프롬프트 3: 답변 생성 (+ 특화 기능) ──────────────────────

_COMMON_RULES = f"""규칙
1. 아래 [근거]에 적힌 내용만 사용한다. 근거에 없는 사실을 사전 지식으로 보태지 않는다.
2. 근거에서 가져온 문장 끝에 [근거 N] 형식으로 번호를 붙인다. 여러 개면 [근거 1, 3].
3. 근거에서 확인되지 않는 내용은 추측하지 말고 "{NOT_FOUND}"라고 쓴다.
4. 출처끼리 내용이 다르면 출처를 밝혀 둘 다 제시한다. (예: 국가유산청 설명은 … [근거 2], 위키백과는 … [근거 3])
5. 설화·전승은 "전승에 따르면"이라고 써서 기록과 구분한다.
6. 근거 번호는 [근거]에 있는 번호만 쓴다."""


def answer_generation(mode: str, item_name: str, question: str, evidence_block: str, history: str = "") -> Messages:
    if mode == "guide":
        task = f"""[작업] 관람 해설 카드
{DOMAIN}을 처음 보러 가는 사람을 위한 관람 해설 카드를 쓴다.
아래 소제목 순서로 쓰되, 근거로 확인되지 않는 소제목은 통째로 빼고 맨 끝에 "확인되지 않은 항목: …"으로 적는다.
### 한눈에 보기
### 언제·누가·왜
### 현장에서 꼭 볼 부분
### 복원·보수 이력
### 함께 보면 좋은 유산"""
    elif mode == "factcheck":
        labels = " / ".join(FACTCHECK_LABELS)
        task = f"""[작업] 통설 판정
사용자가 들은 이야기(주장)가 근거와 맞는지 판정한다.
첫 줄은 반드시 "판정: <{labels}>" 중 하나로 쓴다.
- 근거로 맞다고 확인되면 "사실", 일부만 맞으면 "일부 사실", 근거와 어긋나면 "사실과 다름",
  근거에 판단할 내용이 없으면 "문서로 확인 불가".
둘째 줄부터 판정 이유를 2~5문장으로, 문장마다 [근거 N]을 붙여 쓴다."""
    else:
        task = """[작업] 근거 기반 답변
질문에 핵심부터 3~8문장으로 답한다. 나열이 필요하면 짧은 글머리표를 써도 된다."""

    system = f"{EXPERT_ROLE}\n{task}\n\n{_COMMON_RULES}"
    label = "주장" if mode == "factcheck" else "질문"
    parts = [f"[선택한 {DOMAIN}]\n{item_name}"]
    if history:
        parts.append(f"[이전 대화 — 맥락 참고용, 근거 아님]\n{history}")
    parts.append(f"[근거]\n{evidence_block}")
    parts.append(f"[{label}]\n{question}")
    return [("system", system), ("human", "\n\n".join(parts))]


# ── 조건 탐색 선별 (F2011) ───────────────────────────────────

def explore_selection(condition: str, candidates_block: str, max_results: int) -> Messages:
    system = f"""{EXPERT_ROLE}
[작업] 조건 탐색 선별
사용자의 조건과 {DOMAIN} 후보 목록(메타데이터)을 보고, 조건을 모두 만족하는 {DOMAIN}만 고른다.
- 후보의 메타데이터로 확인되는 경우에만 고른다. 확인되지 않으면 고르지 않는다.
- 조건이 여러 개면 전부 맞아야 한다.
출력은 JSON 배열 하나만: [{{"id": "후보 ID", "reason": "조건과 맞는 이유 한 문장"}}]
최대 {max_results}개. 맞는 것이 없으면 []."""
    human = f"[조건]\n{condition}\n\n[후보]\n{candidates_block}"
    return [("system", system), ("human", human)]


# ── RAG 없이 답하기 (F2015 비교용) ───────────────────────────

def no_rag_answer(item_name: str, question: str) -> Messages:
    system = f"{EXPERT_ROLE}\n[작업] 일반 답변\n질문에 한국어로 3~8문장으로 답한다."
    return [("system", system), ("human", f"[{DOMAIN}] {item_name}\n[질문] {question}")]
