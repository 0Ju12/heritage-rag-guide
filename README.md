# 🏛️ 국보 입문 가이드 — 근거를 인용하는 RAG 국가유산 Q&A

국보를 고르고 질문하면 **국보 메타데이터 · 한국어 위키백과 · 국가유산청 공식 설명**에서 근거를 찾아
문장마다 `[근거 N]`을 붙여 답하고, **실제로 인용한 근거만** 원문 링크와 함께 보여 주는 LLM 서비스입니다.
문서에서 확인되지 않는 내용은 추측하지 않고 "제공된 문서에서 확인되지 않습니다"라고 답합니다.

> SSAFY 16기 AI 코어 프로젝트 2 (개인, 2026.10) — 데이터 수집부터 RAG 파이프라인·화면까지 직접 구현

```
나  : 서울 숭례문 — 2008년 화재 뒤 복원하면서 원형과 달라진 부분은?
안내: 2008년 2월 방화로 누각 2층이 무너졌고 2013년 5월 다시 공개되었습니다 [근거 3].
      복구 때 좌우 성곽 일부를 함께 복원했습니다 [근거 3]. 위키백과에는 기와·단청 재료 논란이 기록돼 있습니다 [근거 2].
답변에 사용한 근거
 [근거 1] 🏷️ 국보 메타데이터 · 서울 숭례문
 [근거 2] 📖 위키백과 · 숭례문 방화 사건
 [근거 3] 🏛️ 국가유산청 · 서울 숭례문 (국가유산청 설명)
```

## 무엇을 만들었나

| 단계 | 내용 | 코드 |
|---|---|---|
| **데이터 수집** | 국가유산청 오픈API(XML, EUC-KR 대응)로 국보 목록·상세 수집 → 지정 해제 제외, 공식 설명문 HTML 정제 | `data_prep/khs_api.py`, `collect_items.py` |
| | 국보 이름 → 한국어 위키백과 문서 자동 연결 (정확 일치 → 지역명 제거 → 검색, `석굴`·`삼층석탑` 같은 일반명사 문서 오연결 방지) | `data_prep/collect_items.py` |
| | 공손한 HTTP 클라이언트: User-Agent 연락처, 호출 간격, 429/5xx `Retry-After` 재시도 | `data_prep/http_client.py` |
| **색인 (RAG 1·2)** | 국보 1건 = 청크 1개 메타데이터 컬렉션 + 위키·공식 설명 청크 컬렉션 (ChromaDB). 청크 ID를 `국보ID:문서ID:순번`으로 고정해 재실행해도 중복 없음 | `vectorstore/` |
| | 출처별 청킹 설정 (위키 1000/200, 공식 설명 800/100) | `config.yaml`, `vectorstore/chunking.py` |
| **질문 시 수집** | 프롬프트 1이 검색어 추출(국보 자체 문서 항상 첫 번째) → 위키 검색 → 프롬프트 2가 관련 문서만 선별 → 본문 수집·색인. 같은 질문은 다시 수집하지 않는 캐시, 위키 장애 시 저장 문서로 대체 | `data_prep/collector.py`, `docs_store.py` |
| **검색·생성** | LangGraph `retrieve → generate`. 선택 국보 메타 + 국보 범위로 필터한 문서 검색(유사도/MMR) + 관련 국보 → 병합·중복 제거·근거 번호 부여 | `rag/` |
| **인용 검증** | 답변의 `[근거 N]`을 파싱해 **근거 목록에 없는 번호는 지우고**, 실제 인용한 근거만 화면에 표시 | `rag/citations.py` |
| **특화 기능** | 관람 해설 카드, 통설 판정(사실/일부 사실/다름/확인 불가), 조건으로 국보 찾기(LLM이 고른 ID 중 후보에 있는 것만 허용) | `services/` |
| **화면** | Streamlit 앱 + FastAPI·HTML/CSS/JS 화면(같은 서비스 계층 공유), 사진 배경·관련 링크(유튜브·지도) | `app.py`, `api/`, `frontend/` |
| **안정성** | 사용자에게는 안내 문구만, 상세 오류는 로그 파일로 (키·트레이스백 노출 방지 테스트 포함) | `core/errors.py` |

## LLM 응답을 믿지 않는 설계

- 검색어·문서 선별·조건 탐색 결과는 JSON으로 받되, **형식이 깨지면 안전한 기본값**(국보 이름으로만 검색 등)으로 떨어지게 파싱
- 조건 탐색은 LLM이 낸 ID 중 **실제 후보에 있는 것만** 채택 → 없는 국보가 끼어들 수 없음
- 답변 인용은 코드가 다시 검사해 존재하지 않는 근거 번호를 제거
- 선별 단계에서 LLM이 실패하면 그 시도 기록을 남기지 않아(manifest 롤백) **다음 질문이 오염되지 않음**

## 테스트

외부 호출 없이 **전체 파이프라인 50개 테스트**가 돕니다 — 가짜 LLM(`tests/fakes.py`)·결정적 임베딩·가짜 위키/국가유산청 응답,
Streamlit `AppTest`로 실제 화면 실행, FastAPI `TestClient`, 로컬 OpenAI 호환 서버로 실제 클라이언트 설정 검증.

```bash
pip install -r requirements-dev.txt
python -m pytest -q        # 50 passed
```

## 실행

```bash
pip install -r requirements.txt
cp .env.example .env                    # GMS_KEY(OpenAI 호환 키), WIKI_CONTACT(위키 User-Agent 연락처 이메일)
python scripts/check_setup.py           # 키·네트워크 점검
python scripts/collect_items.py         # 국보 메타데이터 + 국가유산청 설명 수집
python scripts/index_items.py           # RAG 1 색인
python scripts/index_official.py        # RAG 2 색인
streamlit run app.py                    # 또는 uvicorn api.server:app --port 8000
```

자세한 사용법·설정·검증 체크리스트는 [docs/USAGE.md](docs/USAGE.md).

## 데이터와 라이선스

수집 데이터(`data/`)와 벡터 DB는 저장소에 포함하지 않습니다. 실행 시 직접 수집됩니다.
- 국가유산청 국가유산 검색 오픈API — 공공누리 정책에 따라 출처 표시
- 한국어 위키백과 (CC BY-SA 4.0) — 근거마다 문서 제목·원문 링크 표시

## 기술

Python · LangChain · LangGraph · ChromaDB · OpenAI 호환 API(gpt-5.4-nano, text-embedding-3-small) · Streamlit · FastAPI · pytest
