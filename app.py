"""국보 입문 가이드 — Streamlit 화면.

실행:
    streamlit run app.py

화면 구성
    사이드바   국보 선택(F2009) · 색인 현황(F2002) · 검색 설정(Top-k, 유사도/MMR — F2006, F2014)
    탭 1      질의응답 — 국보별로 대화 기록 분리(F2009), 진행 상태(F2012), 인용된 근거만 표시(F2008)
    탭 2      관람 해설 카드 · 통설 판정 (F2010)
    탭 3      조건으로 찾기 — 자연어 조건 → 맞는 국보 카드 → 누르면 그 국보로 이동 (F2011)

화면에는 안내 문구만 보이고 오류 상세·프롬프트·키는 보이지 않는다 (NF2004). 상세는 data/logs/app.log.
"""

from __future__ import annotations

import streamlit as st

from core.config import get_settings
from core.errors import AppError, IndexEmptyError, MissingKeyError, friendly_message, get_logger
from core.llm import has_api_key
from data_prep.domain import (
    DISCLAIMER, DOMAIN, EXAMPLE_CLAIMS, EXAMPLE_CONDITIONS, EXAMPLE_QUESTIONS, ICON, RISKY_DOMAIN,
    SERVICE_TAGLINE, SERVICE_TITLE, SOURCE_ITEM, SOURCE_OFFICIAL, SOURCE_WIKI, item_label, main_category,
    order_note, related_links, safe_url,
)
from data_prep.items import ALL, get_catalog
from services.assistant import ask
from services.explore import explore
from vectorstore.store import raw_counts

log = get_logger("heritage_rag.app")
settings = get_settings()
RCFG = settings.section("retrieval")

SOURCE_BADGE = {SOURCE_ITEM: "🏷️ 국보 메타데이터", SOURCE_WIKI: "📖 위키백과", SOURCE_OFFICIAL: "🏛️ 국가유산청"}
JUDGMENT_STYLE = {"사실": ("green", "✅"), "일부 사실": ("orange", "🟠"), "사실과 다름": ("red", "❌"),
                  "문서로 확인 불가": ("gray", "❔")}

st.set_page_config(page_title=SERVICE_TITLE, page_icon=ICON, layout="wide")

# ── 세션 상태 ───────────────────────────────────────────────
ss = st.session_state
ss.setdefault("histories", {})   # 국보 ID → 메시지 목록 (국보마다 따로 — F2009)
ss.setdefault("features", {})    # 국보 ID → {"guide": ..., "factchecks": [...]}
ss.setdefault("explore", None)   # 마지막 조건 탐색 결과
ss.setdefault("pending_q", None)
ss.setdefault("flash", "")
ss.setdefault("item_id", None)   # 국보 선택 위젯 값 (조건 탐색 카드에서도 바꾼다)
ss.setdefault("item_cat", ALL)   # 분류 필터
ss.setdefault("item_era", ALL)   # 시대 필터
ss.setdefault("photo_bg", True)  # 선택한 국보 사진을 배경으로


def select_item(item_id: str, name: str) -> None:
    ss["item_id"] = item_id
    ss["item_filter"] = ""
    ss["item_cat"] = ALL
    ss["item_era"] = ALL
    ss["flash"] = f"'{name}'을(를) 골랐습니다. 질의응답 탭에서 바로 질문해 보세요."


# ── 공통 렌더링 ─────────────────────────────────────────────

LINK_ICON = {"official": "🏛️", "wiki": "📖", "youtube": "▶️", "search": "🔍", "map": "📍", "route": "🧭"}


def set_background(image_url: str) -> None:
    """선택한 국보 사진을 화면 배경으로. 글자가 읽히도록 위는 옅게, 아래로 갈수록 진하게 종이색을 덮는다.

    safe_url()을 통과한 주소만 CSS에 넣는다 (따옴표·괄호가 있으면 넣지 않음).
    """
    url = safe_url(image_url)
    if not url:
        return
    st.markdown(f"""<style>
    [data-testid="stApp"] {{
      background-image:
        linear-gradient(180deg, rgba(247,243,234,.10) 0, rgba(247,243,234,.35) 45%, rgba(247,243,234,.55) 100%),
        url("{url}");
      background-size: cover; background-position: center top; background-attachment: fixed;
    }}
    [data-testid="stHeader"] {{ background: transparent; }}
    [data-testid="stSidebar"] {{ background: rgba(239,232,216,.82); backdrop-filter: blur(10px); }}
    [data-testid="stMainBlockContainer"] {{ background: rgba(255,253,248,.70); backdrop-filter: blur(12px);
      border-radius: 18px; margin-top: 2.5rem; margin-bottom: 2rem; padding-top: 2rem;
      box-shadow: 0 4px 24px rgba(31,42,46,.10); }}
    [data-testid="stBottomBlockContainer"] {{ background: transparent; }}
    </style>""", unsafe_allow_html=True)


def render_links(item: dict) -> None:
    """관련 링크 — 답변 근거가 아닌 바로가기."""
    links = related_links(item)
    if not links:
        return
    st.markdown("**관련 링크** " + "  ·  ".join(f"{LINK_ICON.get(l['kind'], '🔗')} [{l['label']}]({l['url']})" for l in links))
    st.caption("유튜브·네이버는 검색 결과로 연결됩니다. 관련 링크는 답변의 근거가 아닙니다.")


def render_item_header(item: dict) -> None:
    """선택한 국보의 사진과 기본 정보·관련 링크 — 모든 탭 위에 보인다."""
    img = safe_url(item.get("image_url", ""))
    left, right = st.columns([1, 2]) if img else (None, st.container())
    if img:
        with left:
            st.image(img, caption="사진: 국가유산청", width="stretch")
    with right:
        title = item["name"] + (f"  ({item['name_hanja']})" if item.get("name_hanja") else "")
        st.subheader(title)
        if order_note(item):
            st.caption(order_note(item))
        cat = " > ".join(item.get("category") or []) or main_category(item)
        region = " ".join(x for x in (item.get("sido", ""), item.get("sigungu", "")) if x)
        rows = [("분류", cat), ("시대", item.get("era", "")), ("소재지", region + (f" ({item['address']})" if item.get("address") else "")),
                ("지정일", item.get("designated_date", "")), ("소유·관리", " / ".join(x for x in (item.get("owner", ""), item.get("manager", "")) if x))]
        st.markdown("  \n".join(f"**{k}** {v}" for k, v in rows if v))
        render_links(item)


def render_sources(cited: list[dict], evidence_count: int) -> None:
    """답변이 실제로 인용한 근거만 보여 준다. 인용이 없으면 그 사실을 안내한다 (F2008)."""
    if not cited:
        st.caption(f"ⓘ 답변에 인용된 근거가 없습니다. (검색된 근거 {evidence_count}건 중 인용 0건)")
        return
    with st.expander(f"답변에 사용한 근거 {len(cited)}건  ·  검색된 근거 {evidence_count}건", expanded=True):
        for e in cited:
            badge = SOURCE_BADGE.get(e["source_type"], e["source_type"])
            link = f" · [원문]({e['url']})" if e.get("url") else ""
            st.markdown(f"**[근거 {e['number']}]** {badge} · {e['title']}{link}")
            snippet = e["text"].split("\n", 1)[-1].replace("\n", " ")
            st.caption(snippet[:160] + ("…" if len(snippet) > 160 else ""))


def render_collection(col: dict | None) -> None:
    """프롬프트 1이 고른 검색어, 프롬프트 2가 고르고 버린 문서 (F2003, F2004 확인용)."""
    if not col:
        return
    head = "이미 수집한 검색어 — 다시 수집하지 않음" if col["from_cache"] else f"이번에 색인한 문서 {len(col['indexed_titles'])}건"
    with st.expander(f"문서 수집 과정 · {head}"):
        st.markdown("**검색어 (프롬프트 1)** " + " · ".join(f"`{q}`" for q in col["queries"]))
        if col["from_cache"]:
            st.caption("모든 검색어를 이미 처리했습니다. 색인된 문서에서 바로 근거를 찾았습니다.")
        if col["kept"]:
            st.markdown("**색인한 문서** " + " · ".join(
                f"{k['title']}{' (국보 자체 문서)' if k['decision'] == 'own' else ''}" for k in col["kept"]))
        if col["dropped"]:
            st.markdown("**버린 문서 (프롬프트 2·길이 기준)** " + " · ".join(
                f"{d['title']} ({d['note'] or d['decision']})" for d in col["dropped"]))
        if col.get("offline"):
            st.caption(col.get("message", ""))


def render_timing(msg: dict) -> None:
    col = msg.get("collection") or {}
    st.caption(f"⏱ 전체 {msg.get('elapsed', 0):.1f}초 (문서 수집 {col.get('elapsed', 0):.1f}초)")


def render_answer(msg: dict) -> None:
    if msg.get("judgment"):
        color, icon = JUDGMENT_STYLE.get(msg["judgment"], ("gray", "❔"))
        st.markdown(f"### {icon} :{color}[{msg['judgment']}]")
    st.markdown(msg["content"])
    if msg.get("notice"):
        st.info(msg["notice"])
    if RISKY_DOMAIN and DISCLAIMER:
        st.info(DISCLAIMER)
    render_sources(msg.get("cited", []), msg.get("evidence_count", 0))
    render_collection(msg.get("collection"))
    render_timing(msg)


def run_ask(item_id: str, question: str, mode: str, history: list[dict]) -> dict | None:
    """진행 상태를 보여 주며 ask()를 호출하고, 화면에 다시 그릴 수 있는 dict로 돌려준다."""
    try:
        with st.status("관련 문서를 확인하는 중…", expanded=False) as status:
            res = ask(item_id, question, mode, history, ss.get("top_k"), ss.get("search_type"),
                      progress=lambda m: status.update(label=m + "…"))
            col = res.collection
            if col and col.from_cache:
                label = "이미 수집한 문서로 답변했습니다"
            elif col and col.indexed_titles:
                label = "수집한 문서: " + ", ".join(col.indexed_titles[:5])
            else:
                label = "답변을 만들었습니다"
            status.update(label=label, state="complete")
    except AppError as e:
        st.warning(e.message)
        return None
    except Exception as e:  # 오류 상세는 로그에만
        log.exception("질의 처리 실패")
        st.error(friendly_message(e))
        return None
    d = res.to_dict()
    return {"role": "assistant", "content": d["answer"], "cited": d["cited"], "evidence_count": len(d["evidence"]),
            "judgment": d["judgment"], "collection": d["collection"], "elapsed": d["elapsed"], "notice": res.notice,
            "question": res.question}


# ── 준비 상태 확인 (F2012) ──────────────────────────────────
counts = raw_counts()
st.title(f"{ICON} {SERVICE_TITLE}")
st.caption(SERVICE_TAGLINE)

try:
    catalog = get_catalog()
except IndexEmptyError as e:
    st.warning(e.message)
    st.stop()

with st.sidebar:
    st.header(f"{DOMAIN} 선택")
    facets = catalog.facets()
    cat_n, era_n = dict(facets["categories"]), dict(facets["eras"])
    if ss.item_cat not in cat_n and ss.item_cat != ALL:
        ss.item_cat = ALL
    if ss.item_era not in era_n and ss.item_era != ALL:
        ss.item_era = ALL
    f1, f2 = st.columns(2)
    f1.selectbox("분류", [ALL] + list(cat_n), key="item_cat",
                 format_func=lambda c: f"{c} ({len(catalog) if c == ALL else cat_n[c]})")
    f2.selectbox("시대", [ALL] + list(era_n), key="item_era",
                 format_func=lambda e: f"{e} ({len(catalog) if e == ALL else era_n[e]})")
    flt = st.text_input("이름·번호·지역으로 거르기", key="item_filter", placeholder="예: 1, 78호, 경주, 탑")
    options = [it["heritage_id"] for it in catalog.filter(flt, ss.item_cat, ss.item_era)]
    current = ss.get("item_id")
    if current and current not in options and current in catalog.by_id:
        options = [current] + options
    st.selectbox(f"질문할 {DOMAIN} — 옛 지정번호 순 ({len(options)}건)", options, key="item_id",
                 format_func=lambda i: item_label(catalog.by_id[i]), placeholder=f"{DOMAIN}을 고르세요")

    st.divider()
    st.subheader("색인 현황")
    c1, c2 = st.columns(2)
    c1.metric("국보 메타데이터", f"{counts['items']}건")
    c2.metric("외부 문서 청크", f"{counts['docs']}개")
    if counts["items"] and counts["items"] != len(catalog):
        st.caption(f"⚠ 목록 {len(catalog)}건과 색인 {counts['items']}건이 다릅니다. index_items.py를 다시 실행하세요.")

    with st.expander("검색 설정"):
        st.slider("외부 문서 근거 수 (Top-k)", 1, 15, int(RCFG.get("top_k", 5)), key="top_k")
        st.radio("검색 방식", ["similarity", "mmr"], key="search_type", horizontal=True,
                 index=0 if RCFG.get("search_type", "similarity") == "similarity" else 1,
                 format_func=lambda x: "유사도" if x == "similarity" else "MMR (다양성)")
        st.caption("기본값은 config.yaml의 retrieval 에서 바꿉니다.")

    st.toggle("국보 사진을 배경으로", key="photo_bg")
    if ss.get("item_id") and st.button("이 국보의 대화 지우기", width="stretch"):
        ss.histories.pop(ss["item_id"], None)
        ss.features.pop(ss["item_id"], None)

    st.divider()
    st.caption("자료: 국가유산청 국가유산 검색 오픈API · 한국어 위키백과(CC BY-SA 4.0). "
               "기록은 수집 시점 기준이며 원문 링크에서 확인할 수 있습니다.")

if not has_api_key():
    st.error(MissingKeyError().message)
    st.stop()
if counts["items"] == 0:
    st.warning(IndexEmptyError().message)
    st.stop()

if ss.flash:
    st.success(ss.flash)
    ss.flash = ""

item_id = ss.get("item_id")
item = catalog.by_id.get(item_id) if item_id else None
if item:
    if ss.photo_bg:
        set_background(item.get("image_url", ""))
    render_item_header(item)
tab_qa, tab_feature, tab_explore = st.tabs(["💬 질의응답", "🧭 관람 해설 · 통설 판정", "🔎 조건으로 찾기"])

# ── 탭 1: 질의응답 ──────────────────────────────────────────
with tab_qa:
    if not item:
        st.info(f"왼쪽에서 {DOMAIN}을 고르거나, '조건으로 찾기' 탭에서 찾아보세요.")
    else:
        history = ss.histories.setdefault(item_id, [])

        if not history:
            st.caption("이렇게 물어볼 수 있어요")
            cols = st.columns(len(EXAMPLE_QUESTIONS))
            for col, q in zip(cols, EXAMPLE_QUESTIONS):
                if col.button(q, key=f"ex_{item_id}_{q}", width="stretch"):
                    ss.pending_q = q

        for m in history:
            with st.chat_message(m["role"]):
                if m["role"] == "user":
                    st.markdown(m["content"])
                else:
                    render_answer(m)

        typed = st.chat_input(f"{item['name']}에 대해 궁금한 점을 물어보세요", key=f"chat_{item_id}")
        question = typed or ss.pending_q
        ss.pending_q = None
        if question:
            prev = [{"role": m["role"], "content": m["content"]} for m in history]
            history.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                msg = run_ask(item_id, question, "qa", prev)
                if msg:
                    render_answer(msg)
                    history.append(msg)
                else:
                    history.pop()  # 실패한 질문은 기록에 남기지 않는다

# ── 탭 2: 관람 해설 · 통설 판정 (F2010) ─────────────────────
with tab_feature:
    if not item:
        st.info(f"왼쪽에서 {DOMAIN}을 먼저 고르세요.")
    else:
        feat = ss.features.setdefault(item_id, {"guide": None, "factchecks": []})
        left, right = st.columns(2, gap="large")
        with left:
            st.subheader("관람 해설 카드")
            st.caption("현장에 가기 전에 볼 내용을 근거와 함께 정리합니다.")
            if st.button("관람 해설 카드 만들기", key=f"guide_{item_id}", type="primary"):
                msg = run_ask(item_id, "", "guide", [])
                if msg:
                    feat["guide"] = msg
            if feat["guide"]:
                with st.container(border=True):
                    render_answer(feat["guide"])
        with right:
            st.subheader("통설 판정")
            st.caption("들은 이야기가 맞는지 문서로 확인합니다.")
            with st.form(key=f"fc_form_{item_id}", clear_on_submit=True):
                claim = st.text_input("들은 이야기", placeholder=EXAMPLE_CLAIMS[0])
                submitted = st.form_submit_button("판정하기")
            if submitted:
                msg = run_ask(item_id, claim, "factcheck", [])
                if msg:
                    feat["factchecks"].insert(0, msg)
            for m in feat["factchecks"]:
                with st.container(border=True):
                    st.markdown(f"**주장** {m['question']}")
                    render_answer(m)

# ── 탭 3: 조건으로 찾기 (F2011) ──────────────────────────────
with tab_explore:
    st.subheader("조건으로 국보 찾기")
    st.caption("예: " + " / ".join(EXAMPLE_CONDITIONS))
    with st.form(key="explore_form"):
        cond = st.text_input("찾고 싶은 조건", placeholder=EXAMPLE_CONDITIONS[0])
        go = st.form_submit_button("찾기")
    if go:
        try:
            with st.spinner("후보를 찾고 조건과 맞는지 확인하는 중…"):
                hits, n = explore(cond)
            ss.explore = {"condition": cond, "hits": [h.to_dict() for h in hits], "searched": n}
        except AppError as e:
            st.warning(e.message)
        except Exception as e:
            log.exception("조건 탐색 실패")
            st.error(friendly_message(e))
    res = ss.explore
    if res:
        if not res["hits"]:
            st.info(f"'{res['condition']}' 조건에 맞는 {DOMAIN}을 찾지 못했습니다. (후보 {res['searched']}건 확인) 조건을 바꿔 보세요.")
        else:
            st.markdown(f"**'{res['condition']}'** — 후보 {res['searched']}건 중 조건에 맞는 {len(res['hits'])}건")
            cols = st.columns(3)
            for i, h in enumerate(res["hits"]):
                with cols[i % 3].container(border=True):
                    if safe_url(h.get("image_url", "")):
                        st.image(h["image_url"], width="stretch")
                    st.markdown(f"**{h['name']}**" + (f"  `{h['order_label']}`" if h.get("order_label") else ""))
                    st.caption(" · ".join(x for x in (h.get("category", ""), h["era"], h["region"]) if x))
                    st.write(h["reason"])
                    st.button("이 국보에 대해 묻기", key=f"pick_{h['item_id']}", on_click=select_item,
                              args=(h["item_id"], h["name"]), width="stretch")
