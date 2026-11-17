"""반출 신청서 초안과 점검 메모. 센터 시스템의 반출 신청 화면(제목·설명·활용데이터·파일구분·첨부)에 붙여 넣을 문장을 만든다."""
from __future__ import annotations

import html

from .catalog import Catalog
from .guard import FINAL_NOTE, LIGHT_TEXT
from .tools import TOOLS

USE = {"사업계획서": "사업계획서의 시장분석 근거자료", "현황자료": "기관 현황보고 자료",
       "논문": "연구 논문의 분석 결과", "자유": "내부 검토 자료"}


def draft_text(d: dict) -> str:
    """센터 반출 신청 화면의 칸 순서대로 붙여 넣을 수 있는 글."""
    lines = ["[반출 신청서 초안] 센터 반출 신청 화면의 칸에 그대로 붙여 넣으세요.", "",
             f"제목: {d['title']}", "", f"설명: {d['description']}", "",
             f"활용데이터: {', '.join(d['datasets'])}", f"파일구분: {d['file_kind']}",
             "첨부: " + ", ".join([f["name"] for f in d["files"]] + ["보고서.pdf", "반출점검메모.html"])]
    if d.get("excluded"):
        lines.append("제외(반출 기준 미충족): " + ", ".join(d["excluded"]))
    lines += ["", f"※ {d['note']}"]
    return "\r\n".join(lines) + "\r\n"


def processing(r, cat: Catalog) -> list:
    out = []
    for n in r.notes:
        if n == "suppressed":
            out.append("10 미만 칸 삭제처리(역산 방지를 위한 추가 가림 포함)")
        elif n.startswith("rollup:"):
            a, b = n[7:].split(">")
            out.append(f"범주처리({cat.label(r.step.dataset, a)} → {cat.label(r.step.dataset, b)} 상위 단위 재집계)")
        elif n == "to_share":
            out.append("비율 변환(응용집계)")
        elif n == "no_numbers":
            out.append("그림에서 수치 미표시")
    if not out:
        out.append("단순집계(10 미만 칸 없음 확인)" if r.agg_kind == "simple" else "응용집계(비율·순위 등)")
    return out


def draft(results: list, assessments: list, catalog: Catalog, purpose: str, user_note: str) -> dict:
    keep = [(r, a) for r, a in zip(results, assessments) if a.light != "red"]
    groups = {}
    for r, a in keep:
        groups.setdefault((r.step.dataset,), []).append((r, a))
    use = user_note.strip() or USE.get(purpose, USE["자유"])

    def desc(items):
        tools = "·".join(dict.fromkeys(TOOLS[r.step.tool] for r, _ in items))
        procs = "; ".join(dict.fromkeys(p for r, _ in items for p in processing(r, catalog)))
        contents = ", ".join(r.title for r, _ in items)
        names = ", ".join(dict.fromkeys(catalog.name(r.step.dataset) +
                                        (f"({r.period[0]}~{r.period[1]})" if r.period[0] else "") for r, _ in items))
        return (f"혼디(센터 PC 분석 Agent, DuckDB 집계)로 {names} 데이터를 {tools} 분석한 후 {procs}로 가공하여 "
                f"[{contents}]의 그림·보고서를 작성하였고, {purpose} 작성 및 {use}에 활용하고자 합니다. "
                f"원본 행이나 발췌 데이터는 포함하지 않았습니다.")

    files = [{"name": f"그림{k:02d}_{r.id}.png", "result_id": r.id, "title": r.title, "light": a.light}
             for k, (r, a) in enumerate(keep, 1)]  # 보고서 폴더의 그림 파일명과 같게
    out_groups = [{"datasets": [catalog.name(k[0])], "files": [f for f in files if f["result_id"] in {r.id for r, _ in v}],
                   "description": desc(v)} for k, v in groups.items()]
    datasets = list(dict.fromkeys(catalog.name(r.step.dataset) for r, _ in keep))
    return {"title": f"{purpose} 작성을 위한 {', '.join(datasets)} 분석 결과 반출" if datasets else "",
            "description": desc(keep) if keep else "", "datasets": datasets, "file_kind": "분석결과",
            "files": files, "groups": out_groups, "note": FINAL_NOTE,
            "excluded": [r.title for r, a in zip(results, assessments) if a.light == "red"]}


def _conditions(r, cat: Catalog) -> str:
    did = r.step.dataset
    parts = [f"{cat.label(did, k)}={v}" for k, v in r.step.filters.items()]
    fb = (r.step.options or {}).get("filters_b") or {}
    if fb:
        parts.append("비교: " + ", ".join(f"{cat.label(did, k)}={v}" for k, v in fb.items()))
    if r.period and r.period[0]:
        parts.append(f"기간 {r.period[0]}~{r.period[1]}")
    if r.step.by:
        parts.append("구분: " + ", ".join(cat.label(did, b) for b in r.step.by))
    return " · ".join(parts) or "조건 없음"


def check_memo(results: list, assessments: list, catalog: Catalog, purpose: str = "", note: str = "") -> str:
    """반출 신청 첨부용 점검 메모. 게시판 답변(2026-11-15)이 권한 항목을 담는다:
    원본 데이터명, 분석·가공 방법, 10 미만 비식별 처리 내역, 역산 가능성 점검, 활용 목적."""
    rows = []
    for r, a in zip(results, assessments):
        per_col = {m: sum(1 for i, mm in r.masked if mm == m) for m in r.measures}
        n_cells = {m: sum(1 for x in r.rows if x.get(m) is not None) for m in r.measures}
        risky = [m for m, v in per_col.items() if v == 1 and n_cells[m] > 1]
        reverse = ("가린 칸이 있는 열은 2칸 이상 가림, 비교·증감은 해당 행의 차이·기여율도 가림 → 합계·세부값으로 역산 불가"
                   if r.masked and not risky else "가린 칸 없음 — 10 미만 칸이 없어 역산 대상 없음" if not r.masked
                   else "가린 칸이 하나뿐인 열이 있음 → 역산 가능, 추가 처리 필요")
        rows.append(
            f"<tr><td>{html.escape(r.title)}</td><td>{html.escape(catalog.name(r.step.dataset))}</td>"
            f"<td>{html.escape(TOOLS.get(r.step.tool, r.step.tool))} · {a.kind_label}</td>"
            f"<td>{html.escape(_conditions(r, catalog))}</td>"
            f"<td>{html.escape('; '.join(processing(r, catalog)))}</td>"
            f"<td>가린 칸 {len(r.masked)}개 (바탕 건수·최종 값 모두 10 이상인지 확인)</td><td>{reverse}</td>"
            f"<td>{LIGHT_TEXT[a.light]}</td></tr>")
    use = (note.strip() or USE.get(purpose, USE["자유"])) if (purpose or note) else "(반출 신청서에 적은 활용 목적)"
    datasets = list(dict.fromkeys(catalog.name(r.step.dataset) for r in results))
    # 게시판 답변(11/15): 조건이 활용계획과 관련 있는지, 여러 데이터면 데이터별 활용 사유까지 심사한다
    sent = [r for r, a in zip(results, assessments) if a.light != "red"]  # 빨강은 신청서에서 빠지므로 활용 내용에도 넣지 않는다
    conds = list(dict.fromkeys(c for r in sent for c in [_conditions(r, catalog)] if c and c not in ("-", "조건 없음")))
    by_ds = {}
    for r in sent:
        by_ds.setdefault(catalog.name(r.step.dataset), []).append(r.title)
    plan = ("<h3>조건과 활용 계획의 관계(신청 전에 확인)</h3><ul>"
            + "".join(f"<li>☐ {html.escape(c)} — 이 조건이 활용 목적에 필요한 이유를 신청서 설명 칸에 적었습니다.</li>" for c in conds)
            + "<li>☐ 조건을 쓰지 않아도 같은 목적을 이룰 수 있다면 조건을 넓혀 다시 분석했습니다.</li></ul>"
            "<h3>데이터별 활용 내용</h3><ul>"
            + "".join(f"<li><b>{html.escape(d)}</b>: {html.escape(', '.join(ts))}</li>" for d, ts in by_ds.items()) + "</ul>")
    return ("<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>반출 점검 메모</title>"
            "<style>body{font-family:'Malgun Gothic',sans-serif;font-size:12px;padding:20px}"
            "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:4px 6px;text-align:left;vertical-align:top}"
            "th{background:#f1f4f7}.kv b{display:inline-block;min-width:90px}</style></head><body><h2>반출 점검 메모</h2>"
            "<p>제주빅데이터센터 데이터 반출 기준(2026.09.01 개정)과 대회 게시판 안내(2026.11.15)에 따라 결과물마다 "
            "10 미만 처리와 역산 가능성을 점검한 내역입니다.</p>"
            f"<p class='kv'><b>활용 목적</b> {html.escape((purpose + ' — ') if purpose else '')}{html.escape(use)}</p>"
            f"<p class='kv'><b>원본 데이터</b> {html.escape(', '.join(datasets))}</p>"
            "<p class='kv'><b>분석 방법</b> 혼디(센터 PC 로컬 Agent)가 DuckDB로 집계. 외부 AI에는 데이터 값을 보내지 않음. "
            "원본 행·발췌는 결과물에 포함하지 않음.</p>"
            "<table><thead><tr><th>결과물</th><th>원본 데이터</th><th>분석 방법·집계 유형</th><th>적용 조건</th><th>가공 처리</th>"
            "<th>10 미만 처리</th><th>역산 점검</th><th>판정(예상)</th></tr></thead><tbody>" + "".join(rows) +
            f"</tbody></table>{plan}<p>{FINAL_NOTE}</p></body></html>")
