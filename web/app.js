"use strict";
// 혼디 화면. 서버(127.0.0.1)의 JSON API만 사용하고 외부로 아무것도 보내지 않는다.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = { recent: {}, state: null, cards: [], results: new Map(), unselected: new Set(), removing: new Set(), order: [], prepDone: false, reportDone: false, formDone: false,
  focus: { area: "", biz: "" }, focusKey: "", asked: new Set(), explore: false };  // 관심 조건은 데이터 값이라 브라우저에 저장하지 않는다

// ---------- 아이콘(인라인 SVG, 외부 파일 없음) ----------
const P = {
  log: '<path d="M4 5h16M4 10h16M4 15h10M4 20h7"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  door: '<path d="M14 3h5a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1h-5"/><path d="M10 17l5-5-5-5M15 12H3"/>',
  chev: '<path d="M6 9l6 6 6-6"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5M12 3v12"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  spark: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 17l.8 2.2L22 20l-2.2.8L19 23l-.8-2.2L16 20l2.2-.8z"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
  pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  send: '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  pc: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>',
  down: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5M12 15V3"/>',
  table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16"/>',
  map: '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  redo: '<path d="M21 4v6h-6"/><path d="M20.5 15a8.5 8.5 0 1 1-2-8.8L21 10"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5v.01"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  box: '<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.01"/>',
};
function josa(w, p) {  // 받침에 맞는 조사(서버 app/josa.py와 같은 규칙)
  const pair = { 을: ["을", "를"], 이: ["이", "가"], 은: ["은", "는"] }[p], c = String(w).trim().slice(-1).charCodeAt(0);
  if (!(c >= 0xac00 && c <= 0xd7a3)) return `${w}${pair[0]}(${pair[1]})`;
  return w + ((c - 0xac00) % 28 ? pair[0] : pair[1]);
}
const TOOL_KO = { trend: "추이", yoy: "전년 동월 대비", share: "구성비", rank: "순위", compare: "두 조건 비교", contribution: "증감 기여도", profile: "지역 프로필", describe: "기술통계" };
const ROLE_KO = { dim: "구분", count: "건수", amount: "금액", measure: "수치", time: "시간" };
function icon(name) { return `<i data-i="${name}">${svg(name)}</i>`; }
function svg(name) { return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name] || ""}</svg>`; }
function paintIcons(root = document) { $$("i[data-i]", root).forEach((el) => { if (!el.innerHTML) el.innerHTML = svg(el.dataset.i); }); }

// ---------- 공통 ----------
async function api(path, body, opts = {}) {
  const init = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  if (opts.raw) Object.assign(init, opts.raw);
  let r;
  try { r = await fetch(path, init); setOffline(false); }
  catch (e) { setOffline(true); throw new Error("혼디 서버에 연결할 수 없습니다. '실행.bat' 검은 창이 열려 있는지 확인하세요."); }
  let data = {};
  try { data = await r.json(); } catch (e) { /* 빈 응답 */ }
  if (!r.ok) throw new Error(data.error || `오류 ${r.status}`);
  return data;
}
function busy(on, text) { $("#busy").classList.toggle("hidden", !on); if (text) $("#busyText").textContent = text; }
function toast(msg, kind = "", action = null, ms = 0) {
  const t = document.createElement("div");
  t.className = "toast " + kind;
  const span = document.createElement("span"); span.textContent = msg; t.appendChild(span);
  if (action) {
    const b = document.createElement("button"); b.className = "tact"; b.textContent = action.label;
    b.onclick = () => { t.remove(); action.fn(); }; t.appendChild(b);
  }
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), ms || (action ? 7000 : kind === "err" ? 6000 : 3500));
  return t;
}
async function guarded(text, fn) {
  busy(true, text);
  try { return await fn(); }
  catch (e) { toast(e.message, "err", { label: "다시 시도", fn: () => guarded(text, fn) }); }
  finally { busy(false); }
}
function setOffline(on) {
  const b = $("#offline"); if (!b) return;
  b.classList.toggle("hidden", !on);
}
function modal(html) { $("#modalBody").innerHTML = html; paintIcons($("#modalBody")); $("#modal").classList.remove("hidden"); }
function closeModal() { $("#modal").classList.add("hidden"); $(".sheet").classList.remove("wide"); }
$("#modalX").onclick = closeModal;
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
function copyBox(id, text, rows) { return `<div class="copybox"><textarea id="${id}" rows="${rows}" readonly>${esc(text)}</textarea><button class="ghost sm" data-copy="${id}">복사</button></div>`; }
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-copy]");
  if (!b) return;
  const el = document.getElementById(b.dataset.copy);
  try { await navigator.clipboard.writeText(el.value); } catch (err) { el.select(); document.execCommand("copy"); }
  b.textContent = "✓ 복사됨"; b.classList.add("copied");
  setTimeout(() => { b.textContent = "복사"; b.classList.remove("copied"); }, 1800);
});
function openPanel(id, only = false) {
  if (only) $$(".panel").forEach((p) => p.classList.toggle("open", p.id === id));
  else $("#" + id).classList.add("open");
  $("#" + id).scrollIntoView({ behavior: "smooth", block: "nearest" });
}
$$(".phead").forEach((h) => h.addEventListener("click", () => h.parentElement.classList.toggle("open")));

const PURPOSE_SUB = { "사업계획서": "창업·소상공인", "현황자료": "기관 보고", "논문": "연구", "자유": "직접 묻기" };
const EXAMPLES = {
  "사업계획서": ["애월읍 한식 음식점업 손님은 주로 누구이고 언제 오나요?", "한식 음식점업은 어느 동네에서 가장 잘되나요?", "애월읍 한식 음식점업 매출이 작년보다 늘었나요?"],
  "현황자료": ["애월읍 업종별 이용금액 순위를 보여줘", "애월읍 소비가 늘거나 줄어든 이유는 어떤 업종 때문인가요?"],
  "논문": ["법정동별 월평균 이용금액 기술통계를 내줘", "분기별 이용건수 추이를 보여줘"],
  "자유": ["애월읍 한식 음식점업 매출 흐름을 보여줘", "요일별로 어느 요일이 붐비나요?"],
};
const NOTE_LABEL = (n) => n === "suppressed" ? "10 미만 가림 + 역산 방지(삭제처리)" : n.startsWith("rollup:") ? "상위 단위로 묶기(범주처리)" : n === "to_share" ? "비율로 바꾸기(응용집계)" : n === "no_numbers" ? "그림 수치 빼기" : n;

// ---------- 상태 그리기 ----------
async function refresh() {
  const st = await api("/api/state");
  S.state = st;
  $("#purposes").innerHTML = st.purposes.map((p) => `<button class="${p === st.purpose ? "on" : ""}" data-p="${p}">${p}<small>${PURPOSE_SUB[p] || ""}</small></button>`).join("");
  $("#obCount").textContent = st.outbound_count;
  const chip = $("#aiChip");
  chip.textContent = st.ai_ready ? `AI 켜짐 · ${st.settings.ai_model}` : "AI 없이 질문 카드 모드";
  chip.className = "chip " + (st.ai_ready ? "on" : "warn");
  $("#askHint").innerHTML = icon("lock") + (st.ai_ready
    ? "지역명·업종명·금액 같은 실제 값은 〔자리표시자〕로 가린 뒤 AI에 보냅니다. 계산은 이 PC 안에서만 합니다. Enter로 보내기"
    : "AI 키가 없어 질문 카드로 진행합니다. 직접 쓴 질문도 가장 가까운 카드로 바꿔 실행합니다.");
  paintIcons($("#askHint"));
  try { S.cards = (await api("/api/cards")).cards; } catch (e) { S.cards = []; }
  renderDatasets(st.datasets);
  await renderFocus(st.datasets);
  renderResultList(st.results);
  renderComposerCards();
  renderWelcome();
  renderStepper();
  renderStatus();
}
$("#purposes").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-p]"); if (!b) return;
  await api("/api/purpose", { purpose: b.dataset.p }); refresh();
  toast(`목적: ${b.dataset.p} — 질문 카드와 보고서 목차가 바뀌었습니다.`);
});

function stepsInfo() {
  const st = S.state || { datasets: [], results: [] };
  const nData = st.datasets.length, res = st.results, nonGreen = res.filter((r) => r.light !== "green").length;
  const files = st.datasets.reduce((a, d) => a + d.files, 0), missing = st.datasets.reduce((a, d) => a + d.missing.length, 0);
  return [
    { n: 1, t: "방문 전 준비", s: S.prepDone ? "주문서 준비됨" : "받을 데이터·주문서", st: S.prepDone || nData ? "done" : "" },
    { n: 2, t: "파일 넣기", s: nData ? `${nData}종 · 파일 ${files}개${missing ? ` · 빠진 달 ${missing}` : ""}` : "센터 CSV 넣기", st: nData ? (missing ? "warn" : "done") : "" },
    { n: 3, t: "묻고 분석", s: res.length ? `결과 ${res.length}개` : "질문 카드·말로 묻기", st: res.length ? "done" : "" },
    { n: 4, t: "반출 점검", s: !res.length ? "신호등 확인·고치기" : nonGreen ? `고칠 결과 ${nonGreen}개` : "모두 초록", st: !res.length ? "" : nonGreen ? "warn" : "done" },
    { n: 5, t: "가져가기", s: S.reportDone && S.formDone ? "보고서·신청서 완료" : S.reportDone ? "신청서 남음" : "보고서·신청서", st: S.reportDone && S.formDone ? "done" : "" },
  ];
}
function renderStepper() {
  const steps = stepsInfo();
  const active = steps.find((s) => s.st === "");
  $("#stepper").innerHTML = steps.map((s) => `<button class="st ${s.st} ${active && active.n === s.n && s.st !== "warn" ? "active" : ""}" data-step="${s.n}">
    <span class="dot">${s.st === "done" ? "✓" : s.st === "warn" ? "!" : s.n}</span><span><b>${s.t}</b><small>${esc(s.s)}</small></span></button>`).join("");
  $("#p2").classList.toggle("done", steps[1].st === "done");
}
$("#stepper").addEventListener("click", (e) => {
  const b = e.target.closest("[data-step]"); if (!b) return;
  const n = +b.dataset.step;
  if (n === 1) { openPanel("p1"); $("#prepQ").focus(); }
  else if (n === 2) { openPanel("p2"); if (S.state.datasets.length) $("#btnExplore").click(); }
  else if (n === 3) $("#question").focus();
  else if (n === 4) {
    const bad = $$(".res").find((x) => !x.querySelector(".badge.green"));
    (bad || $(".res") || $("#feed")).scrollIntoView({ behavior: "smooth", block: "center" });
  } else { openPanel("p3"); openPanel("p4"); }
});

function renderStatus() {
  const st = S.state; if (!st) return;
  const u = st.usage || {}, s = st.settings;
  const t = st.session ? `${st.session.slice(9, 11)}:${st.session.slice(11, 13)}` : "";
  $("#statusbar").innerHTML = [
    `${icon("lock")}센터 데이터 값 외부 전송: ${s.send_aggregates ? '<b>초록 집계표만(설정에서 켜짐)</b>' : '<b class="ok">안 함</b>'}`,
    `${icon("pc")}계산: <b>이 PC 안(DuckDB)</b>`,
    `AI 호출 이번 달 <b>${u.calls || 0}회</b> · 약 <b>${Number(u.krw || 0).toFixed(1)}원</b> / 한도 ${Number(s.monthly_limit_krw).toLocaleString()}원`,
    `퇴실 시 자동 삭제: <b class="${s.auto_delete ? "ok" : ""}">${s.auto_delete ? "켜짐" : "꺼짐"}</b>`,
    t ? `세션 ${t} 시작` : "",
    st.demo ? '<b class="demo">예시(가상) 데이터 사용 중</b>' : "",
  ].filter(Boolean).join("<span>·</span>");
  paintIcons($("#statusbar"));
}

function renderDatasets(ds) {
  $("#p2sum").textContent = ds.length ? `${ds.length}종 불러옴` : "센터에서";
  if (!ds.length) { $("#datasets").innerHTML = '<p class="muted" style="font-size:13px">아직 불러온 파일이 없습니다.</p>'; return; }
  $("#datasets").innerHTML = ds.map((d) => {
    const all = d.months.concat(d.missing).sort();
    const cells = all.map((m) => `<span class="${d.missing.includes(m) ? "miss" : ""}" title="${m}${d.missing.includes(m) ? " (빠짐)" : ""}"></span>`).join("");
    return `<div class="ds" data-ds="${esc(d.id)}" tabindex="0" role="button" title="눌러서 컬럼·월별 행 수·할 수 있는 분석 보기"><div class="h"><b>${esc(d.name)}</b>${d.sensitive ? '<span class="chip">가공 반출만</span>' : '<span class="chip on">원본 반출 가능</span>'}<span class="more">${icon("info")}자세히</span></div>
      <div class="meta">${d.months[0] || ""} ~ ${d.months[d.months.length - 1] || ""} · ${d.months.length}개월 · ${d.rows.toLocaleString()}행 · 파일 ${d.files}개</div>
      <div class="months">${cells}</div>
      ${d.missing.length ? `<div class="warn">빠진 달 ${d.missing.join(", ")} — 센터에서 이 달만 더 내려받으세요.</div>` : ""}</div>`;
  }).join("");
  paintIcons($("#datasets"));
}
function openDataset(id) {
  guarded("데이터를 살펴보는 중…", async () => {
    const d = await api("/api/dataset?id=" + encodeURIComponent(id));
    const max = Math.max(1, ...d.months.map((m) => m.rows));
    const bars = d.months.map((m) => `<div class="mb ${m.missing ? "miss" : ""}" title="${m.month} · ${m.missing ? "빠진 달" : m.rows.toLocaleString() + "행"}"><i style="height:${m.missing ? 100 : Math.max(4, (m.rows / max) * 100)}%"></i><small>${m.month.slice(2).replace("-", ".")}</small></div>`).join("");
    const cols = d.columns.map((c) => `<tr><td><b>${esc(c.label)}</b><br><small class="muted">${esc(c.key)}</small></td><td><span class="role ${c.role}">${esc(ROLE_KO[c.role] || c.role)}</span></td>
      <td>${c.distinct != null ? c.distinct.toLocaleString() + "종" : ""}</td><td class="tops">${(c.top || []).map((v) => `<span>${esc(v)}</span>`).join("")}${c.note ? `<div class="muted" style="font-size:11.5px">${esc(c.note)}</div>` : ""}</td></tr>`).join("");
    modal(`<h2>${esc(d.name)} <small class="muted" style="font-size:13px">${esc(d.id)}</small></h2>
      <p class="notes">${d.rows.toLocaleString()}행 · 파일 ${d.files}개 · ${d.months.filter((m) => !m.missing).length}개월${d.provider ? " · 제공 " + esc(d.provider) : ""} · ${d.sensitive ? "가공 결과만 반출 가능" : "원본 반출 가능 데이터"}</p>
      <h3>월별 행 수</h3><div class="monthbars">${bars}</div>
      ${d.months.some((m) => m.missing) ? `<p class="warn">빨간 칸은 빠진 달입니다. 센터 조회 화면에서 그 달만 더 내려받아 넣으면 됩니다.</p>` : ""}
      <h3>이 데이터로 바로 할 수 있는 분석</h3>
      <div class="cardgrid sm">${d.cards.length ? d.cards.map((c) => { const [a, b] = cardParts(c.label); return `<button class="cardtile" data-dcard="${esc(c.id)}"><b>${esc(a)}</b><small>${esc(b)}</small></button>`; }).join("") : '<p class="muted">질문 카드는 없지만 아래 입력창에 직접 물어볼 수 있습니다.</p>'}</div>
      <h3>컬럼 ${d.columns.length}개</h3>
      <div class="tscroll"><table class="t cols"><thead><tr><th>이름</th><th>종류</th><th>값 가짓수</th><th>자주 나오는 값</th></tr></thead><tbody>${cols}</tbody></table></div>
      <p class="muted" style="font-size:12px">이 화면은 이 PC 안에서만 계산했고 외부로 보내지 않았습니다.</p>`);
    $$("[data-dcard]", $("#modalBody")).forEach((b) => (b.onclick = () => { closeModal(); askCard(b.dataset.dcard); }));
  });
}
$("#datasets").addEventListener("click", (e) => { const d = e.target.closest("[data-ds]"); if (d) openDataset(d.dataset.ds); });
$("#datasets").addEventListener("keydown", (e) => { const d = e.target.closest("[data-ds]"); if (d && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openDataset(d.dataset.ds); } });

// ---------- 내 관심 조건(지역·업종 한 번 고르기) ----------
async function renderFocus(ds) {
  const box = $("#focus");
  box.classList.toggle("hidden", !ds.length);
  if (!ds.length) { S.focusKey = ""; S.focus = { area: "", biz: "" }; return; }
  const key = ds.map((d) => d.id + d.rows).join(",");
  if (key === S.focusKey) return;
  let f = { areas: [], businesses: [] };
  try { f = await api("/api/focus-options"); S.focusKey = key; } catch (e) { /* 목록 없이도 동작 — 다음 새로고침 때 다시 시도 */ }
  const fill = (sel, list, cur, none) => {
    sel.innerHTML = `<option value="">${none}</option>` + list.map((v) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(v)}</option>`).join("");
    sel.disabled = !list.length; sel.closest("label").classList.toggle("hidden", !list.length);
  };
  if (S.focus.area && !f.areas.includes(S.focus.area)) S.focus.area = "";
  if (S.focus.biz && !f.businesses.includes(S.focus.biz)) S.focus.biz = "";
  fill($("#focusArea"), f.areas, S.focus.area, "고르지 않음");
  fill($("#focusBiz"), f.businesses, S.focus.biz, "고르지 않음");
}
function focusText() { return [S.focus.area, S.focus.biz].filter(Boolean).join(" · "); }
["#focusArea", "#focusBiz"].forEach((id) => $(id).addEventListener("change", () => {
  S.focus = { area: $("#focusArea").value, biz: $("#focusBiz").value };
  const t = focusText();
  toast(t ? `관심 조건: ${t} — 이제 질문을 누르면 이 조건으로 바로 계산해요.` : "관심 조건을 비웠어요. 질문할 때마다 골라 주세요.", t ? "ok" : "");
  renderWelcome();
}));
$("#btnExplore").onclick = () => { S.explore = true; renderWelcome(); $("#welcome").scrollIntoView({ behavior: "smooth", block: "start" }); };
const FOCUS_KEYS = { bjd: "area", emd_nm: "area", biz_nm: "biz" };
function autoFill(box) {  // 계획에 빈 값이 있으면 관심 조건으로 채운다. 모두 채웠으면 true
  let all = true;
  $$(".need", box).forEach((el) => {
    const inp = $("input", el), v = S.focus[FOCUS_KEYS[el.dataset.key]];
    const opts = $$("option", $("datalist", el)).map((o) => o.value);
    if (v && opts.includes(v)) { inp.value = v; inp.dispatchEvent(new Event("input")); } else all = false;
  });
  return all;
}
function shortName(n) { return String(n).replace(/_v\d+$/, ""); }

function cardParts(label) { const i = label.indexOf(" ("); return i > 0 ? [label.slice(0, i), label.slice(i + 2, -1)] : [label, ""]; }
function renderComposerCards() {
  $("#cards").innerHTML = S.cards.map((c) => `<button data-card="${c.id}" ${c.enabled ? "" : "disabled"} title="${esc(c.enabled ? c.label : c.why)}">${esc(cardParts(c.label)[0])}</button>`).join("");
}
function renderWelcome() {
  const st = S.state, w = $("#welcome");
  document.body.classList.toggle("nodata", !st.datasets.length);  // 파일을 넣기 전에는 질문창을 숨겨 첫 화면을 단순하게
  if ((st.results.length || $$(".turn").length) && !S.explore) { w.classList.add("hidden"); return; }
  w.classList.remove("hidden");
  if (!st.datasets.length) {
    w.innerHTML = `<div class="whead"><span class="eyebrow">제주빅데이터센터 분석실 PC용</span>
        <h2>센터 데이터, 코딩 없이<br>클릭 몇 번으로 분석해요</h2>
        <p class="lead">센터에서 내려받은 파일을 넣고 궁금한 질문을 고르면, 그림과 쉬운 한 줄 설명으로 알려 드려요. 반출 기준 점검과 보고서까지 이어서 해 드려요.</p></div>
      <ol class="flow">
        <li><span class="fn">1</span><b>센터 조회 화면에서 CSV 내려받기</b><small>한 달씩 받아도 괜찮아요. 여러 파일을 한꺼번에 넣으면 돼요.</small></li>
        <li><span class="fn">2</span><b>혼디에 파일 넣기</b><small>다운로드 폴더에서 찾아 데이터 종류와 기간을 알아서 정리해요.</small></li>
        <li><span class="fn">3</span><b>질문 고르기</b><small>그림, 한 줄 요약, 반출 가능 여부까지 바로 보여 드려요.</small></li>
      </ol>
      <div class="tiles">
        <button class="tile hero" data-go="scan">${icon("folder")}<b>다운로드 폴더에서 찾기</b><small>센터에서 받은 Results_….csv를 찾아 미리 골라 둘게요</small></button>
        <button class="tile" data-go="files">${icon("upload")}<b>파일 직접 고르기</b><small>파일을 화면 어디에나 끌어다 놓아도 돼요</small></button>
        <button class="tile" data-go="demo">${icon("spark")}<b>예시 데이터로 체험</b><small>가상 데이터로 처음부터 끝까지 따라 해 봐요</small></button>
        <button class="tile" data-go="prep">${icon("map")}<b>방문 전 준비</b><small>무엇을 몇 달치 받을지 다운로드 주문서를 만들어요</small></button>
      </div>
      <div class="trust"><span>${icon("pc")}계산은 이 PC 안에서만</span><span>${icon("lock")}데이터 값은 AI로 보내지 않음</span><span>${icon("shield")}반출 기준 미리 점검</span><span>${icon("trash")}퇴실하면 자동 삭제</span></div>`;
  } else {
    const ex = EXAMPLES[st.purpose] || EXAMPLES["자유"];
    const mine = new Set(S.cards.filter((c) => c.enabled).map((c) => c.id));
    const ft = focusText();
    const xcard = (d) => {
      const qs = (d.cards || []).filter((id) => mine.has(id)).slice(0, 3).map((id) => S.cards.find((c) => c.id === id));
      return `<article class="xcard"><div class="xh"><div><b>${esc(shortName(d.name))}</b><small>${d.months.length ? `${d.months[0]} ~ ${d.months[d.months.length - 1]} · ${d.months.length}개월 · ` : ""}${d.rows.toLocaleString()}행</small></div>
          ${d.sensitive ? '<span class="chip">가공 결과만 반출</span>' : '<span class="chip on">원본 반출 가능</span>'}</div>
        <p class="about">${esc(d.about || "")}</p>
        ${d.measures && d.measures.length ? `<div class="xrow"><span class="k">알 수 있는 수치</span><span class="tags">${d.measures.slice(0, 5).map((m) => `<span>${esc(m)}</span>`).join("")}</span></div>` : ""}
        ${d.by && d.by.length ? `<div class="xrow"><span class="k">나눠 보는 기준</span><span class="tags">${d.by.slice(0, 6).map((m) => `<span>${esc(m)}</span>`).join("")}${d.by.length > 6 ? `<span class="more-tag">+${d.by.length - 6}</span>` : ""}</span></div>` : ""}
        ${d.missing.length ? `<p class="warn">빠진 달 ${d.missing.join(", ")} — 센터에서 이 달만 더 내려받으세요.</p>` : ""}
        <div class="xq">${qs.map((c) => `<button data-card="${c.id}">${esc(cardParts(c.label)[0])}</button>`).join("")}<button class="link" data-ds="${esc(d.id)}">자세히 보기 →</button></div></article>`;
    };
    w.innerHTML = `<div class="whead">${S.explore ? '<button class="x" data-go="close" aria-label="둘러보기 닫기">×</button>' : ""}<span class="eyebrow">1단계 · 데이터 둘러보기</span>
        <h2>불러온 데이터 ${st.datasets.length}종을 둘러보세요</h2>
        <p class="lead">데이터마다 무엇을 알 수 있는지 정리했어요. 궁금한 질문을 누르면 바로 분석해 드려요.${ft ? ` 지금은 <b>${esc(ft)}</b> 기준으로 계산해요.` : " 위에서 <b>관심 지역·업종</b>을 고르면 질문할 때마다 다시 고르지 않아도 돼요."}</p></div>
      <div class="explore">${st.datasets.map(xcard).join("")}</div>
      <h3 class="sec"><span class="eyebrow">2단계 · 바로 물어보기</span>${esc(st.purpose)}에 자주 쓰는 질문</h3>
      <div class="cardgrid">${S.cards.map((c) => { const [a, b] = cardParts(c.label); return `<button class="cardtile" data-card="${c.id}" ${c.enabled ? "" : "disabled"}><b>${esc(a)}</b><small>${esc(c.enabled ? b : c.why)}</small></button>`; }).join("")}</div>
      <div class="examples"><span class="muted" style="font-size:13px">이렇게 말로 물어봐도 돼요:</span>${ex.map((q) => `<button data-ex="${esc(q)}">${esc(q)}</button>`).join("")}</div>`;
  }
  paintIcons(w);
}
$("#welcome").addEventListener("click", (e) => {
  const go = e.target.closest("[data-go]"), card = e.target.closest("[data-card]"), ex = e.target.closest("[data-ex]");
  const dsb = e.target.closest("[data-ds]");
  if (dsb) return openDataset(dsb.dataset.ds);
  if (go) {
    if (go.dataset.go === "close") { S.explore = false; renderWelcome(); return; }
    if (go.dataset.go === "scan") { openPanel("p2"); $("#btnScan").click(); }
    if (go.dataset.go === "files") $("#filePick").click();
    if (go.dataset.go === "demo") $("#btnDemo").click();
    if (go.dataset.go === "prep") { openPanel("p1"); $("#prepQ").focus(); }
  } else if (card && !card.disabled) { S.explore = false; askCard(card.dataset.card); }
  else if (ex) { $("#question").value = ex.dataset.ex; autoGrow(); $("#question").focus(); }
});

// ---------- ① 방문 전 준비 ----------
$("#btnPrep").onclick = () => guarded("받을 데이터를 고르는 중…", async () => {
  const area = $("#prepArea").value.trim();
  const d = await api("/api/prep", { purpose: S.state.purpose, question: $("#prepQ").value, conditions: area ? { bjd: area, emd_nm: area } : {}, name: "", visit_date: "" });
  const total = d.recs.reduce((a, r) => a + r.months.length, 0);
  $("#prepOut").innerHTML = `<ul style="padding-left:18px;font-size:14px">${d.recs.map((r) => `<li><b>${esc(r.name)}</b> <span class="muted">${r.months[0]}~${r.months[r.months.length - 1]}</span><br><small class="muted">${esc(r.why)}</small></li>`).join("")}</ul>
    <p class="notes">센터 조회는 한 번에 1개월씩이라 총 <b>${total}번</b> 내려받게 됩니다.</p>
    <div class="outfiles"><a href="${d.order_url}" target="_blank">${icon("file")}다운로드 주문서(인쇄용)<small>새 창</small></a></div>
    <label class="lbl">운영자 요청문 — 여러 달은 미리 받아 달라고 요청할 수 있어요</label>
    ${copyBox("reqText", d.request_text, 6)}`;
  paintIcons($("#prepOut"));
  S.prepDone = true; renderStepper();
});
(function initDates() {
  const t = new Date(); const a = new Date(t.getFullYear(), t.getMonth() - 2, 1);
  const f = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  $("#hubFrom").value = f(a); $("#hubTo").value = f(new Date(a.getFullYear(), a.getMonth(), 14));
})();
$("#btnHub").onclick = () => guarded("공개 데이터를 불러오는 중…", async () => {
  const kind = $("#hubKind").value, emd = $("#hubEmd").value.trim();
  const p = new URLSearchParams({ kind });
  const from = $("#hubFrom").value.replaceAll("-", ""), to = $("#hubTo").value.replaceAll("-", "");
  if (kind === "weather") p.set("searchDate", from); else { p.set("startDate", from); p.set("endDate", to); }
  if (emd && kind === "population") p.set("emd", emd);
  const d = await api("/api/hub?" + p.toString());
  const max = Math.max(1, ...d.series.map((x) => x.value));
  $("#hubOut").innerHTML = `<p><b>${esc(d.name)}</b> <span class="chip ${d.source === "live" ? "on" : "warn"}">${d.source === "live" ? "실시간" : d.source === "cache" ? "저장본" : "예시(가상)"}</span></p>
    <div class="spark">${d.series.map((x) => `<span style="height:${Math.round((x.value / max) * 100)}%" title="${x.date}: ${x.value.toLocaleString()}"></span>`).join("")}</div>
    <p class="muted" style="font-size:12px">${esc(d.note)} · 원문: <a href="${d.url}" target="_blank">제주데이터허브</a></p>`;
});

// ---------- ② 받은 파일 ----------
const drop = $("#drop");
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => { e.stopPropagation(); upload([...e.dataTransfer.files]); });
drop.onclick = () => $("#filePick").click();
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#filePick").click(); } });
// 화면 어디에 놓아도 받기
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => { e.preventDefault(); if (e.dataTransfer && e.dataTransfer.files.length) upload([...e.dataTransfer.files]); });
$("#filePick").onchange = (e) => { upload([...e.target.files]); e.target.value = ""; };
const STATUS_TXT = { ok: "✔", duplicate: "⚠", unknown: "✖", error: "✖", ambiguous: "?" };
function fileLog(list) {
  const amb = list.filter((x) => x.status === "ambiguous");
  const sets = [...new Map(amb.map((x) => [x.candidates.map((c) => c.id).join(","), x.candidates])).values()];
  $("#uploadOut").innerHTML = `<div class="filelog">${list.map((x) => `<div><span class="${x.status}">${STATUS_TXT[x.status] || "?"}</span><span class="n">${esc(x.name)}<small>${x.status === "ok" ? `${esc(x.dataset)} · ${esc(x.month)} · ${Number(x.rows).toLocaleString()}행${x.message ? " · " + esc(x.message) : ""}` : esc(x.message)}</small></span></div>`).join("")}</div>`
    + sets.map((cs) => `<div class="notes"><b>어느 데이터인가요?</b> 컬럼 구성이 똑같은 데이터가 있어 파일만으로는 구분할 수 없습니다. 센터 화면에서 고른 데이터를 눌러 주세요(같은 파일 ${amb.filter((x) => x.candidates.map((c) => c.id).join(",") === cs.map((c) => c.id).join(",")).length}개에 모두 적용).
      <div class="row">${cs.map((c) => `<button class="ghost sm" data-assign="${esc(c.id)}">${esc(c.name)}</button>`).join("")}</div></div>`).join("");
}
$("#uploadOut").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-assign]"); if (!b) return;
  await guarded("고른 데이터로 불러오는 중…", async () => {
    const d = await api("/api/files/assign", { dataset: b.dataset.assign });
    fileLog(d.files); toast(`${d.files.filter((x) => x.status === "ok").length}개 파일을 불러왔습니다.`, "ok"); await refresh();
  });
});
async function upload(files) {
  files = files.filter((f) => f.name.toLowerCase().endsWith(".csv"));
  if (!files.length) return toast("CSV 파일만 넣을 수 있습니다.", "err");
  openPanel("p2");
  const log = [];
  await guarded(`파일 ${files.length}개를 읽는 중…`, async () => {
    for (const [i, f] of files.entries()) {
      $("#busyText").textContent = `파일 읽는 중… (${i + 1}/${files.length}) ${f.name}`;
      const d = await api("/api/files/upload", undefined, { raw: { method: "POST", headers: { "X-Filename": encodeURIComponent(f.name) }, body: f } });
      log.push(...d.files);
    }
  });
  fileLog(log);
  $("#p1").classList.remove("open");
  const ok = log.filter((x) => x.status === "ok").length;
  toast(`${ok}개 파일을 불러왔습니다${log.length > ok ? `, ${log.length - ok}개는 확인이 필요합니다` : ""}.`, log.length > ok ? "" : "ok");
  await refresh();
}
$("#btnScan").onclick = () => guarded("다운로드·바탕화면 폴더를 살피는 중…", async () => {
  const d = await api("/api/files/scan", {});
  if (!d.files.length) { $("#scanOut").innerHTML = `<p class="notes">다운로드·바탕화면\\요청파일 폴더에 CSV가 없습니다.</p>`; return; }
  $("#scanOut").innerHTML = `<p class="lbl">센터 파일(Results_…)은 미리 골라 두었습니다</p><div class="filelist">${d.files.map((f) => `<label><input type="checkbox" value="${esc(f.path)}" ${f.center ? "checked" : ""}> ${esc(f.name)} <span class="muted">${esc(f.folder.split(/[\\/]/).slice(-1)[0])}</span></label>`).join("")}</div>
    <div class="row"><button id="btnLoadSel">고른 파일 불러오기</button></div>`;
  $("#btnLoadSel").onclick = () => guarded("불러오는 중…", async () => {
    const paths = $$("#scanOut input:checked").map((x) => x.value);
    const r = await api("/api/files/load", { paths });
    $("#scanOut").innerHTML = ""; fileLog(r.files); toast(`${r.files.filter((x) => x.status === "ok").length}개 파일을 불러왔습니다.`, "ok"); refresh();
  });
});
$("#btnDemo").onclick = () => guarded("예시(가상) 데이터를 만드는 중…", async () => {
  await api("/api/demo", {});
  toast("예시 데이터 49개 파일을 불러왔습니다. 2025년 11월 카드 파일 하나는 일부러 뺐습니다.", "ok");
  $("#uploadOut").innerHTML = "";
  $("#p1").classList.remove("open");
  await refresh();
});

// ---------- 대화(질문 → 계획 → 실행) ----------
function newTurn(text, sub) {
  const t = document.createElement("div");
  t.className = "turn";
  t.innerHTML = `<div class="msg user">${sub ? `<small>${esc(sub)}</small>` : ""}${esc(text)}</div>`;
  $("#feed").appendChild(t);
  $("#welcome").classList.add("hidden");
  return t;
}
function agentMsg(turn, title) {
  const m = document.createElement("div");
  m.className = "msg agent";
  m.innerHTML = `<div class="ahead"><span class="logo">혼</span>혼디 · ${esc(title)}</div><div class="abody"></div>`;
  turn.appendChild(m);
  m.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return m;
}
function progress(box, labels) {
  box.innerHTML = `<ol class="progress">${labels.map((l) => `<li><span class="pi"></span>${esc(l)}</li>`).join("")}</ol>`;
  const lis = $$("li", box); let i = 0; lis[0].className = "run";
  const timer = setInterval(() => { if (i < lis.length - 1) { lis[i].className = "ok"; i++; lis[i].className = "run"; } }, 700);
  return { done() { clearInterval(timer); lis.forEach((l) => (l.className = "ok")); }, fail() { clearInterval(timer); lis[i].className = "fail"; } };
}
function askCard(id) {
  if (S.cardBusy) return;  // 두 번 눌러도 한 번만(관심 조건이 있으면 바로 실행되므로)
  const c = S.cards.find((x) => x.id === id);
  S.asked.add(id); S.explore = false; S.cardBusy = true;
  makePlan({ card: id }, c ? cardParts(c.label)[0] : "질문 카드", "질문 카드").finally(() => { S.cardBusy = false; });
}
$("#cards").addEventListener("click", (e) => { const b = e.target.closest("[data-card]"); if (b && !b.disabled) askCard(b.dataset.card); });
function autoGrow() { const q = $("#question"); q.style.height = "auto"; q.style.height = Math.min(160, q.scrollHeight + 2) + "px"; }
$("#question").addEventListener("input", autoGrow);
$("#btnAsk").onclick = () => { const q = $("#question").value.trim(); if (!q) return $("#question").focus(); $("#question").value = ""; autoGrow(); makePlan({ question: q }, q); };
$("#question").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("#btnAsk").click(); } });

async function makePlan(body, text, sub) {
  if (!S.state.datasets.length) { toast("먼저 왼쪽 ②에 센터 파일을 넣거나 '예시 데이터로 체험'을 눌러 주세요.", "err"); openPanel("p2"); return; }
  const turn = newTurn(text, sub);
  const m = agentMsg(turn, "분석 계획");
  const box = $(".abody", m);
  const prog = progress(box, body.question
    ? (S.state.ai_ready ? ["질문 속 지역·업종·금액을 〔자리표시자〕로 가리기", "AI가 분석 계획 세우기(가린 질문만 전송)", "계획 검증 — 데이터·컬럼·도구 확인"] : ["질문과 가장 가까운 질문 카드 찾기", "계획 검증 — 데이터·컬럼·도구 확인"])
    : ["질문 카드 계획 불러오기", "계획 검증 — 불러온 파일 확인"]);
  let d;
  try { d = await api("/api/plan", body); prog.done(); }
  catch (e) { prog.fail(); box.insertAdjacentHTML("beforeend", `<p class="err-line">${esc(e.message)}</p>`); return; }
  const trace = (d.trace || []).map((t, i) => t.error
    ? `<b>AI 호출 ${i + 1}</b> 실패: ${esc(t.error)}`
    : `<b>AI 호출 ${i + 1}</b> · 보낸 글(값 ${t.masked}개 가림)\n${esc(t.sent)}\n→ 토큰 ${t.input_tokens}+${t.output_tokens} · 약 ${Number(t.krw).toFixed(2)}원`).join("\n\n");
  $(".ahead", m).insertAdjacentHTML("beforeend", ` <span class="chip ${d.plan.source === "ai" ? "on" : ""}">${d.plan.source === "ai" ? "AI가 세운 계획" : "질문 카드"}</span>`);
  box.innerHTML = `<div class="done-line">${icon("check")}${d.plan.source === "ai" ? "값을 가리고 AI에 계획을 받아 검증했습니다." : "계획을 준비했습니다."} 이렇게 계산할게요:</div>
    <ol class="planlist">${d.plan_text.map((t) => `<li>${esc(t.replace(/^\d+\.\s*/, ""))}</li>`).join("")}</ol>
    ${d.notes.length ? `<div class="notes">${d.notes.map(esc).join("<br>")}</div>` : ""}
    ${trace ? `<details class="tr" open><summary>Agent 기록 — AI가 본 것은 이것뿐입니다</summary><div class="trace">${trace}</div></details>` : ""}
    ${d.needs.length ? `<p class="lbl" style="margin-top:10px">아래 값을 골라 주세요 (불러온 데이터에 있는 값만 고를 수 있어요)</p>` + d.needs.map(needHTML).join("") : ""}
    <div class="row actions"><button class="primary btn-run">${icon("pc")}이대로 실행</button><button class="ghost cancel">취소</button></div>`;
  paintIcons(m);
  $$(".need", box).forEach(bindNeed);
  const filled = body.card ? autoFill(box) : false;  // 말로 물은 질문은 관심 조건으로 몰래 채우지 않는다(질문 속 지역과 다를 수 있음)
  $(".cancel", box).onclick = () => { $(".actions", box).outerHTML = '<p class="muted" style="font-size:13px">취소했습니다.</p>'; };
  $(".btn-run", box).onclick = () => runPlan(turn, box, d.plan, d.needs);
  m.scrollIntoView({ behavior: "smooth", block: "nearest" });
  if (body.card && d.plan.source === "card" && filled && (d.needs.length ? focusText() : true)) {  // 질문 카드는 고를 값이 다 채워지면 바로 실행
    $(".actions", box).insertAdjacentHTML("beforebegin", `<div class="notes">${d.needs.length ? `관심 조건 <b>${esc(focusText())}</b>으로 채워 바로 계산해요.` : "고를 값이 없어 바로 계산해요."}</div>`);
    runPlan(turn, box, d.plan, d.needs);
  }
  refresh();
}
function needHTML(n) {
  const recent = (S.recent[n.key] || []).filter((v) => n.options.includes(v));
  const top = [...new Set([...recent, ...(n.top || n.options).slice(0, 12)])].slice(0, 14);
  return `<div class="need" data-key="${esc(n.key)}"><div class="lbl">${esc(n.label)}</div>
    <div class="chips">${top.map((o) => `<button type="button" data-v="${esc(o)}">${esc(o)}</button>`).join("")}</div>
    <input list="dl_${esc(n.key)}_${Date.now()}" data-need="${esc(n.key)}" placeholder="${n.options.length > top.length ? `다른 값 검색 (전체 ${n.options.length}개)` : "직접 입력"}">
    <datalist id="dl_${esc(n.key)}_${Date.now()}">${n.options.map((o) => `<option value="${esc(o)}">`).join("")}</datalist></div>`;
}
function bindNeed(el) {
  const inp = $("input", el), dl = $("datalist", el);
  inp.setAttribute("list", dl.id);
  const sync = () => $$(".chips button", el).forEach((b) => b.classList.toggle("on", b.dataset.v === inp.value));
  $(".chips", el).addEventListener("click", (e) => { const b = e.target.closest("[data-v]"); if (!b) return; inp.value = b.dataset.v; sync(); });
  inp.addEventListener("input", sync);
}
async function runPlan(turn, box, plan, needs) {
  const values = {};
  for (const el of $$("[data-need]", box)) {
    const n = needs.find((x) => x.key === el.dataset.need);
    if (!el.value) { el.focus(); return toast(`${josa(n.label, "을")} 골라 주세요.`, "err"); }
    if (!n.options.includes(el.value)) { el.focus(); return toast(`${josa(el.value, "은")} 불러온 데이터에 없습니다. 목록에서 골라 주세요.`, "err"); }
    values[el.dataset.need] = el.value;
    S.recent[el.dataset.need] = [el.value, ...(S.recent[el.dataset.need] || []).filter((v) => v !== el.value)].slice(0, 4);
  }
  const actions = $(".actions", box);
  actions.innerHTML = "";
  $$("input,.chips button", box).forEach((x) => (x.disabled = true));
  const prog = progress(actions, ["이 PC 안에서 계산(DuckDB)", "반출 기준 점검(10 미만·역산·발췌)", "그림·해설·출처 만들기"]);
  try {
    const d = await api("/api/run", { plan, values });
    prog.done();
    const g = d.results.filter((r) => r.light === "green").length;
    actions.innerHTML = `<div class="done-line">${icon("check")}결과 ${d.results.length}개를 만들었습니다${g < d.results.length ? ` — 반출 전에 고칠 결과가 ${d.results.length - g}개 있어요` : " — 모두 반출 충족 예상(초록)"}.</div>`;
    paintIcons(actions);
    const chosen = Object.entries(values).map(([k, v]) => `${esc((needs.find((n) => n.key === k) || {}).label || k)} = <b>${esc(v)}</b>`);
    $$(".need", box).forEach((x) => x.remove());
    const lbl = $("p.lbl", box); if (lbl) lbl.outerHTML = chosen.length ? `<div class="notes">고른 값: ${chosen.join(" · ")}</div>` : "";
    const els = d.results.map((r) => addResult(r, false, turn));
    addNext(turn);
    if (els[0]) setTimeout(() => els[0].scrollIntoView({ behavior: "smooth", block: "start" }), 120);
    refresh();
  } catch (e) { prog.fail(); actions.insertAdjacentHTML("beforeend", `<p class="err-line">${esc(e.message)}</p>`); }
}

function addNext(turn) {  // 탐색이 끊기지 않게 같은 조건으로 이어서 볼 질문
  const next = S.cards.filter((c) => c.enabled && !S.asked.has(c.id)).slice(0, 4);
  if (!next.length) return;
  const ft = focusText();
  turn.insertAdjacentHTML("beforeend", `<div class="next"><span class="nl">${icon("spark")}이어서 볼 만한 질문${ft ? ` <small>${esc(ft)} 기준</small>` : ""}</span>${next.map((c) => `<button data-card="${c.id}">${esc(cardParts(c.label)[0])}</button>`).join("")}</div>`);
  paintIcons(turn);
}

// ---------- 결과 카드 ----------
function fname(s) { return String(s).replace(/[\\/:*?"<>|]/g, "_").slice(0, 80) + ".png"; }
function resultHTML(r) {
  const picked = !S.unselected.has(r.id);
  const narrative = r.ai_narrative || r.narrative;
  const table = `<table class="t"><thead><tr>${r.table.columns.map((c) => `<th>${esc(c.label)}</th>`).join("")}</tr></thead><tbody>${r.table.rows.map((row) => `<tr>${row.map((v) => `<td class="${String(v).includes("가림") ? "m" : ""}">${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table>${r.table.total > r.table.rows.length ? `<p class="muted" style="font-size:12px">상위 ${r.table.rows.length}행 표시(전체 ${r.table.total}행)</p>` : ""}`;
  return `<header><span class="ldot ${r.light}"></span><h3>${esc(r.title)}<small>${esc(r.dataset)} · ${esc(r.kind)}</small></h3><span class="badge ${r.light}">반출 ${esc(r.light_text)}</span></header>
    ${r.headline ? `<div class="headline"><span class="hl-k">한 줄 요약</span><p>${esc(r.headline)}</p></div>` : ""}
    <div class="grid"><div class="fig"><img src="${r.png}" alt="${esc(r.title)}" loading="lazy" data-zoom="${r.id}">
      ${r.howto ? `<p class="howto-line">${icon("info")}<span><b>그래프 읽는 법</b> ${esc(r.howto)}</span></p>` : ""}</div>
    <div class="info">
      <h4>자세한 해설${r.ai_narrative ? " (AI)" : ""}</h4><ul>${narrative.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
      <div class="guard ${r.light}"><div class="gt">${icon("shield")}반출 지킴이</div><ul>${r.reasons.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
      ${r.fixes.length ? `<div class="fixes">${r.fixes.map((f) => `<button data-fix="${esc(f.id)}" data-rid="${r.id}"><b>고치기</b> ${esc(f.label)}</button>`).join("")}</div>` : ""}
      ${r.notes.length ? `<div class="fixed-note">✓ 적용한 처리: ${r.notes.map((n) => esc(NOTE_LABEL(n))).join(", ")}</div>` : ""}</div>
      ${r.caveats.length ? `<h4>데이터 한계</h4><ul>${r.caveats.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>` : ""}
      <p class="src">${esc(r.source)}</p>
    </div></div>
    <div class="rfoot"><label><input type="checkbox" data-pick="${r.id}" ${picked ? "checked" : ""}>보고서·신청서에 넣기</label>
      <button class="ghost sm" data-table="${r.id}">${icon("table")}표 보기 · 가린 칸 ${r.masked}개</button>
      ${r.edit ? `<button class="ghost sm" data-edit="${r.id}" title="지역·업종·기간·지표만 바꿔 같은 분석을 다시">${icon("redo")}조건 바꿔 다시</button>` : ""}
      <a href="${r.png}" download="${esc(fname(r.title))}"><button class="ghost sm" tabindex="-1">${icon("down")}그림 저장</button></a>
      <span class="sp"></span><button class="link" data-remove="${r.id}">${icon("trash")}결과 빼기</button></div>
    <div class="editor hidden"></div>
    <div class="tblwrap hidden">${table}</div>`;
}
function editorHTML(r) {
  const e = r.edit;
  const opt = (v, cur) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(v)}</option>`;
  const flt = e.filters.map((f) => `<label><span>${esc(f.label)}</span><select data-ef="${esc(f.key)}">
      ${f.top.length ? `<optgroup label="자주 나오는 값">${f.top.map((v) => opt(v, f.value)).join("")}</optgroup>` : ""}
      <optgroup label="전체 (${f.options.length})">${f.options.filter((v) => !f.top.includes(v)).map((v) => opt(v, f.value)).join("")}</optgroup></select></label>`).join("");
  const per = e.months.length && e.tool !== "contribution" && e.tool !== "yoy" ? `<label><span>기간</span><span class="pair"><select data-ep="0">${e.months.map((m) => opt(m, e.period[0])).join("")}</select>~<select data-ep="1">${e.months.map((m) => opt(m, e.period[1])).join("")}</select></span></label>` : "";
  const met = e.metrics.length > 1 ? `<label><span>지표</span><select data-em>${e.metrics.map((m) => `<option value="${esc(m.key)}" ${m.key === e.metric ? "selected" : ""}>${esc(m.label)}</option>`).join("")}</select></label>` : "";
  return `<div class="eh">${icon("redo")}<b>${esc(TOOL_KO[e.tool] || e.tool)}</b> 분석을 조건만 바꿔 다시 실행합니다 <small class="muted">원래 결과는 그대로 남습니다</small></div>
    <div class="efields">${flt}${per}${met}</div>
    <div class="row"><button class="primary sm" data-rerun="${r.id}">${icon("redo")}다시 실행</button><button class="ghost sm" data-edit="${r.id}">닫기</button></div>`;
}
function placeResult(nr, afterEl) {
  S.results.set(nr.id, nr);
  const el = document.createElement("article"); el.className = "res flash"; el.id = "r_" + nr.id; el.innerHTML = resultHTML(nr);
  paintIcons(el); afterEl.after(el);
  setTimeout(() => el.classList.remove("flash"), 1600);
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  return el;
}
function removeWithUndo(id) {
  const el = document.getElementById("r_" + id); if (!el) return;
  el.classList.add("hidden"); S.removing.add(id);
  renderResultList(S.state.results);
  const r = S.results.get(id);
  const timer = setTimeout(async () => {
    S.removing.delete(id);
    try { await api("/api/remove", { result_id: id }); } catch (e) { /* 연결 끊김은 배너로 안내 */ }
    el.remove(); S.results.delete(id); refresh();
  }, 7000);
  toast(`'${r ? r.title : "결과"}'를 뺐습니다.`, "", { label: "되돌리기", fn: () => {
    clearTimeout(timer); S.removing.delete(id); el.classList.remove("hidden");
    renderResultList(S.state.results); toast("되돌렸습니다.", "ok");
  } });
}
function addResult(r, top, turn) {
  S.results.set(r.id, r);
  if (!turn) turn = $(".turn:last-child") || newTurn("결과", "분석");
  const el = document.createElement("article");
  el.className = "res"; el.id = "r_" + r.id; el.innerHTML = resultHTML(r);
  paintIcons(el);
  turn.appendChild(el);
  $("#welcome").classList.add("hidden");
  return el;
}
function showResults(results, text, sub) {  // 시연·외부 호출용: 결과 묶음을 새 대화로 보여 줌
  const t = newTurn(text, sub);
  results.forEach((r) => addResult(r, false, t));
  return t;
}
$("#feed").addEventListener("click", async (e) => {
  const nx = e.target.closest(".next [data-card]");
  if (nx) { nx.closest(".next").remove(); askCard(nx.dataset.card); return; }
  const fx = e.target.closest("[data-fix]"), rm = e.target.closest("[data-remove]"), tb = e.target.closest("[data-table]"), zm = e.target.closest("[data-zoom]");
  const ed = e.target.closest("[data-edit]"), rr = e.target.closest("[data-rerun]");
  if (fx) {
    const rid = fx.dataset.rid, before = S.results.get(rid);
    await guarded("고치는 중… (다시 집계하고 반출 기준을 점검합니다)", async () => {
      const d = await api("/api/fix", { result_id: rid, fix_id: fx.dataset.fix });
      const nr = d.results[0];
      await api("/api/remove", { result_id: rid });
      S.results.delete(rid); S.results.set(nr.id, nr);
      if (S.unselected.delete(rid)) S.unselected.add(nr.id);
      const old = document.getElementById("r_" + rid);
      const el = document.createElement("article"); el.className = "res flash"; el.id = "r_" + nr.id; el.innerHTML = resultHTML(nr);
      paintIcons(el); old.replaceWith(el); setTimeout(() => el.classList.remove("flash"), 1600);
      toast(`고쳤습니다: 반출 ${before ? before.light_text + " → " : ""}${nr.light_text}`, nr.light === "green" ? "ok" : "");
      refresh();
    });
  } else if (rm) {
    removeWithUndo(rm.dataset.remove);
  } else if (ed) {
    const card = ed.closest(".res"), box = $(".editor", card), r = S.results.get(ed.dataset.edit);
    if (box.classList.contains("hidden")) { box.innerHTML = editorHTML(r); paintIcons(box); box.classList.remove("hidden"); $("select", box)?.focus(); }
    else box.classList.add("hidden");
  } else if (rr) {
    const card = rr.closest(".res"), box = $(".editor", card), r = S.results.get(rr.dataset.rerun);
    const filters = {}; $$("[data-ef]", box).forEach((s) => { if (s.value !== (r.edit.filters.find((f) => f.key === s.dataset.ef) || {}).value) filters[s.dataset.ef] = s.value; });
    const body = { result_id: r.id, filters };
    const p0 = $("[data-ep='0']", box), p1 = $("[data-ep='1']", box), m = $("[data-em]", box);
    if (p0 && p1) {
      if (p0.value > p1.value) return toast("기간의 시작이 끝보다 늦습니다.", "err");
      if (p0.value !== r.edit.period[0] || p1.value !== r.edit.period[1]) body.period = [p0.value, p1.value];
    }
    if (m && m.value !== r.edit.metric) body.metric = m.value;
    if (!Object.keys(filters).length && !body.period && !body.metric) return toast("바꾼 조건이 없습니다. 값을 하나 이상 바꿔 주세요.", "err");
    await guarded("조건을 바꿔 다시 집계하고 반출 기준을 점검하는 중…", async () => {
      const d = await api("/api/rerun", body);
      box.classList.add("hidden");
      const nr = d.results[0];
      placeResult(nr, card);
      toast(`다시 실행했습니다: 반출 ${nr.light_text}`, nr.light === "green" ? "ok" : "");
      refresh();
    });
  } else if (tb) {
    const w = $(".tblwrap", tb.closest(".res")); w.classList.toggle("hidden");
  } else if (zm) {
    const r = S.results.get(zm.dataset.zoom);
    modal(`<h2 style="font-size:17px">${esc(r.title)}</h2><img class="zoom" src="${r.png}" alt=""><p class="src">${esc(r.source)}</p>`);
  }
});
$("#feed").addEventListener("change", (e) => {
  const id = e.target.dataset.pick; if (!id) return;
  e.target.checked ? S.unselected.delete(id) : S.unselected.add(id);
  renderResultList(S.state.results);
});

function orderedResults(list) {
  const ids = list.map((r) => r.id);
  S.order = S.order.filter((id) => ids.includes(id)).concat(ids.filter((id) => !S.order.includes(id)));
  const by = new Map(list.map((r) => [r.id, r]));
  return S.order.map((id) => by.get(id)).filter((r) => r && !S.removing.has(r.id));
}
function renderResultList(all) {
  const el = $("#resultList");
  const list = orderedResults(all);
  const n = { green: 0, yellow: 0, red: 0 }; list.forEach((r) => n[r.light]++);
  const sel = list.filter((r) => !S.unselected.has(r.id) && r.light !== "red").length;
  $("#p3sum").textContent = list.length ? `${list.length}개 · 넣을 것 ${sel}개` : "";
  if (!list.length) { el.className = "muted"; el.innerHTML = '<p style="font-size:13px">아직 결과가 없습니다. 질문하면 여기에 모입니다.</p>'; return; }
  el.className = "reslist";
  el.innerHTML = `<div class="sum"><span><span class="ldot green"></span> 초록 ${n.green}</span><span><span class="ldot yellow"></span> 노랑 ${n.yellow}</span><span><span class="ldot red"></span> 빨강 ${n.red}</span></div>`
    + list.map((r, i) => `<div class="it ${r.light === "red" ? "out" : ""}"><input type="checkbox" data-sel="${r.id}" ${S.unselected.has(r.id) ? "" : "checked"} aria-label="보고서에 넣기"><span class="ldot ${r.light}"></span><span class="no">${i + 1}</span><a href="#r_${r.id}" title="${esc(r.title)}">${esc(r.title)}</a>
      <span class="mv"><button class="link" data-mv="-1" data-id="${r.id}" ${i ? "" : "disabled"} title="앞으로" aria-label="앞으로">▲</button><button class="link" data-mv="1" data-id="${r.id}" ${i < list.length - 1 ? "" : "disabled"} title="뒤로" aria-label="뒤로">▼</button></span></div>`).join("")
    + `<p class="muted" style="font-size:12px">번호 순서대로 보고서에 실립니다(▲▼로 바꾸기). 빨강 결과는 보고서·신청서에서 자동으로 빠집니다.</p>`;
}
$("#resultList").addEventListener("change", (e) => {
  const id = e.target.dataset.sel; if (!id) return;
  e.target.checked ? S.unselected.delete(id) : S.unselected.add(id);
  const c = $(`[data-pick="${id}"]`); if (c) c.checked = e.target.checked;
});
$("#resultList").addEventListener("click", (e) => {
  const mv = e.target.closest("[data-mv]");
  if (mv) {
    const i = S.order.indexOf(mv.dataset.id), j = i + Number(mv.dataset.mv);
    if (i < 0 || j < 0 || j >= S.order.length) return;
    [S.order[i], S.order[j]] = [S.order[j], S.order[i]];
    renderResultList(S.state.results); return;
  }
  const a = e.target.closest("a[href^='#r_']"); if (!a) return;
  e.preventDefault(); const el = $(a.getAttribute("href"));
  if (el) { el.scrollIntoView({ behavior: "smooth", block: "center" }); el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 1400); }
});
function selectedIds() { return orderedResults(S.state ? S.state.results : []).map((r) => r.id).filter((id) => !S.unselected.has(id)); }

// ---------- ③ 보고서 · ④ 신청서 ----------
$("#btnReport").onclick = () => {
  const ids = selectedIds();
  if (!ids.length) return toast("보고서에 넣을 결과를 먼저 만들거나 골라 주세요.", "err");
  guarded("보고서를 만드는 중(그림·PDF 변환)…", async () => {
    const d = await api("/api/report", { result_ids: ids, title: $("#repTitle").value });
    $("#reportOut").innerHTML = `<div class="outfiles">${d.pdf_url ? `<a href="${d.pdf_url}" target="_blank">${icon("file")}보고서 PDF<small>열기</small></a>` : ""}<a href="${d.html_url}" target="_blank">${icon("file")}보고서 HTML<small>열기·인쇄</small></a></div>
      <button class="ghost sm" id="btnPreview">${icon("file")}여기서 미리보기</button>
      <p class="muted" style="font-size:12px">그림 ${d.pngs.length}장 · 목적(${esc(S.state.purpose)})에 맞춘 목차 · 그림마다 출처 표기. 반출 신청 때 첨부하세요.</p>`;
    paintIcons($("#reportOut"));
    $("#btnPreview").onclick = () => { modal(`<h2>보고서 미리보기</h2><iframe class="preview" src="${d.html_url}" title="보고서 미리보기"></iframe>`); $(".sheet").classList.add("wide"); };
    S.reportDone = true; renderStepper(); toast("보고서를 만들었습니다.", "ok");
  });
};
$("#btnForm").onclick = () => {
  const ids = selectedIds();
  if (!ids.length) return toast("신청서에 넣을 결과를 먼저 만들거나 골라 주세요.", "err");
  guarded("신청서 초안을 쓰는 중…", async () => {
    const d = await api("/api/export-form", { result_ids: ids, note: $("#useNote").value });
    const f = d.draft;
    if (!f.files.length) { $("#formOut").innerHTML = '<p class="warn">반출 가능한 결과가 없습니다. 빨강 결과를 먼저 고쳐 주세요.</p>'; return; }
    $("#formOut").innerHTML = `<p class="notes">센터 반출 신청 화면의 칸 순서대로입니다. [복사]를 눌러 붙여 넣으세요.</p>
      <div class="kv"><b>제목</b></div>${copyBox("fTitle", f.title, 2)}
      <div class="kv"><b>설명</b></div>${copyBox("fDesc", f.description, 7)}
      <div class="kv"><b>활용데이터</b> ${f.datasets.map(esc).join(", ")}</div>
      <div class="kv"><b>파일구분</b> ${esc(f.file_kind)}</div>
      <div class="kv"><b>첨부</b> 그림 ${f.files.length}개 + 보고서 PDF</div>
      <div class="outfiles"><a href="${d.memo_url}" target="_blank">${icon("shield")}반출 점검 메모(첨부용)<small>열기</small></a></div>
      ${f.excluded.length ? `<p class="warn">제외(빨강): ${f.excluded.map(esc).join(", ")}</p>` : ""}
      <p class="muted" style="font-size:12px">${esc(f.note)} 심사는 최대 5일(평균 3일) 걸립니다.</p>`;
    paintIcons($("#formOut"));
    S.formDone = true; renderStepper(); toast("신청서 초안을 만들었습니다.", "ok");
  });
};

$("#btnBundle").onclick = () => {
  const ids = selectedIds();
  if (!ids.length) return toast("묶을 결과를 먼저 만들거나 골라 주세요.", "err");
  guarded("반출 신청 묶음을 만드는 중(보고서 PDF·그림·점검 메모·신청서 초안)…", async () => {
    const d = await api("/api/bundle", { result_ids: ids, title: $("#repTitle").value, note: $("#useNote").value });
    const name = decodeURIComponent(d.zip_url.split("/").pop());
    $("#formOut").insertAdjacentHTML("afterbegin", `<div class="bundle">${icon("box")}<div><b>반출 신청 묶음</b><small>${d.files.length}개 파일: ${d.files.map(esc).join(", ")}</small></div><a href="${d.zip_url}" download="${esc(name)}"><button class="primary sm" tabindex="-1">${icon("down")}내려받기</button></a></div>`);
    paintIcons($("#formOut"));
    S.formDone = true; renderStepper(); toast("반출 신청 묶음을 만들었습니다. 센터 반출 신청 화면에 첨부하세요.", "ok");
  });
};

// ---------- 세션 기록·도움말·단축키 ----------
const EVENT_KO = { purpose: "목적 선택", load: "파일 불러오기", plan: "분석 계획", result: "분석 결과", fix: "반출 고치기", rerun: "조건 바꿔 다시", report: "보고서", bundle: "반출 신청 묶음" };
const LIGHT_KO = { green: "초록", yellow: "노랑", red: "빨강" };
$("#btnLog").onclick = () => guarded("기록을 불러오는 중…", async () => {
  const d = await api("/api/activity");
  const dsName = (id) => ((S.state.datasets || []).find((x) => x.id === id) || {}).name || id;
  const line = (e) => {
    const bits = [];
    if (e.dataset) bits.push(esc(dsName(e.dataset)));
    if (e.tool) bits.push(esc(TOOL_KO[e.tool] || e.tool));
    if (e.light) bits.push(`<span class="ldot ${e.light}"></span>${LIGHT_KO[e.light] || ""}`);
    if (e.files != null) bits.push(`파일 ${e.files}개`);
    if (e.count != null) bits.push(`${e.count}개`);
    if (e.purpose) bits.push(esc(e.purpose));
    if (e.source) bits.push(e.source === "ai" ? "AI 계획" : e.source === "card" ? "질문 카드" : esc(e.source));
    if (e.fix) bits.push(esc(e.fix));
    return `<li class="ev ${esc(e.event)}"><time>${esc((e.time || "").slice(11, 19))}</time><b>${esc(EVENT_KO[e.event] || e.event)}</b><span>${bits.join(" · ")}</span></li>`;
  };
  modal(`<h2>이번 세션 기록</h2><p class="notes">무엇을 했는지만 남깁니다. 지역명·업종명·금액 같은 데이터 값은 기록하지 않으며, 퇴실하면 함께 지워집니다.</p>
    ${d.events.length ? `<ol class="timeline">${d.events.slice().reverse().map(line).join("")}</ol>` : '<p class="muted">아직 기록이 없습니다.</p>'}`);
});
function showHelp() {
  modal(`<h2>혼디 사용법</h2>
    <ol class="howto"><li><b>방문 전 준비</b> — 무엇을 만들지 적으면 받을 데이터와 다운로드 주문서를 만들어 드립니다.</li>
      <li><b>파일 넣기</b> — 센터에서 내려받은 Results_….csv를 끌어다 놓으면 종류·기간을 알아서 정리합니다. 데이터 이름을 누르면 컬럼과 월별 행 수를 볼 수 있습니다.</li>
      <li><b>묻기</b> — 질문 카드를 누르거나 편하게 물어보세요. 실행 전에 무엇을 계산할지 먼저 보여 드립니다.</li>
      <li><b>점검·고치기</b> — 결과마다 반출 신호등이 붙습니다. 노랑·빨강이면 [고치기] 한 번으로 기준에 맞춥니다. [조건 바꿔 다시]로 지역·기간·지표만 바꿔 볼 수 있습니다.</li>
      <li><b>보고서·신청서</b> — 넣을 결과를 고르고 순서를 정한 뒤 보고서·신청서 초안·반출 신청 묶음(ZIP)을 만드세요.</li>
      <li><b>퇴실</b> — 반출 신청을 마쳤으면 [퇴실]로 이 PC의 자료를 지웁니다.</li></ol>
    <h3>단축키</h3>
    <table class="t keys"><tbody>
      <tr><td><kbd>/</kbd></td><td>질문 입력창으로</td></tr>
      <tr><td><kbd>Enter</kbd> · <kbd>Shift</kbd>+<kbd>Enter</kbd></td><td>보내기 · 줄 바꾸기</td></tr>
      <tr><td><kbd>Alt</kbd>+<kbd>1</kbd>~<kbd>4</kbd></td><td>왼쪽 단계 열기(준비·파일·결과물·신청서)</td></tr>
      <tr><td><kbd>?</kbd></td><td>이 도움말</td></tr>
      <tr><td><kbd>Esc</kbd></td><td>창 닫기</td></tr></tbody></table>
    <h3>안심하고 쓰세요</h3>
    <ul><li>계산은 이 PC 안에서만 합니다. AI에는 〔자리표시자〕로 가린 질문만 갑니다(상단 'AI 전송 기록'에서 전부 확인).</li>
      <li>반출 신호등은 예상입니다. 최종 판단은 센터 심사(평균 3일)입니다.</li>
      <li>막히면 센터 운영자에게 '설정·점검' 화면을 보여 주세요.</li></ul>`);
}
$("#btnHelp").onclick = showHelp;
document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "");
  if (e.altKey && /^[1-4]$/.test(e.key)) { e.preventDefault(); openPanel("p" + e.key, true); return; }
  if (typing || !$("#modal").classList.contains("hidden") && e.key !== "?") return;
  if (e.key === "/") { e.preventDefault(); $("#question").focus(); }
  else if (e.key === "?") { e.preventDefault(); showHelp(); }
});
setInterval(() => { if (!$("#offline").classList.contains("hidden")) api("/api/state").then(() => refresh()).catch(() => {}); }, 5000);

// ---------- 기록·설정·퇴실 ----------
$("#btnOutbound").onclick = () => guarded("기록을 불러오는 중…", async () => {
  const d = await api("/api/outbound");
  const u = d.usage;
  modal(`<h2>AI 전송 기록</h2><p>이번 세션에서 외부 AI(OpenAI ${esc(d.model)})로 나간 글 <b>전부</b>입니다. 지역명·업종명·금액 같은 실제 값은 〔자리표시자〕로 가려졌습니다.</p>
    <p class="notes">이번 달 ${u.calls}회 · 토큰 ${u.input_tokens.toLocaleString()}+${u.output_tokens.toLocaleString()} · 약 ${Number(u.krw).toFixed(1)}원 / 한도 ${Number(d.limit_krw).toLocaleString()}원</p>
    ${d.records.length ? d.records.slice().reverse().map((r) => `<div class="oblog"><b>${esc(r.time)}</b> ${r.error ? `<span class="warn">실패: ${esc(r.error)}</span>` : `· 토큰 ${r.input_tokens}+${r.output_tokens} · 약 ${Number(r.krw).toFixed(2)}원`}<pre>${esc(r.user)}</pre>${r.reply ? `<details><summary>AI 응답</summary><pre>${esc(r.reply)}</pre></details>` : ""}</div>`).join("") : '<p class="muted">아직 AI로 보낸 글이 없습니다.</p>'}`);
});
$("#btnSettings").onclick = () => guarded("설치 상태를 점검하는 중…", async () => {
  const [c, st] = await Promise.all([api("/api/selfcheck"), api("/api/state")]);
  const s = st.settings;
  modal(`<h2>설정 · 점검</h2>
    <label class="switch"><input type="checkbox" id="sAgg" ${s.send_aggregates ? "checked" : ""}><span><b>AI 해설에 집계값 보내기</b><br><small class="muted">반출 기준을 충족(초록)한 30행 이하 표만 보냅니다. 센터 심의 전까지 꺼 두는 것을 권장합니다.</small></span></label>
    <label class="switch"><input type="checkbox" id="sDel" ${s.auto_delete ? "checked" : ""}><span><b>퇴실 시 자료 삭제</b><br><small class="muted">불러온 파일·결과·AI 기록을 지웁니다(센터 운영 원칙).</small></span></label>
    <label class="switch"><input type="checkbox" id="sKeep" ${s.keep_results ? "checked" : ""}><span><b>결과물만 보존</b><br><small class="muted">삭제할 때 결과 그림·보고서 폴더만 남깁니다.</small></span></label>
    <label class="switch"><input type="checkbox" id="sBig" ${document.body.classList.contains("big") ? "checked" : ""}><span><b>큰 글씨</b><br><small class="muted">화면 글자를 크게 합니다.</small></span></label>
    <h3>설치 점검</h3><ul class="checks">${c.checks.map((x) => `<li class="${x.level}"><b>${x.level === "ok" ? "✔ 정상" : x.level === "warn" ? "! 확인" : "✖ 문제"}</b> ${esc(x.name)} — ${esc(x.detail)}${x.fix ? `<br><small class="muted">${esc(x.fix)}</small>` : ""}</li>`).join("")}</ul>`);
  const save = async () => { await api("/api/settings", { send_aggregates: $("#sAgg").checked, auto_delete: $("#sDel").checked, keep_results: $("#sKeep").checked }); toast("설정을 바꿨습니다."); refresh(); };
  ["#sAgg", "#sDel", "#sKeep"].forEach((id) => $(id).addEventListener("change", save));
  $("#sBig").addEventListener("change", (e) => { document.body.classList.toggle("big", e.target.checked); try { localStorage.setItem("big", e.target.checked ? "1" : ""); } catch (err) { /* 무시 */ } });
});
$("#btnEnd").onclick = () => {
  const st = S.state || { results: [], datasets: [] };
  modal(`<h2>퇴실하고 세션을 지울까요?</h2>
    <p>반출 신청을 마쳤는지 확인하세요. 아래 자료가 이 PC에서 <b>삭제</b>됩니다.</p>
    <ul><li>혼디에 끌어다 놓은 파일 사본과 불러온 데이터</li><li>분석 결과 ${st.results.length}개와 보고서·그림</li><li>AI 전송 기록 ${st.outbound_count || 0}건</li></ul>
    ${(st.external_files || []).length ? `<p class="warn">'폴더에서 찾기'로 읽은 원본 CSV는 그 폴더에 그대로 있습니다. 퇴실 전에 직접 지워 주세요:<br>${st.external_files.map((f) => `${esc(f.folder)} (${f.count}개)`).join("<br>")}</p>` : ""}
    ${!S.formDone && st.results.length ? '<p class="warn">아직 반출 신청서 초안을 만들지 않았습니다.</p>' : ""}
    <div class="row"><button class="danger" id="btnEndOk">${icon("trash")}삭제하고 새로 시작</button><button class="ghost" id="btnEndNo">돌아가기</button></div>`);
  $("#btnEndNo").onclick = closeModal;
  $("#btnEndOk").onclick = () => guarded("지우는 중…", async () => {
    const d = await api("/api/session/end", {});
    closeModal();
    S.results.clear(); S.unselected.clear(); S.removing.clear(); S.order = []; S.prepDone = S.reportDone = S.formDone = false;
    S.focus = { area: "", biz: "" }; S.focusKey = ""; S.asked.clear(); S.explore = false; S.recent = {};
    $("#feed").innerHTML = "";
    ["#prepOut", "#reportOut", "#formOut", "#scanOut", "#hubOut", "#uploadOut"].forEach((s) => ($(s).innerHTML = ""));
    toast(`파일 ${d.ended.deleted}개를 지웠습니다. 수고하셨습니다!`, "ok"); refresh();
  });
};

async function boot() {
  paintIcons();
  try { if (localStorage.getItem("big")) document.body.classList.add("big"); } catch (e) { /* 무시 */ }
  await refresh();
  if (S.state.datasets.length) $("#p1").classList.remove("open");
  else $("#p1").classList.add("open");
  if (location.hash.startsWith("#tour=")) { const s = document.createElement("script"); s.src = "/web/tour.js"; document.body.appendChild(s); return; }
  try {
    const c = await api("/api/selfcheck");
    const fails = c.checks.filter((x) => x.level === "fail");
    if (fails.length) { const b = $("#banner"); b.classList.remove("hidden"); b.classList.add("fail"); b.innerHTML = "설치 점검에서 문제가 발견되었습니다: " + fails.map((x) => `<b>${esc(x.name)}</b> ${esc(x.fix || x.detail)}`).join(" · "); }
  } catch (e) { /* 점검 실패는 무시 */ }
}
boot();
