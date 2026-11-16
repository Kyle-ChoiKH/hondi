from app.guard import apply_fix, apply_suppression, assess
from app.model import Result, Step
from app.tools import run_step


def mk(rows, did="1-08", by=("bjd",), measures=("use_amt",), kind="simple"):
    step = Step("rank", did, measures[0], list(by), {})
    return Result("r1", "t", step, list(by), list(measures), rows, kind, ("2025-07", "2025-07"))


def row(name, v, n, nr=5):
    return {"bjd": name, "use_amt": v, "_n_rows": nr, "_n_count": n}


def test_green_for_public_dataset(cat):
    r = mk([{"bus_station_name": "a", "user_count": 3, "_n_rows": 1, "_n_count": 3}],
           did="3-04", by=("bus_station_name",), measures=("user_count",))
    assert assess(r, cat).light == "green"


def test_red_small_cells(cat):
    a = assess(mk([row("애월읍", 1000, 50), row("노형동", 300, 4), row("연동", 900, 30)]), cat)
    assert a.light == "red"
    assert any("10 미만" in x for x in a.reasons)
    assert a.kind_label == "단순집계"


def test_suppression_adds_complement(cat):
    r = apply_suppression(mk([row("애월읍", 1000, 50), row("노형동", 300, 4), row("연동", 900, 30)]))
    assert len(r.masked) == 2
    assert (1, "use_amt") in r.masked and (2, "use_amt") in r.masked
    assert assess(r, cat).light in ("green", "yellow")


def test_single_masked_cell_is_red(cat):
    r = mk([row("애월읍", 1000, 50), row("노형동", 300, 4), row("연동", 900, 30)])
    r.masked = {(1, "use_amt")}
    a = assess(r, cat)
    assert a.light == "red" and any("역산" in x for x in a.reasons)


def test_single_row_cell_yellow(cat):
    a = assess(mk([row("애월읍", 1000, 50), row("노형동", 300, 40, nr=1)]), cat)
    assert a.light == "yellow"
    assert any("한 행" in x for x in a.reasons)


def test_csv_format_red_for_sensitive(cat):
    a = assess(mk([row("애월읍", 1000, 50), row("노형동", 300, 40)]), cat, fmt="csv")
    assert a.light == "red"
    assert any("그림" in x for x in a.reasons)


def test_applied_small_denominator_yellow(cat):
    r = mk([{"bjd": "애월읍", "use_amt_pct": 90.0, "_n_rows": 5, "_n_count": 50},
            {"bjd": "노형동", "use_amt_pct": 10.0, "_n_rows": 5, "_n_count": 3}],
           measures=("use_amt_pct",), kind="applied")
    a = assess(r, cat)
    assert a.light == "yellow" and a.kind_label == "응용집계"


def test_all_cells_small(cat):
    a = assess(mk([row("애월읍", 10, 3), row("노형동", 30, 4), row("연동", 20, 2)]), cat)
    assert a.light == "red"
    assert any("가릴 칸이 너무 많" in x for x in a.reasons)
    assert a.fixes[0].op == "rollup"


def test_rollup_fix_reaches_green(small_ws, cat):
    r = run_step(small_ws, cat, Step("share", "1-08", "use_cnt", ["age"], {"bjd": "애월읍"},
                                     {"period": ["2024-07", "2024-07"]}))
    a = assess(r, cat)
    assert a.light != "green"
    fix = next(f for f in a.fixes if f.op == "rollup")
    r2 = apply_fix(small_ws, cat, r, fix)
    assert r2.step.by == ["age_band"]
    assert assess(r2, cat).light == "green"


def test_suppress_fix(small_ws, cat):
    r = run_step(small_ws, cat, Step("share", "1-08", "use_cnt", ["age"], {"bjd": "애월읍"},
                                     {"period": ["2024-07", "2024-07"]}))
    fix = next(f for f in assess(r, cat).fixes if f.op == "suppress")
    r2 = apply_fix(small_ws, cat, r, fix)
    assert len(r2.masked) >= 2 and assess(r2, cat).light != "red"


# ---- 최종 리뷰 수정(C1·I2·I3) ----
def test_count_metric_itself_under_10_is_not_green(small_ws, cat):
    # 이용자수 9(=3×3개월) 인데 이용건수는 12 → 지표 자체가 10 미만이므로 초록이면 안 됨 (C1)
    r = run_step(small_ws, cat, Step("trend", "1-08", "user_cnt", ["quarter"], {"bjd": "애월읍", "user_type": "일본"},
                                     {"period": ["2024-07", "2024-09"]}))
    assert r.rows[0]["user_cnt"] == 9
    assert assess(r, cat).light != "green"


def test_yoy_uses_smaller_of_two_months(tmp_path, cat):
    # 2024-07 건수 4, 2025-07 건수 12 → 증감률로 작년 값이 역산되므로 초록이면 안 됨 (I2)
    import sys
    sys.path.insert(0, "tests")
    from conftest import H108, small_rows, write_csv
    from app.ingest import Workspace
    rows = small_rows()
    for x in rows:
        if x[7] == "일본" and x[0].startswith("2025"):
            x[12], x[13] = 12, 150
    files = [write_csv(tmp_path / f"Results_20261109_{ym}.csv", H108, [x for x in rows if x[0] == ym])
             for ym in sorted({x[0] for x in rows})]
    ws = Workspace(cat)
    ws.add_files(files)
    r = run_step(ws, cat, Step("yoy", "1-08", "use_amt", [], {"bjd": "애월읍", "user_type": "일본"},
                               {"period": ["2025-07", "2025-08"]}))
    assert r.rows[0]["yoy_pct"] == 50.0
    from app.guard import cell_count
    assert cell_count(r.rows[0], "yoy_pct") == 4  # 두 달 중 작은 건수


def test_compare_hides_derived_columns_with_hidden_parts(cat):
    def row(k, a, b, na, nb):
        return {"age": k, "use_amt_a": a, "use_amt_b": b, "diff_pct": round((a - b) / b * 100, 1), "_n_rows": 5,
                "_n_count": min(na, nb), "_n:use_amt_a": na, "_n:use_amt_b": nb, "_r:use_amt_a": 5, "_r:use_amt_b": 5}
    rows = [row("20", 500, 400, 4, 50), row("30", 900, 800, 12, 15), row("40", 2000, 1000, 80, 11),
            row("50", 3000, 2500, 60, 60)]
    step = Step("compare", "1-08", "use_amt", ["age"], {"bjd": "애월읍"}, {"filters_b": {"bjd": "노형동"}})
    s = apply_suppression(Result("x", "t", step, ["age"], ["use_amt_a", "use_amt_b", "diff_pct"], rows, "simple", ("", "")))
    for i in range(len(rows)):
        if (i, "use_amt_a") in s.masked or (i, "use_amt_b") in s.masked:
            visible = [m for m in ("use_amt_a", "use_amt_b", "diff_pct") if (i, m) not in s.masked]
            assert len(visible) <= 1, (i, visible)  # 남은 두 칸으로 가린 칸을 되살릴 수 없어야 함


def test_single_cell_column_hidden_is_not_red_loop(cat):
    step = Step("trend", "1-08", "use_amt", [], {"bjd": "우도면"}, {})
    r = Result("x", "t", step, [], ["use_amt"], [{"use_amt": 500, "_n_rows": 3, "_n_count": 4}], "simple", ("", ""))
    a = assess(apply_suppression(r), cat)
    assert not any("하나뿐" in x for x in a.reasons)  # 칸이 하나뿐이면 합계 역산 대상이 없음 (M3)


# ---- 게시판 답변(11/15): 단순 사칙연산 값도 단순집계, '10 미만'은 최종 결과값 기준, 금액은 원 단위 ----
def test_simple_value_itself_under_10_is_hidden(cat):
    step = Step("trend", "1-08", "use_cnt", ["bjd"], {}, {})
    rows = [{"bjd": "가", "per": 1.3, "_n_rows": 50, "_n_count": 500},
            {"bjd": "나", "per": 2.1, "_n_rows": 50, "_n_count": 500},
            {"bjd": "다", "per": 12.0, "_n_rows": 50, "_n_count": 500}]
    r = Result("x", "t", step, ["bjd"], ["per"], rows, "simple", ("", ""))
    assert assess(r, cat).light != "green"           # 건수는 충분해도 값 1.3은 10 미만
    s = apply_suppression(r)
    assert {(0, "per"), (1, "per")} <= s.masked and (2, "per") not in s.masked


def test_applied_ratio_under_10_is_allowed(cat):
    step = Step("share", "1-08", "use_cnt", ["bjd"], {}, {})
    rows = [{"bjd": "가", "use_cnt_pct": 3.6, "_n_rows": 50, "_n_count": 500},
            {"bjd": "나", "use_cnt_pct": 96.4, "_n_rows": 50, "_n_count": 500}]
    r = Result("x", "t", step, ["bjd"], ["use_cnt_pct"], rows, "applied", ("", ""))
    assert assess(r, cat).light == "green"           # 비율은 응용집계라 수치 포함 반출 가능
