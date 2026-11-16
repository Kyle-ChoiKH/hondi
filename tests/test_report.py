import shutil
from pathlib import Path

import pytest

from app.export_form import check_memo, draft
from app.guard import apply_suppression, assess
from app.model import Step
from app.report import build_report, find_browser
from app.tools import run_step


def results(ws, cat):
    rs = [
        run_step(ws, cat, Step("trend", "1-08", "use_amt", ["base_year_month"], {"bjd": "애월읍"})),
        run_step(ws, cat, Step("share", "1-08", "use_cnt", ["user_type"], {"bjd": "애월읍"})),
        apply_suppression(run_step(ws, cat, Step("share", "1-08", "use_cnt", ["age"], {"bjd": "애월읍"},
                                                 {"period": ["2024-07", "2024-07"]}))),
        run_step(ws, cat, Step("rank", "1-08", "use_amt", ["bjd"], {"biz_nm": "한식 음식점업"})),
    ]
    red = run_step(ws, cat, Step("rank", "1-08", "use_amt", ["age"], {"bjd": "애월읍"},
                                 {"period": ["2024-07", "2024-07"]}))
    rs.append(red)
    return rs, [assess(r, cat) for r in rs]


def test_report_html_has_sections_and_sources(small_ws, cat, tmp_path):
    rs, ass = results(small_ws, cat)
    out = build_report("사업계획서", rs, ass, cat, tmp_path, {"title": "애월읍 국수집 시장 분석"}, make_pdf=False)
    html = out["html"].read_text(encoding="utf-8")
    for h in ["시장 규모와 추이", "고객 특성", "이용 시간대·요일", "경쟁·입지 비교", "시사점"]:
        assert h in html
    assert html.count("출처: 제주빅데이터센터") == len(out["pngs"]) == 4
    assert "데이터 출처와 한계" in html and "최종 반출 여부는 센터 심사" in html


def test_red_results_excluded(small_ws, cat, tmp_path):
    rs, ass = results(small_ws, cat)
    assert ass[-1].light == "red"
    out = build_report("현황자료", rs, ass, cat, tmp_path, {}, make_pdf=False)
    html = out["html"].read_text(encoding="utf-8")
    assert "보고서에서 뺀 결과" in html
    assert len(out["pngs"]) == 4


@pytest.mark.skipif(find_browser() is None, reason="Edge/Chrome 없음")
def test_pdf_when_browser_available(small_ws, cat, tmp_path):
    rs, ass = results(small_ws, cat)
    out = build_report("논문", rs[:2], ass[:2], cat, tmp_path, {})
    assert out["pdf"] and out["pdf"].exists() and out["pdf"].read_bytes()[:4] == b"%PDF"


def test_draft_mentions_processing(small_ws, cat):
    rs, ass = results(small_ws, cat)
    d = draft(rs, ass, cat, "사업계획서", "애월읍 국수집 창업 사업계획서")
    assert "삭제처리" in d["description"]
    assert "애월읍 국수집 창업 사업계획서" in d["description"]
    assert d["file_kind"] == "분석결과"
    assert "카드 이용 현황(읍면동)_v02" in d["datasets"]
    assert all(f["light"] != "red" for f in d["files"])
    assert len(d["files"]) == 4


def test_draft_groups_by_dataset(small_ws, cat):
    rs, ass = results(small_ws, cat)
    d = draft(rs, ass, cat, "현황자료", "")
    assert len(d["groups"]) == 1 and len(d["groups"][0]["files"]) == 4


def test_check_memo(small_ws, cat):
    rs, ass = results(small_ws, cat)
    memo = check_memo(rs[:4], ass[:4], cat)
    assert "역산" in memo and "가린 칸" in memo and "<table" in memo


@pytest.mark.skipif(find_browser() is None, reason="Edge/Chrome 없음")
def test_to_pdf_accepts_relative_paths(tmp_path, monkeypatch):
    from app.report import to_pdf
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.html").write_text("<html><body>가나다</body></html>", encoding="utf-8")
    out = to_pdf(Path("a.html"), Path("a.pdf"))
    assert out is not None and (tmp_path / "a.pdf").read_bytes()[:4] == b"%PDF"


def test_draft_file_names_match_report_pngs(small_ws, cat, tmp_path):
    rs, ass = results(small_ws, cat)
    out = build_report("사업계획서", rs, ass, cat, tmp_path, {}, make_pdf=False)
    d = draft(rs, ass, cat, "사업계획서", "")
    assert [f["name"] for f in d["files"]] == [p.name for p in out["pngs"]]  # (M6)


def test_check_memo_has_items_center_asked_for(small_ws, cat):
    # 게시판 답변(11/15): 원본 데이터명, 분석·가공 방법, 10 미만 비식별 처리, 역산 점검, 활용 목적
    rs, ass = results(small_ws, cat)
    html = check_memo(rs, ass, cat, purpose="사업계획서", note="애월읍 국수집 창업")
    for word in ("원본 데이터", "분석 방법", "적용 조건", "10 미만 처리", "역산 점검", "활용 목적", "애월읍 국수집 창업", "추이"):
        assert word in html, word


def test_report_puts_one_line_summary_above_each_figure_except_papers(small_ws, cat, tmp_path):
    from app.narrate import headline
    rs, ass = results(small_ws, cat)
    out = build_report("사업계획서", rs, ass, cat, tmp_path / "b", {"title": "t"}, make_pdf=False)
    html = out["html"].read_text(encoding="utf-8")
    assert html.count('class="hl"') == len(out["pngs"]) and headline(rs[0], cat).split(".")[0] in html
    paper = build_report("논문", rs, ass, cat, tmp_path / "p", {"title": "t"}, make_pdf=False)
    assert 'class="hl"' not in paper["html"].read_text(encoding="utf-8")   # 논문은 해요체 요약을 넣지 않음


def test_check_memo_asks_to_link_conditions_to_plan(small_ws, cat):
    # 게시판 답변(11/15, 원본 한 행 문의): 조건이 활용계획과 관련 있는지, 여러 데이터면 데이터별 활용 사유까지 심사
    rs, ass = results(small_ws, cat)
    html = check_memo(rs, ass, cat, purpose="사업계획서", note="애월읍 국수집 창업")
    assert "조건과 활용 계획" in html and "애월읍" in html and "☐" in html
    assert "데이터별 활용 내용" in html and cat.name(rs[0].step.dataset) in html
