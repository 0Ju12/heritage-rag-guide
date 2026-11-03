// 국보 입문 가이드 — 화면 스크립트 (F2013)
// 서버(api/server.py)와는 /api/* JSON 요청·응답으로만 주고받는다.

const $ = (sel) => document.querySelector(sel);
const state = {
  items: [],
  selected: null,
  histories: new Map(),  // 국보 ID → [{role, content, resp?}]  (국보마다 따로 — F2009)
  guides: new Map(),     // 국보 ID → 응답
  facts: new Map(),      // 국보 ID → [{claim, resp}]
  busy: false,
  ready: false,
  examples: { questions: [], claims: [], conditions: [] },
};

const SOURCE_CLASS = { "국보 메타데이터": "meta", "위키백과": "wiki", "국가유산청": "official" };
const JUDGMENT_CLASS = { "사실": "j-사실", "일부 사실": "j-일부", "사실과 다름": "j-다름", "문서로 확인 불가": "j-불가" };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// http(s)이고 따옴표·괄호·공백이 없을 때만 — CSS url()과 속성에 넣어도 안전하게 (서버 safe_url과 같은 규칙)
function safeUrl(u) {
  return /^https?:\/\/[^\s"'()<>\\]+$/i.test(u || "") ? u : "";
}

const LINK_ICON = { official: "🏛️", wiki: "📖", youtube: "▶️", search: "🔍", map: "📍", route: "🧭" };

// 선택한 국보 사진을 배경으로 (끄기 가능, 사진 없으면 원래 배경)
function setBackground(it) {
  const bg = $("#bg");
  const url = it && $("#bg-toggle").checked ? safeUrl(it.image_url) : "";
  document.body.classList.toggle("has-bg", !!url);
  if (!url) { bg.classList.remove("on"); bg.style.backgroundImage = ""; return; }
  bg.style.backgroundImage =
    `linear-gradient(180deg, rgba(247,243,234,.10) 0, rgba(247,243,234,.35) 45%, rgba(247,243,234,.55) 100%), url("${url}")`;
  bg.classList.add("on");
}

// 답변 텍스트 → 안전한 HTML (소제목, 굵게, 글머리표, [근거 N] 강조)
function formatAnswer(text) {
  let h = esc(text);
  h = h.replace(/^#{2,4}\s*(.+)$/gm, "<h4>$1</h4>");
  h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  h = h.replace(/^\s*[-•*]\s+(.+)$/gm, "<li>$1</li>");
  h = h.replace(/(?:<li>.*<\/li>\n?)+/g, (m) => `<ul>${m.replace(/\n/g, "")}</ul>`);
  h = h.replace(/\[근거\s*([\d,\s·~\-–]+)\]/g, '<span class="cite">[근거 $1]</span>');
  h = h.replace(/(<\/h4>|<\/ul>)\n/g, "$1").replace(/\n/g, "<br>");
  return h;
}

async function api(path, body) {
  const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new Error("서버에 연결하지 못했습니다. 서버가 실행 중인지 확인해 주세요.");
  }
  let data = null;
  try { data = await res.json(); } catch { /* 본문 없음 */ }
  if (!res.ok) throw new Error((data && data.detail) || "처리 중 문제가 생겼습니다.");
  return data;
}

// ── 진행 상태 (F2012) ──────────────────────────────────────
let statusTimers = [];
function showStatus(steps) {
  const box = $("#status");
  box.classList.remove("hidden");
  $("#status-text").textContent = steps[0];
  statusTimers = steps.slice(1).map((s, i) => setTimeout(() => ($("#status-text").textContent = s), (i + 1) * 2500));
}
function hideStatus() {
  statusTimers.forEach(clearTimeout);
  $("#status").classList.add("hidden");
}
function setBusy(b) {
  state.busy = b;
  document.querySelectorAll("button.primary").forEach((btn) => (btn.disabled = b));
}
const STEPS = ["검색어를 고르는 중…", "위키백과에서 관련 문서를 찾는 중…", "문서를 고르고 색인하는 중…", "근거를 찾고 답변을 만드는 중…"];

function showBanner(msg) {
  const b = $("#banner");
  if (!msg) { b.classList.add("hidden"); return; }
  b.textContent = msg;
  b.classList.remove("hidden");
}

// ── 응답 렌더링 (F2007, F2008) ─────────────────────────────
function renderSources(resp) {
  if (!resp.sources.length) {
    return `<p class="notice">ⓘ ${esc(resp.no_citation_notice || "답변에 인용된 근거가 없습니다.")} (검색된 근거 ${resp.evidence_count}건)</p>`;
  }
  const rows = resp.sources.map((s) => {
    const cls = SOURCE_CLASS[s.source_type] || "meta";
    const url = safeUrl(s.url);
    const link = url ? ` · <a href="${esc(url)}" target="_blank" rel="noopener">원문</a>` : "";
    return `<div class="source"><span class="num">[근거 ${s.number}]</span>
      <span><span class="badge ${cls}">${esc(s.source_type)}</span>${esc(s.title)}${link}</span>
      <span class="excerpt">${esc(s.excerpt.slice(0, 160))}${s.excerpt.length > 160 ? "…" : ""}</span></div>`;
  }).join("");
  return `<div class="sources"><h5>답변에 사용한 근거 ${resp.sources.length}건 · 검색된 근거 ${resp.evidence_count}건</h5>${rows}</div>`;
}

function renderCollection(col) {
  if (!col) return "";
  const head = col.from_cache ? "이미 수집한 검색어 — 다시 수집하지 않음" : `이번에 색인한 문서 ${col.indexed_titles.length}건`;
  const kept = col.kept.map((k) => esc(k.title) + (k.decision === "own" ? " (국보 자체 문서)" : "")).join(" · ");
  const dropped = col.dropped.map((d) => `${esc(d.title)} (${esc(d.note || d.decision)})`).join(" · ");
  return `<details class="process"><summary>문서 수집 과정 · ${head}</summary>
    <div>검색어(프롬프트 1): ${col.queries.map((q) => `<code>${esc(q)}</code>`).join(" ")}</div>
    ${kept ? `<div>색인한 문서: ${kept}</div>` : ""}
    ${dropped ? `<div>버린 문서: ${dropped}</div>` : ""}
    ${col.offline ? `<div>${esc(col.message)}</div>` : ""}
  </details>`;
}

function renderResponse(resp) {
  const j = resp.judgment ? `<div class="judgment ${JUDGMENT_CLASS[resp.judgment] || "j-불가"}">${esc(resp.judgment)}</div>` : "";
  const notice = resp.notice ? `<p class="notice">${esc(resp.notice)}</p>` : "";
  const disc = resp.disclaimer ? `<p class="notice">${esc(resp.disclaimer)}</p>` : "";
  const col = resp.collection;
  const timing = `<p class="notice">⏱ 전체 ${resp.elapsed.toFixed(1)}초${col ? ` (문서 수집 ${col.elapsed.toFixed(1)}초)` : ""}</p>`;
  return `${j}<div class="answer">${formatAnswer(resp.answer)}</div>${notice}${disc}${renderSources(resp)}${renderCollection(col)}${timing}`;
}

// ── 국보 목록 · 선택 (F2009) ──────────────────────────────
// 번호 검색: '1', '1호', '제78호', '국보 78-2호'
const NUM_RE = /^(?:국보\s*)?제?\s*(\d{1,4})\s*(?:-\s*(\d+))?\s*호?$/;

function filteredItems() {
  const q = $("#item-filter").value.trim();
  const cat = $("#cat-filter").value, era = $("#era-filter").value;
  let list = state.items;
  if (cat !== "전체") list = list.filter((it) => it.category === cat);
  if (era !== "전체") list = list.filter((it) => it.era_group === era);
  if (!q) return list;
  const m = q.match(NUM_RE);
  if (m) {
    const want = m[2] ? `${Number(m[1])}-${Number(m[2])}` : String(Number(m[1]));
    const hits = list.filter((it) => {
      const n = (it.order_label.match(/(\d+(?:-\d+)?)/) || [])[1] || "";
      return m[2] ? n === want : n.split("-")[0] === want;
    });
    if (hits.length) return hits;
  }
  return list.filter((it) => it.name.includes(q) || it.era.includes(q) || it.region.includes(q) || it.name_hanja.includes(q));
}

function numberOf(it) {
  return it.label.includes(" · ") ? it.label.split(" · ")[0] : "";
}

function renderItemList() {
  const list = filteredItems();
  $("#item-count").textContent = `${list.length}건`;
  $("#item-list").innerHTML = list.map((it) =>
    `<li data-id="${esc(it.item_id)}" class="${state.selected && state.selected.item_id === it.item_id ? "active" : ""}" role="option">
      ${numberOf(it) ? `<span class="num">${esc(numberOf(it))}</span>` : ""}${esc(it.name)}
      <small>${esc([it.category, it.era, it.region].filter(Boolean).join(" · "))}</small></li>`).join("");
}

function renderFacets(f) {
  const opt = (x) => `<option value="${esc(x.name)}">${esc(x.name)} (${x.count})</option>`;
  $("#cat-filter").innerHTML = `<option value="전체">전체 (${f.total})</option>` + f.categories.map(opt).join("");
  $("#era-filter").innerHTML = `<option value="전체">전체 (${f.total})</option>` + f.eras.map(opt).join("");
}

function renderItemHead(it) {
  $("#item-head").classList.toggle("hidden", !it);
  if (!it) return;
  $("#item-name").textContent = it.name + (it.name_hanja ? ` (${it.name_hanja})` : "");
  $("#item-order").textContent = it.order_note || "";
  const photo = $("#item-photo"), url = safeUrl(it.image_url);
  photo.classList.toggle("hidden", !url);
  const img = photo.querySelector("img");
  if (url) {
    img.src = url;
    img.alt = `${it.name} 사진`;
    img.onerror = () => photo.classList.add("hidden");   // 사진을 못 불러오면 감춘다
  } else {
    img.removeAttribute("src");
  }
  const facts = [["분류", it.category_path.join(" > ") || it.category], ["시대", it.era],
    ["소재지", it.region + (it.address ? ` (${it.address})` : "")], ["지정일", it.designated_date]];
  $("#item-facts").innerHTML = facts.filter(([, v]) => v).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
  $("#item-links").innerHTML = (it.links || []).filter((l) => safeUrl(l.url)).map((l) =>
    `<a class="link ${esc(l.kind)}" href="${esc(l.url)}" target="_blank" rel="noopener">${LINK_ICON[l.kind] || "🔗"} ${esc(l.label)}</a>`).join("");
}

function selectItem(id) {
  state.selected = state.items.find((it) => it.item_id === id) || null;
  renderItemList();
  const it = state.selected;
  renderItemHead(it);
  setBackground(it);
  document.querySelectorAll(".need-item").forEach((el) => el.classList.toggle("hidden", !!it));
  document.querySelectorAll(".has-item").forEach((el) => el.classList.toggle("hidden", !it));
  renderChat();
  renderGuide();
  renderFacts();
}

// ── 질의응답 ──────────────────────────────────────────────
function renderChat() {
  const it = state.selected;
  $("#qa-empty").classList.toggle("hidden", !!it);
  $("#chat-form").classList.toggle("hidden", !it);
  const log = $("#chat-log");
  if (!it) { log.innerHTML = ""; $("#qa-examples").classList.add("hidden"); return; }
  const hist = state.histories.get(it.item_id) || [];
  $("#qa-examples").classList.toggle("hidden", hist.length > 0);
  $("#qa-examples").innerHTML = state.examples.questions.map((q) => `<button class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("");
  log.innerHTML = hist.map((m) => m.role === "user"
    ? `<div class="msg user"><div class="label">나</div>${esc(m.content)}</div>`
    : `<div class="msg assistant"><div class="label">안내</div>${renderResponse(m.resp)}</div>`).join("");
  $("#chat-input").placeholder = `${it.name}에 대해 궁금한 점을 물어보세요`;
}

async function sendQuestion(question) {
  const it = state.selected;
  if (!it || state.busy || !question.trim()) return;
  const hist = state.histories.get(it.item_id) || [];
  const history = hist.map((m) => ({ role: m.role, content: m.content.slice(0, 4000) })).slice(-6);
  hist.push({ role: "user", content: question });
  state.histories.set(it.item_id, hist);
  renderChat();
  setBusy(true);
  showStatus(STEPS);
  try {
    const resp = await api("/api/chat", { item_id: it.item_id, question, mode: "qa", history, ...searchParams() });
    hist.push({ role: "assistant", content: resp.answer, resp });
    showBanner("");
  } catch (e) {
    hist.pop();  // 실패한 질문은 기록하지 않는다
    showBanner(e.message);
  } finally {
    hideStatus();
    setBusy(false);
    if (state.selected && state.selected.item_id === it.item_id) renderChat();
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }
}

function searchParams() {
  return { top_k: Number($("#topk").value), search_type: $("#search-type").value };
}

// ── 관람 해설 · 통설 판정 (F2010) ─────────────────────────
function renderGuide() {
  const it = state.selected;
  const resp = it && state.guides.get(it.item_id);
  $("#guide-out").innerHTML = resp ? `<div class="msg assistant result-block">${renderResponse(resp)}</div>` : "";
}

function renderFacts() {
  const it = state.selected;
  const list = (it && state.facts.get(it.item_id)) || [];
  $("#fact-out").innerHTML = list.map((f) =>
    `<div class="msg assistant result-block"><div class="label">주장: ${esc(f.claim)}</div>${renderResponse(f.resp)}</div>`).join("");
  $("#fact-input").placeholder = state.examples.claims[0] || "들은 이야기를 적어 주세요";
}

async function runFeature(mode, text) {
  const it = state.selected;
  if (!it || state.busy) return;
  setBusy(true);
  showStatus(STEPS);
  try {
    const resp = await api("/api/chat", { item_id: it.item_id, question: text || "", mode, ...searchParams() });
    if (mode === "guide") state.guides.set(it.item_id, resp);
    else {
      const list = state.facts.get(it.item_id) || [];
      list.unshift({ claim: text, resp });
      state.facts.set(it.item_id, list);
    }
    showBanner("");
  } catch (e) {
    showBanner(e.message);
  } finally {
    hideStatus();
    setBusy(false);
    renderGuide();
    renderFacts();
  }
}

// ── 조건으로 찾기 (F2011) ─────────────────────────────────
async function runExplore(condition) {
  if (state.busy || !condition.trim()) return;
  setBusy(true);
  showStatus(["후보를 찾는 중…", "조건과 맞는지 하나씩 확인하는 중…"]);
  const out = $("#explore-out");
  try {
    const data = await api("/api/explore", { condition });
    if (!data.results.length) {
      out.innerHTML = `<div class="empty">‘${esc(condition)}’ 조건에 맞는 국보를 찾지 못했습니다. (후보 ${data.searched}건 확인)</div>`;
    } else {
      out.innerHTML = `<p class="muted">‘${esc(condition)}’ — 후보 ${data.searched}건 중 조건에 맞는 ${data.results.length}건</p>
        <div class="cards">${data.results.map((r) => `<div class="card">
          ${safeUrl(r.image_url) ? `<img src="${esc(r.image_url)}" alt="${esc(r.name)} 사진" loading="lazy" onerror="this.remove()" />` : ""}
          <h4>${esc(r.name)}</h4>
          ${r.order_label ? `<span class="tag">${esc(r.order_label)}</span>` : ""}
          <span class="muted small">${esc([r.category, r.era, r.region].filter(Boolean).join(" · "))}</span>
          <span>${esc(r.reason)}</span>
          <button class="primary pick" data-id="${esc(r.item_id)}">이 국보에 대해 묻기</button></div>`).join("")}</div>`;
    }
    showBanner("");
  } catch (e) {
    showBanner(e.message);
  } finally {
    hideStatus();
    setBusy(false);
  }
}

// ── 탭 ────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== name));
}

// ── 시작 ──────────────────────────────────────────────────
async function init() {
  try {
    const h = await api("/api/health");
    $("#title").textContent = h.title;
    document.title = h.title;
    $("#tagline").textContent = h.tagline;
    state.examples = h.examples;
    state.ready = h.ready;
    $("#health").innerHTML = `
      <span class="pill ${h.has_key ? "ok" : "bad"}">${h.has_key ? "API 키 확인" : "API 키 없음"}</span>
      <span class="pill ${h.items_indexed ? "ok" : "bad"}">국보 메타데이터 ${h.items_indexed}건</span>
      <span class="pill">외부 문서 청크 ${h.docs_indexed}개</span>`;
    showBanner(h.message);
    $("#explore-examples").innerHTML = h.examples.conditions.map((c) => `<button class="chip" data-c="${esc(c)}">${esc(c)}</button>`).join("");
    if (h.items_total) {
      state.items = await api("/api/items");
      renderFacets(await api("/api/facets"));
    }
    renderItemList();
    selectItem(null);
  } catch (e) {
    showBanner(e.message);
  }
}

$("#item-filter").addEventListener("input", renderItemList);
$("#cat-filter").addEventListener("change", renderItemList);
$("#bg-toggle").addEventListener("change", () => setBackground(state.selected));
$("#era-filter").addEventListener("change", renderItemList);
$("#item-list").addEventListener("click", (e) => {
  const li = e.target.closest("li[data-id]");
  if (li) selectItem(li.dataset.id);
});
$("#topk").addEventListener("input", () => ($("#topk-val").textContent = $("#topk").value));
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#chat-input").value;
  $("#chat-input").value = "";
  sendQuestion(q);
});
$("#qa-examples").addEventListener("click", (e) => {
  const b = e.target.closest("[data-q]");
  if (b) sendQuestion(b.dataset.q);
});
$("#clear-chat").addEventListener("click", () => {
  if (state.selected) { state.histories.delete(state.selected.item_id); renderChat(); }
});
$("#guide-btn").addEventListener("click", () => runFeature("guide", ""));
$("#fact-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = $("#fact-input").value;
  if (!v.trim()) return showBanner("판정할 이야기를 입력해 주세요.");
  $("#fact-input").value = "";
  runFeature("factcheck", v);
});
$("#explore-form").addEventListener("submit", (e) => {
  e.preventDefault();
  runExplore($("#explore-input").value);
});
$("#explore-examples").addEventListener("click", (e) => {
  const b = e.target.closest("[data-c]");
  if (b) { $("#explore-input").value = b.dataset.c; runExplore(b.dataset.c); }
});
$("#explore-out").addEventListener("click", (e) => {
  const b = e.target.closest(".pick");
  if (b) { selectItem(b.dataset.id); switchTab("qa"); $("#chat-input").focus(); }
});

init();
