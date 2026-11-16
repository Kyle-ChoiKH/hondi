"""목적별 보고서(HTML → PDF). PDF는 Windows 기본 Edge(없으면 Chrome)의 헤드리스 인쇄로 만든다."""
from __future__ import annotations

import html
import os
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from .catalog import Catalog
from .charts import render
from .guard import FINAL_NOTE, LIGHT_TEXT
from .narrate import caveats, fmt_value, headline, narrate, source_line

SECTIONS = {
    "사업계획서": ["시장 규모와 추이", "고객 특성", "이용 시간대·요일", "경쟁·입지 비교", "시사점"],
    "현황자료": ["개요", "주요 지표", "변화", "유의사항"],
    "논문": ["데이터와 변수", "기술통계", "분석 결과", "한계와 인용"],
    "자유": ["분석 결과", "요약"],
}
TIME_LIKE = {"time", "week", "base_hour", "day_of_week"}
CUSTOMER = {"user_type", "user_group", "age", "age_band", "sex", "tour_type"}
PLACE = {"bjd", "dstrct_se", "city", "emd_nm", "bjd_nm", "area_type"}


def _section(purpose: str, r) -> str:
    by = set(r.step.by)
    t = r.step.tool
    if purpose == "사업계획서":
        if by & TIME_LIKE:
            return "이용 시간대·요일"
        if by & CUSTOMER:
            return "고객 특성"
        if by & PLACE or t == "compare":
            return "경쟁·입지 비교"
        return "시장 규모와 추이"
    if purpose == "현황자료":
        if t == "profile":
            return "개요"
        if t in ("contribution", "yoy"):
            return "변화"
        return "주요 지표"
    if purpose == "논문":
        return "기술통계" if t == "describe" else "분석 결과"
    return "분석 결과"


def _summary_section(purpose: str) -> str:
    return SECTIONS[purpose][-1]


def _table(r, cat: Catalog) -> str:
    did = r.step.dataset
    cols = r.dims + r.measures
    head = "".join(f"<th>{html.escape(cat.label(did, c) if c in r.dims else _mlabel(c, cat, did))}</th>" for c in cols)
    body = []
    for i, row in enumerate(r.rows[:30]):
        cells = [f"<td>{html.escape(str(row.get(d)))}</td>" for d in r.dims]
        for m in r.measures:
            if (i, m) in r.masked:
                cells.append('<td class="mask">10 미만(가림)</td>')
            elif m == "값" and row.get("_applied"):
                cells.append(f'<td class="n">{row.get(m):.1f}%</td>')
            else:
                cells.append(f'<td class="n">{html.escape(fmt_value(row.get(m), m if m != "값" else r.step.metric, cat, did))}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    more = f'<p class="sub">상위 30행만 표시(전체 {len(r.rows)}행)</p>' if len(r.rows) > 30 else ""
    return f'<table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>{more}'


def _mlabel(m: str, cat: Catalog, did: str) -> str:
    names = {"rank": "순위", "yoy_pct": "전년 대비(%)", "diff_pct": "차이(%)", "change_diff": "증감",
             "contrib_pct": "기여율(%)", "mean": "평균", "median": "중앙값", "min": "최소", "max": "최대",
             "std": "표준편차", "값": "값"}
    if m in names:
        return names[m]
    if m.endswith("_pct"):
        return cat.label(did, m[:-4]) + " 비중(%)"
    if m.endswith("_a") or m.endswith("_b"):
        return cat.label(did, m[:-2]) + (" (가)" if m.endswith("_a") else " (나)")
    return cat.label(did, m)


CSS = """
body{font-family:'Pretendard','Malgun Gothic','맑은 고딕',sans-serif;color:#191f28;margin:0;padding:28px 40px;font-size:13px;line-height:1.6}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;border-bottom:2px solid #3182f6;padding-bottom:4px;margin-top:28px}
h3{font-size:14px;margin:18px 0 6px}.sub{color:#6b7684;font-size:12px}
figure{margin:10px 0 18px;page-break-inside:avoid}figure img{width:100%;border:1px solid #e3e7ec}
figcaption{font-size:11px;color:#6b7684}table{border-collapse:collapse;width:100%;margin:6px 0;font-size:12px}
th,td{border:1px solid #d5dbe1;padding:4px 6px;text-align:left}th{background:#f1f4f7}td.n{text-align:right}
td.mask{color:#6b7684;background:repeating-linear-gradient(45deg,#f6f7f9,#f6f7f9 4px,#eceff2 4px,#eceff2 8px)}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;color:#fff}
.green{background:#0d9f61}.yellow{background:#e09400}.red{background:#e42939}
.hl{background:#e8f3ff;border-radius:8px;padding:8px 12px;font-size:14px;font-weight:700;margin:6px 0 8px}ul{margin:4px 0;padding-left:20px}.note{background:#f4f7f9;border-left:3px solid #3182f6;padding:8px 12px}
@page{size:A4;margin:14mm}
"""


def build_report(purpose: str, results: list, assessments: list, catalog: Catalog, out_dir: Path, meta: dict,
                 make_pdf: bool = True, demo: bool = False) -> dict:
    purpose = purpose if purpose in SECTIONS else "자유"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    keep = [(r, a) for r, a in zip(results, assessments) if a.light != "red"]
    dropped = [r for r, a in zip(results, assessments) if a.light == "red"]
    sections = {s: [] for s in SECTIONS[purpose]}
    pngs, findings, sources = [], [], {}
    for k, (r, a) in enumerate(keep, 1):
        png = render(r, catalog, out_dir / f"그림{k:02d}_{r.id}.png", demo=demo)
        pngs.append(png)
        sents = narrate(r, catalog)
        if sents:
            findings.append(sents[0])
        sources[source_line(r, catalog).replace("출처: ", "")] = caveats(r, catalog, demo)
        hl = headline(r, catalog) if purpose != "논문" else ""
        block = (f'<h3>{html.escape(r.title)} <span class="badge {a.light}">{LIGHT_TEXT[a.light]}</span></h3>'
                 + (f'<p class="hl">{html.escape(hl)}</p>' if hl else "")
                 + f'<figure><img src="{png.name}" alt="{html.escape(r.title)}">'
                 f'<figcaption>{html.escape(source_line(r, catalog))}</figcaption></figure>'
                 f'<ul>{"".join(f"<li>{html.escape(s)}</li>" for s in sents)}</ul>'
                 + (_table(r, catalog) if "no_numbers" not in r.notes else "")
                 + "".join(f'<p class="sub">※ {html.escape(c)}</p>' for c in caveats(r, catalog, demo)))
        sections[_section(purpose, r)].append(block)
    summ = _summary_section(purpose)
    if purpose == "논문":
        sections["데이터와 변수"].append(_variables(keep, catalog))
    sections[summ].append("<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in findings) + "</ul>"
                          if findings else "<p>요약할 결과가 없습니다.</p>")
    if purpose == "논문":
        sections["한계와 인용"].append(
            "<p>인용 표기: " + "; ".join(html.escape(f"제주빅데이터센터, {s}") for s in sources) + "</p>")
    title = meta.get("title") or f"{purpose} 분석 자료"
    parts = [f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
             f"<style>{CSS}</style></head><body>",
             f"<h1>{html.escape(title)}</h1><p class='sub'>작성일 {date.today():%Y-%m-%d} · 혼디(제주빅데이터센터 분석 Agent)"
             f"{' · 작성자 ' + html.escape(meta['author']) if meta.get('author') else ''}</p>"]
    if demo:
        parts.append("<p class='note'>이 보고서는 예시(가상) 데이터로 만든 것으로 실제 센터 데이터가 아닙니다.</p>")
    for i, (name, blocks) in enumerate(sections.items(), 1):
        parts.append(f"<h2>{i}. {html.escape(name)}</h2>" + ("".join(blocks) or "<p class='sub'>해당 결과 없음</p>"))
    parts.append("<h2>데이터 출처와 한계</h2><ul>")
    for s, cv in sources.items():
        parts.append(f"<li>제주빅데이터센터, {html.escape(s)}" + (" — " + html.escape(" ".join(cv)) if cv else "") + "</li>")
    parts.append("</ul><p class='sub'>10 미만 수치는 반출 기준에 따라 가리거나 묶었습니다. " + FINAL_NOTE + "</p>")
    if dropped:
        parts.append("<p class='note'>보고서에서 뺀 결과(반출 기준 미충족): " +
                     ", ".join(html.escape(r.title) for r in dropped) + "</p>")
    parts.append("</body></html>")
    h = out_dir / "보고서.html"
    h.write_text("".join(parts), encoding="utf-8")
    pdf = to_pdf(h, out_dir / "보고서.pdf") if make_pdf else None
    return {"html": h, "pdf": pdf, "pngs": pngs}


def _variables(keep, cat: Catalog) -> str:
    rows, seen = [], set()
    for r, _ in keep:
        did = r.step.dataset
        for c in [*r.step.by, r.step.metric, *r.step.filters]:
            if (did, c) in seen:
                continue
            seen.add((did, c))
            col = cat.column(did, c)
            rows.append(f"<tr><td>{html.escape(c)}</td><td>{html.escape(cat.label(did, c))}</td>"
                        f"<td>{html.escape(col['role'] if col else '가상 묶음')}</td>"
                        f"<td>{html.escape((col or {}).get('note', '')[:60])}</td><td>{html.escape(cat.name(did))}</td></tr>")
    return ("<table><thead><tr><th>변수</th><th>이름</th><th>유형</th><th>설명</th><th>데이터</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def find_browser():
    cands = [os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
             os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
             os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
             os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")]
    for c in cands:
        if c and Path(c).exists():
            return c
    return shutil.which("msedge") or shutil.which("chrome")


def to_pdf(html_path: Path, pdf_path: Path):
    exe = find_browser()
    if not exe:
        return None
    pdf_path = Path(pdf_path).resolve()  # 브라우저는 상대 경로를 자기 폴더 기준으로 해석한다
    if pdf_path.exists():
        pdf_path.unlink()
    with tempfile.TemporaryDirectory() as prof:
        try:
            subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--user-data-dir={prof}", f"--print-to-pdf={pdf_path}", Path(html_path).resolve().as_uri()],
                           timeout=60, capture_output=True)
        except (subprocess.TimeoutExpired, OSError):
            return None
    return pdf_path if pdf_path.exists() and pdf_path.stat().st_size > 0 else None
