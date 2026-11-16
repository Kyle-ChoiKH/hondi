// 자동 시연(#tour=장면). 평가자 시연·매뉴얼 화면 캡처용. 예시(가상) 데이터만 쓴다.
// 캡처가 애니메이션 중간(반투명)에 찍히지 않도록 시연에서는 움직임을 끈다.
document.head.insertAdjacentHTML("beforeend", "<style>*,*::before,*::after{animation:none!important;transition:none!important}</style>");
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(sel, ms = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { const el = document.querySelector(sel); if (el) return el; await wait(150); }
  throw new Error("시연: " + sel + " 없음");
}
async function freshDemo() {
  await api("/api/session/end", {});
  await api("/api/purpose", { purpose: "사업계획서" });
  await api("/api/demo", {});
  $("#p1").classList.remove("open");
  await refresh();
}
// 헤드리스 캡처는 스크롤 위치를 반영하지 못해, 스크롤 대신 위쪽 내용을 숨긴다.
function focus(...sels) { sels.forEach((x) => $$(x).forEach((e) => (e.style.display = "none"))); window.scrollTo(0, 0); }
async function cardFlow(card, values) {
  askCard(card);
  await until(".turn:last-child .btn-run");
  for (const [k, v] of Object.entries(values)) { const el = $(`.turn:last-child [data-need="${k}"]`); if (el) el.value = v; }
  $(".turn:last-child .btn-run").click();
  await until(".turn:last-child .res");
  await wait(400);
}
const V = { bjd: "애월읍", biz_nm: "한식 음식점업" };
const YELLOW = { purpose: "현황자료", source: "card", steps: [{ tool: "rank", dataset: "1-08", metric: "use_amt", by: ["user_type"], filters: { bjd: "우도면", biz_nm: "한식 음식점업" }, options: { period: ["2026-06", "2026-06"], top: 10 } }] };

async function setFocus(area, biz) {  // 관심 조건 고르기(사람이 고르는 것과 같은 이벤트)
  await until("#focusArea option[value='" + area + "']");
  $("#focusArea").value = area; $("#focusArea").dispatchEvent(new Event("change"));
  $("#focusBiz").value = biz; $("#focusBiz").dispatchEvent(new Event("change"));
}

const scenes = {
  async start() { await api("/api/session/end", {}); await api("/api/purpose", { purpose: "사업계획서" }); await refresh(); $("#p1").classList.remove("open"); },
  async home() { await freshDemo(); await setFocus("애월읍", "한식 음식점업"); $$(".toast").forEach((t) => t.remove()); },
  async easy() {
    await freshDemo();
    await setFocus("애월읍", "한식 음식점업");
    $$(".toast").forEach((t) => t.remove());
    askCard("biz_customers");
    await until(".turn:last-child .next");
    await wait(400);
    focus(".msg.user", ".msg.agent");
  },
  async ask() {
    await freshDemo();
    $("#question").value = "애월읍 한식 음식점업 손님은 주로 누구이고 언제 오나요?";
    $("#btnAsk").click();
    await until(".turn:last-child .btn-run");
    await wait(300);
    window.scrollTo(0, 0);
  },
  async results() {
    await freshDemo();
    await cardFlow("biz_customers", V);
    focus(".msg.agent");
  },
  async guard() {
    await freshDemo();
    const d = await api("/api/run", { plan: YELLOW, values: {} });
    showResults(d.results, "우도면 한식 음식점업 6월 이용자 순위", "말로 묻기");
    await refresh();
    window.scrollTo(0, 0);
  },
  async fixed() {
    await scenes.guard();
    (await until("[data-fix^='rollup']")).click();
    await until(".res .badge.green");
    await wait(500);
    window.scrollTo(0, 0);
  },
  async export() {
    await freshDemo();
    await cardFlow("biz_trend", V);
    await cardFlow("biz_customers", V);
    $("#p2").classList.remove("open"); $("#p3").classList.add("open"); $("#p4").classList.add("open");
    $("#repTitle").value = "애월읍 한식 음식점 시장 분석";
    $("#useNote").value = "애월읍 국수집 창업 사업계획서";
    $("#btnForm").click();
    await until("#fDesc");
    S.reportDone = true; renderStepper();
    focus(".msg.agent", ".msg.user");
  },
  async prep() {
    await freshDemo();
    $("#p1").classList.add("open"); $("#p2").classList.remove("open");
    $("#prepQ").value = "애월읍에 국수집을 내려고 사업계획서를 씁니다";
    $("#prepArea").value = "애월읍";
    $("#btnPrep").click();
    await until("#reqText");
    $("#p1 details").open = true;
    $("#btnHub").click();
    await until("#hubOut .spark");
    window.scrollTo(0, 0);
  },
  async dataset() {
    await freshDemo();
    openDataset("1-08");
    await until("#modalBody .monthbars");
  },
  async rerun() {
    await freshDemo();
    await cardFlow("biz_trend", V);
    $(".turn:last-child [data-edit]").click();
    const ed = await until(".turn:last-child .editor select");
    $(".turn:last-child [data-ef='bjd']").value = "노형동";
    $(".turn:last-child [data-rerun]").click();
    await until(".turn:last-child .res:nth-of-type(2)");
    await wait(400);
    $(".turn:last-child .res [data-edit]").click();
    $("#p2").classList.remove("open"); $("#p3").classList.add("open");
    focus(".msg.agent", ".msg.user");
  },
  async outbound() {
    await scenes.ask();
    $("#btnOutbound").click();
    await until(".oblog");
  },
};

(async () => {
  const name = location.hash.replace("#tour=", "");
  try { await (scenes[name] || scenes.home)(); } catch (e) { console.error(e); }
  document.title = "TOUR_DONE";
})();
