# 🏛️ 국보 입문 가이드 — RAG 기반 국가유산 지식 서비스

국보를 고르고 질문하면 **국보 메타데이터 · 한국어 위키백과 · 국가유산청 공식 설명**에서 근거를 찾아,
문장마다 `[근거 N]`을 붙여 답하고 **실제로 인용한 근거만** 출처 종류·원문 링크와 함께 보여 주는 서비스입니다.
문서에서 확인되지 않는 것은 추측하지 않고 "제공된 문서에서 확인되지 않습니다"라고 답합니다.

```
나  : 서울 숭례문 — 2008년 화재 뒤 복원하면서 원형과 달라진 부분은?
안내: 2008년 2월 방화로 누각 2층이 무너졌고 2013년 5월 다시 공개되었습니다 [근거 3].
      복구 때 좌우 성곽 일부를 함께 복원했습니다 [근거 3]. 위키백과에는 기와·단청 재료 논란이 기록돼 있습니다 [근거 2].
답변에 사용한 근거
 [근거 1] 🏷️ 국보 메타데이터 · 서울 숭례문 · 원문
 [근거 2] 📖 위키백과 · 숭례문 방화 사건 · 원문
 [근거 3] 🏛️ 국가유산청 · 서울 숭례문 (국가유산청 설명) · 원문
```

---

## 1. 빠른 시작

```bash
# 프로젝트 폴더에서
python -m venv .venv
.venv\Scripts\activate                 # Windows   (Mac: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env                 # Windows   (Mac: cp .env.example .env)  → GMS_KEY, WIKI_CONTACT 입력

python scripts/check_setup.py          # 0. 키·네트워크 점검
python scripts/collect_items.py        # 1. 국보 메타데이터 + 국가유산청 설명 수집  (약 5~10분)
python scripts/index_items.py          # 2. 국보 메타데이터 색인 (RAG 1)
python scripts/index_official.py       # 3. 국가유산청 설명 색인 (RAG 2, 출처 종류 ②)
streamlit run app.py                   # 4. 화면 실행 → http://localhost:8501
```
심화 F2013 화면: `uvicorn api.server:app --port 8000` → http://localhost:8000

---

## 2. 자세한 실행 방법

### 2-0. 준비물
- Python **3.10 이상** (3.10 ~ 3.13에서 동작)
- SSAFY **GMS 키** (LLM `gpt-5.4-nano`, 임베딩 `text-embedding-3-small` — `config.yaml`에서 변경 가능)
- 인터넷: `gms.ssafy.io`, `ko.wikipedia.org`, `www.khs.go.kr`(국가유산청)에 접속 가능해야 합니다.
  교육장 네트워크에서 국가유산청이 막히면 휴대폰 핫스팟으로 1단계만 실행하면 됩니다.

### 2-1. 가상환경과 설치
| | Windows (PowerShell / cmd) | Mac / Linux |
|---|---|---|
| 가상환경 만들기 | `python -m venv .venv` | `python3 -m venv .venv` |
| 켜기 | `.venv\Scripts\activate` | `source .venv/bin/activate` |
| 설치 | `pip install -r requirements.txt` | 같음 |

PowerShell에서 `activate`가 막히면 한 번만: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 2-2. `.env` 만들기 (API 키는 코드에 넣지 않음 — NF2003)
`.env.example`을 `.env`로 복사하고 채웁니다.
```
GMS_KEY=발급받은_키
WIKI_CONTACT=your-email@example.com     ← 영문 이메일 (위키백과 User-Agent 정책, 없으면 분당 10회 제한)
```

### 2-3. 실행 전 점검
```bash
python scripts/check_setup.py
```
① 환경변수 ② 위키백과 ③ 국가유산청 ④ GMS(LLM·임베딩)를 차례로 확인합니다. `✗`가 있으면 그 줄의 안내대로 해결하세요.

### 2-4. 데이터 수집 — `collect_items.py`
```bash
python scripts/collect_items.py              # 국보 전부
python scripts/collect_items.py --limit 20   # 빠른 시험
```
- 국가유산청 오픈API(키 불필요)에서 국보 목록 → 상세를 받아 `data/items.json`을 만들고,
  상세의 공식 설명문은 `data/official/{국보ID}.json`으로 따로 저장합니다 (출처 종류 "국가유산청").
- 국보 이름(예: "서울 숭례문")을 한국어 위키 문서 제목("숭례문")에 자동으로 연결합니다
  (정확한 제목 → 소재지로 판단한 지역명을 뗀 제목 → 끝 단어 → 위키 검색 순).
  끝 단어가 '석굴', '삼층석탑'처럼 일반명사면 그 단어만으로는 연결하지 않고, 맞는 문서가 없으면 연결을 비워 둡니다.
- 끝나면 건수와 **항목 1건의 색인 텍스트**를 출력합니다 (F2001 확인).

### 2-5. 색인 — `index_items.py`, `index_official.py`
```bash
python scripts/index_items.py          # 로드 건수 = 색인 건수, 두 번 실행해도 늘지 않음 (F2002)
python scripts/index_official.py       # 국가유산청 설명문 청킹·색인 (F2005, F2016)
```
위키백과 문서는 **질문할 때 자동으로** 수집·색인됩니다 (처음 들어온 검색어만, NF2002).
첫 질문을 빠르게 하고 싶으면 국보 자체 문서를 미리 받아 둘 수 있습니다:
```bash
python scripts/prefetch_wiki.py --limit 30   # (선택) 앞에서 30건
```

### 2-6. 화면 실행
```bash
streamlit run app.py                        # 필수 화면 (Streamlit)
uvicorn api.server:app --port 8000          # 심화 F2013 (HTML/CSS/JS + FastAPI), API 문서: /api/docs
```

### 2-7. 테스트 (선택)
외부 호출 없이(가짜 LLM·임베딩·API) 전체 기능을 검증합니다.
```bash
pip install -r requirements-dev.txt
python -m pytest            # 50개
```

---

## 3. 기능 (필수 / 심화)

| 번호 | 기능 | 화면에서 | 구현 위치 |
|---|---|---|---|
| F2001 | 국보 메타데이터 로드, 1건 = 색인 텍스트 1개 | `collect_items.py` 출력 | `data_prep/domain.py` `index_text()` |
| F2002 | 메타데이터 색인 (RAG 1), 재실행해도 중복 없음 | 사이드바 "색인 현황" | `vectorstore/store.py` `index_items()` |
| F2003 | 프롬프트 1 검색어 추출 (해설사 역할, JSON 배열, 자체 문서 항상 첫 번째) | 답변 아래 "문서 수집 과정" | `rag/prompts.py` `query_extraction()` |
| F2004 | 위키 검색 → 프롬프트 2 선별 → 본문·URL 수집, 자체 문서 최우선, 위키 차단 시 저장 문서로 대체 | "문서 수집 과정"의 색인한/버린 문서 | `data_prep/collector.py` |
| F2005 | 출처별 청킹(설정값), 별도 컬렉션, 청크 ID `국보ID:문서ID:순번` | — | `vectorstore/chunking.py` |
| F2006 | 선택 국보 메타 항상 포함 + 외부 문서 의미 검색(국보 필터) + 관련 국보 → 병합·중복 제거, Top-k 설정 | 사이드바 "검색 설정" | `rag/retriever.py` |
| F2007 | LangGraph `retrieve → generate`, 근거만 사용, 출처 유형 구분, 없으면 "확인되지 않습니다" | — | `rag/graph.py`, `rag/prompts.py` |
| F2008 | `[근거 N]` 표기, 인용된 근거만 제목·원문 링크와 표시, 인용 0건 안내 | 답변 아래 근거 목록 | `rag/citations.py`, `app.py` |
| F2009 | 국보 선택 + 채팅, **국보별 대화 기록 분리**. 목록은 옛 지정번호 순(`001 · 서울 숭례문`), 분류·시대 필터, 번호 검색(`1`, `78호`), 선택한 국보의 사진·기본 정보 | 사이드바 선택 · 💬 탭 | `app.py`, `data_prep/items.py` |
| F2010 | 특화 기능: **관람 해설 카드**, **통설 판정**(사실/일부 사실/사실과 다름/문서로 확인 불가) — 둘 다 근거 표시 | 🧭 탭 | `rag/prompts.py`, `services/assistant.py` |
| F2011 | 자연어 조건 → 메타 검색 후보 → LLM이 조건 대조 → 맞는 국보만 카드 → 누르면 그 국보로 | 🔎 탭 | `services/explore.py` |
| F2012 | 수집·생성 진행 상태(끝나면 수집 문서 제목), 색인 없음·키 누락 안내 | 상태 표시줄, 안내 문구 | `app.py`, `core/errors.py` |
| **F2013** | HTML/CSS/JS 화면 + FastAPI 서버 분리, 요청·응답 형식 정의 | http://localhost:8000 | `frontend/`, `api/` |
| **F2014** | MMR 검색 (`fetch_k`개 후보 → 다양성으로 `top_k`개), 유사도와 비교 | 사이드바 "검색 방식" | `vectorstore/store.py`, `scripts/compare_search.py` |
| **F2015** | RAG 사용 전후 비교 문서 자동 생성 | — | `scripts/compare_rag.py` → `docs/rag_comparison.md` |
| **F2016** | 위키백과 + 국가유산청 설명 함께 색인, 출처 종류 배지, 출처별 청킹 | 근거 배지 📖 / 🏛️ | `vectorstore/chunking.py` |

비기능: 응답 시간 표시·로그(NF2001) · 수집 캐시 `data/wiki_manifest.json` — 처리한 검색어와 '질문 → 검색어'를 기억해 같은 질문은 프롬프트 1도 다시 부르지 않음(NF2002) · `.env`(NF2003) ·
화면엔 안내 문구만, 상세는 `data/logs/app.log`(NF2004) · 모듈 분리(NF2005) ·
User-Agent 연락처·재시도·호출 간격(NF2006, `data_prep/http_client.py`) · 출처·이용 조건 기록(NF2007, 아래 6절)

---

## 4. 데이터 준비 · 색인 흐름

```
[1회] collect_items.py
  국가유산청 목록(국보) ─▶ 상세 ─┬─▶ data/items.json ──index_items.py──▶ heritage_items  (RAG 1, 국보 1건 = 청크 1개)
                                 └─▶ data/official/ ──index_official.py─▶ heritage_docs   (출처: 국가유산청)

[질문마다] (처음 들어온 검색어만 수집)
  국보 + 질문 ─▶ 프롬프트 1(검색어) ─▶ 위키 검색(제목·요약) ─▶ 프롬프트 2(선별) ─▶ 본문 수집 ─▶ 청킹 ─▶ heritage_docs (출처: 위키백과)
                                                                              └▶ data/wiki/ (원문 보관, 위키 차단 시 대체용)
  LangGraph: retrieve(메타 1 + 외부 문서 top_k + 관련 국보) ─▶ generate(프롬프트 3) ─▶ 인용된 근거만 표시
```

| 컬렉션 | 내용 | 청크 ID | 메타데이터 |
|---|---|---|---|
| `heritage_items` | 국보 메타데이터 (이름·한자·지정·분류·시대·소재지·수량·지정일·소유·개요) | 국보 ID | item_id, title, url, source_type, era, sido, category |
| `heritage_docs` | 위키백과 문서 + 국가유산청 설명 청크 | `국보ID:문서ID:순번` | item_id, related_item, title, url, page_id, source_type, search_query, collected_at, chunk_index |

---

## 5. 설정 (`config.yaml`)

| 키 | 기본값 | 의미 |
|---|---|---|
| `chunking.wiki` | 1000 / 200 | 위키백과 청크 크기 / 중복 길이 (서술형 긴 문서) |
| `chunking.official` | 800 / 100 | 국가유산청 설명 청크 (짧고 정제된 문서 → 대부분 1~2청크) |
| `retrieval.top_k` | 5 | 외부 문서 근거 수 (선택 국보 메타 1건은 별도로 항상 포함) |
| `retrieval.related_items_k` | 2 | 함께 볼 관련 국보 메타 수 (비교 질문 대비, 0이면 끔) |
| `retrieval.search_type` | similarity | `similarity` 또는 `mmr` |
| `retrieval.mmr_fetch_k` / `mmr_lambda` | 30 / 0.5 | MMR 후보 수 / 관련성↔다양성 |
| `collection.max_queries` / `search_limit` / `max_selected` / `min_doc_chars` | 4 / 5 / 5 / 300 | 수집 범위 |

청킹 값을 바꾼 뒤에는 `python scripts/rechunk.py`로 다시 색인합니다 (`--dry-run`이면 청크 수만 비교).

---

### 목록 · 사진 · 번호에 대해
- **옛 지정번호**: 국보 지정번호 표기는 2021-11-19 폐지됐습니다. 국가유산청 데이터의 지정번호 칸(`ccbaAsno`, 예 `00010000`) 앞 4자리로
  '옛 지정번호 제1호'를 표시하고 정렬합니다. 2021-11-19 이후 지정된 국보는 '관리번호'로만 표시합니다.
  `collect_items.py`가 끝날 때 "번호 순 앞 3건"을 찍으니 **숭례문이 제1호로 나오는지** 확인하세요.
- **분류·시대**: 분류는 국가유산청 대분류(유적건조물·유물·기록유산 …), 시대는 시대 문자열에서 묶은 값(선사·삼국·통일신라·발해·고려·조선·근현대)입니다.
- **사진**: 국가유산청 상세 데이터의 대표 사진 주소를 그대로 보여 주며 "사진: 국가유산청"을 표시합니다. 사진을 못 불러오면 감춥니다.
- **사진 배경**: 국보를 고르면 그 사진이 화면 배경으로 깔리고, 본문은 반투명 카드 위에 보입니다. 사이드바의 "국보 사진을 배경으로"로 끌 수 있습니다.
  따옴표·괄호·공백이 든 주소는 화면 스타일에 넣지 않습니다(`data_prep/domain.py` `safe_url`).
- **관련 링크** (답변의 근거 아님): 국가유산포털 · 위키백과 · 유튜브 검색 · 네이버 검색, 좌표가 있으면 카카오맵 위치 · 길찾기.
  유튜브는 API 키 없이 검색 결과 페이지로 연결합니다(`data_prep/domain.py` `related_links`).
- 이전 버전으로 이미 색인했다면 `python scripts/index_items.py`를 한 번 더 실행하세요 (색인 텍스트에 번호가 추가됨, 다시 수집할 필요 없음).

## 6. 사용한 데이터 · 문서의 출처와 이용 조건 (NF2007)

| 출처 | 쓰는 곳 | 이용 조건 |
|---|---|---|
| 국가유산청 국가유산 검색 오픈API (`www.khs.go.kr/cha/SearchKindOpenapiList.do`, `SearchKindOpenapiDt.do`, 종목코드 11 = 국보) | 국보 메타데이터, 공식 설명문, 대표 사진 주소 | 키 없이 공개. 국가유산청 누리집 저작권 정책을 따르며 출처를 표시함. **제출 전 국가유산청 오픈API 안내 페이지의 공공누리 유형을 확인해 이 칸에 적을 것** |
| 한국어 위키백과 (MediaWiki API `ko.wikipedia.org/w/api.php`) | 외부 문서 (RAG 2) | CC BY-SA 4.0 — 근거마다 문서 제목과 원문 링크를 표시. User-Agent에 연락처 포함, 호출 간격·재시도 준수 |
| SSAFY GMS (OpenAI 호환) | LLM · 임베딩 | 교육 과정 이용 조건에 따름. 키는 `.env`로만 관리 |

기록·수치는 **수집 시점 기준**이며, 화면의 원문 링크에서 최신 정보를 확인할 수 있습니다.
2021-11-19부터 국가유산 지정번호 표기가 폐지되어, 항목 ID는 번호가 아닌 국가유산청 API 키값(`kh_종목_지정번호_시도`)으로 고정했습니다.

---

## 7. 검증용 명령 (셀프·상호 체크리스트 대응)

| 체크리스트 | 명령 / 방법 |
|---|---|
| 1 F2001 | `python scripts/index_items.py --show 3` → 로드 건수 = 색인 건수, 색인 텍스트 출력 |
| 2 F2002 | `python scripts/index_items.py`를 두 번 → 청크 수 그대로 |
| 3 F2003·F2004 | `python scripts/check_pipeline.py --item 숭례문 --question "2008년 화재 뒤 원형과 달라진 부분은?"` → 검색어, ✓색인/✗버림 목록 |
| 4 NF2002 | 위 명령을 한 번 더 → "다시 수집하지 않았습니다", 수집 시간 0초대 |
| 5 F2005 | `python scripts/rechunk.py --dry-run` vs `--dry-run --chunk-size 500 --overlap 100` → 청크 수 변화. 실제 반영은 config 수정 후 `python scripts/rechunk.py` |
| 6 F2006 | `check_pipeline.py ... --top-k 3` vs `--top-k 8` → 근거 목록 비교 (화면: 사이드바 Top-k) |
| 7 F2007 | `python scripts/check_pipeline.py --graph` → `retrieve → generate` |
| 8 F2008 | 답변의 `[근거 N]`과 근거 목록 대조 (`check_pipeline.py`의 "인용 대조 일치: ✓"), 배지로 출처 구분 |
| 9 | 문서에 없는 것 질문(예: "복원 공사 목수의 하루 품삯은?") → "확인되지 않습니다", "인용된 근거가 없습니다" |
| 10 F2009 | 국보 A에서 대화 → B로 바꾸면 빈 대화 → A로 돌아오면 그대로 |
| 11 F2011 | 🔎 탭에서 "통일신라 시대에 만든 경주의 석탑" → 카드 하나씩 시대·지역 대조 |
| 12 F2010 | 🧭 탭 관람 해설 카드 / 통설 판정 → 근거 목록 표시 |
| 13 F2012 | 질문 중 상태 표시줄 / `python scripts/reset_index.py --yes` 후 실행 → 색인 없음 안내 / `.env`의 GMS_KEY 비우고 실행 → 키 안내 |
| 15 F2013 | `uvicorn api.server:app --port 8000` |
| 16 F2014 | `python scripts/compare_search.py --item 숭례문 --question "화재 뒤 복원"` → `docs/search_comparison.md` |
| 17·18 F2015 | `python scripts/compare_rag.py` → `docs/rag_comparison.md` (사실 정확성 칸은 직접 기입) |
| 19 F2016 | 근거 배지 📖 위키백과 / 🏛️ 국가유산청 |
| 20 NF2001 | 답변 아래 "⏱ 전체 n초 (문서 수집 m초)" — 첫 질문과 두 번째 질문 비교 |
| 21 NF2003·NF2004 | 저장소에서 키 문자열 검색, `.env`는 `.gitignore`. 오류 시 화면엔 안내만, 상세는 `data/logs/app.log` |
| 22 NF2005 | 아래 8절 폴더 구조 |
| 23 NF2006 | `data_prep/http_client.py` (User-Agent, 재시도, 간격) |

---

## 8. 프로젝트 구조 (NF2005 — 책임별 모듈 분리)

```
config.yaml                 청킹·검색·수집 설정
.env.example                GMS_KEY, WIKI_CONTACT
app.py                      [UI] Streamlit 화면
api/  server.py schemas.py  [UI·심화] FastAPI 서버, 요청·응답 형식
frontend/                   [UI·심화] HTML · CSS · JS
core/                       설정, LLM·임베딩 클라이언트, 오류 안내·로그
data_prep/                  [데이터 준비 — 도메인에 묶인 부분은 모두 여기]
  domain.py                 도메인 상수, 색인 텍스트 구성
  khs_api.py wiki_api.py    외부 API 클라이언트
  http_client.py            호출 예절 (User-Agent·재시도·간격)
  collect_items.py          국보 수집
  collector.py              외부 문서 수집 (프롬프트 1·2, 캐시)
  docs_store.py items.py    수집 이력·문서 파일, 항목 로드
vectorstore/                [색인] 컬렉션, 청킹
rag/                        [검색·생성] 프롬프트 3종, retriever, LangGraph, 인용 해석
services/                   [서비스] 질의응답·특화 기능, 조건 탐색, 비교
scripts/                    수집·색인·점검·비교 스크립트
tests/                      오프라인 테스트 50개
data/                       (실행 중 생성) items.json, official/, wiki/, chroma/, logs/
```

---

## 9. 문제 해결

| 증상 | 해결 |
|---|---|
| 화면에 "GMS_KEY가 설정되지 않았습니다" | `.env`가 프로젝트 폴더에 있는지, `GMS_KEY=` 뒤에 값이 있는지 확인 후 다시 실행 |
| "색인이 비어 있습니다" | `collect_items.py` → `index_items.py` → `index_official.py` 순서로 실행 |
| `collect_items.py`가 "위키 분류로 대체" | 국가유산청 접속 차단 → 핫스팟으로 다시 실행 (대체 모드는 시대·소재지가 비어 있음) |
| 위키 429 / 느림 | `.env`에 `WIKI_CONTACT`(영문 이메일) 넣기 |
| 답변이 늘 "확인되지 않습니다" | 그 국보의 위키 문서가 없을 수 있음 → "문서 수집 과정"에서 색인된 문서 확인, `top_k`를 늘려 보기 |
| 오류 원인을 보고 싶을 때 | `data/logs/app.log` (화면에는 일부러 보이지 않음) |
