import pytest

from app.model import Step
from app.tools import run_step


def test_trend_sum(small_ws, cat):
    r = run_step(small_ws, cat, Step("trend", "1-08", "use_amt", ["base_year_month"],
                                     {"bjd": "애월읍", "biz_nm": "한식 음식점업"},
                                     {"period": ["2024-07", "2024-08"]}))
    assert [row["base_year_month"] for row in r.rows] == ["202407", "202408"]
    assert [row["use_amt"] for row in r.rows] == [1100, 2100]
    assert [row["_n_rows"] for row in r.rows] == [2, 2]
    assert [row["_n_count"] for row in r.rows] == [34, 34]
    assert r.agg_kind == "simple"
    assert r.period == ("2024-07", "2024-08")


def test_share_sums_to_100(small_ws, cat):
    r = run_step(small_ws, cat, Step("share", "1-08", "use_cnt", ["user_type"], {"bjd": "애월읍"}))
    assert abs(sum(row["use_cnt_pct"] for row in r.rows) - 100.0) < 0.1
    assert r.agg_kind == "applied"


def test_yoy(small_ws, cat):
    r = run_step(small_ws, cat, Step("yoy", "1-08", "use_amt", [], {"bjd": "애월읍", "biz_nm": "한식 음식점업"}))
    last = r.rows[-1]
    assert last["base_year_month"] == "202508"
    # 2025-08: 14000+100, 2024-08: 2000+100
    assert last["yoy_pct"] == pytest.approx((14100 - 2100) / 2100 * 100, abs=0.1)
    assert r.rows[0]["yoy_pct"] is None


def test_rank(small_ws, cat):
    r = run_step(small_ws, cat, Step("rank", "1-08", "use_amt", ["bjd"], {"biz_nm": "한식 음식점업"},
                                     {"period": ["2024-07", "2024-07"], "top": 5}))
    assert [row["bjd"] for row in r.rows] == ["노형동", "애월읍"]
    assert [row["rank"] for row in r.rows] == [1, 2]


def test_compare(small_ws, cat):
    r = run_step(small_ws, cat, Step("compare", "1-08", "use_amt", ["biz_nm"], {"bjd": "애월읍"},
                                     {"filters_b": {"bjd": "노형동"}, "period": ["2024-07", "2024-07"]}))
    row = next(x for x in r.rows if x["biz_nm"] == "한식 음식점업")
    assert row["use_amt_a"] == 1100 and row["use_amt_b"] == 2000


def test_contribution_sums(small_ws, cat):
    r = run_step(small_ws, cat, Step("contribution", "1-08", "use_amt", ["biz_nm"], {"bjd": "애월읍"},
                                     {"period_a": ["2024-07", "2024-07"], "period_b": ["2024-08", "2024-08"]}))
    assert sum(row["change_diff"] for row in r.rows) == 1000
    assert abs(sum(row["contrib_pct"] for row in r.rows) - 100.0) < 0.1


def test_profile(small_ws, cat):
    r = run_step(small_ws, cat, Step("profile", "1-08", "use_amt", [], {}, {"area": "애월읍"}))
    labels = [row["지표"] for row in r.rows]
    assert any("합계" in x for x in labels)
    assert any("업종" in x for x in labels)


def test_describe(small_ws, cat):
    r = run_step(small_ws, cat, Step("describe", "1-08", "use_amt", ["bjd"], {}))
    nh = next(x for x in r.rows if x["bjd"] == "노형동")
    assert nh["mean"] == 2000 and nh["min"] == 2000 and nh["max"] == 2000


def test_virtual_columns(small_ws, cat):
    total = run_step(small_ws, cat, Step("trend", "1-08", "use_amt", ["year"], {}))
    by_d = run_step(small_ws, cat, Step("rank", "1-08", "use_amt", ["dstrct_se"], {}))
    assert sum(x["use_amt"] for x in total.rows) == sum(x["use_amt"] for x in by_d.rows)
    q = run_step(small_ws, cat, Step("trend", "1-08", "use_amt", ["quarter"], {}))
    assert q.rows[0]["quarter"] == "2024-Q3"


def test_rejects_unknown_column(small_ws, cat):
    with pytest.raises(ValueError):
        run_step(small_ws, cat, Step("trend", "1-08", "use_amt", ["bogus"], {}))


def test_rejects_unfilled_placeholder(small_ws, cat):
    with pytest.raises(ValueError):
        run_step(small_ws, cat, Step("trend", "1-08", "use_amt", ["base_year_month"], {"bjd": "?"}))


def test_filters_bound_not_interpolated(small_ws, cat):
    r = run_step(small_ws, cat, Step("trend", "1-08", "use_amt", ["base_year_month"],
                                     {"bjd": "애월읍' OR 1=1 --"}))
    assert r.rows == []


def test_average_measures_are_averaged_not_summed(tmp_path, cat):
    from app.ingest import Workspace
    from app.synth import generate
    ws = Workspace(cat)
    ws.add_files(generate("5-02", ["2025-07"], tmp_path))
    r = run_step(ws, cat, Step("trend", "5-02", "average_temperature", ["quarter"], {}, {}))
    lo, hi = ws.con.execute(f"select min(average_temperature), max(average_temperature) from {ws.table('5-02')}").fetchone()
    assert lo <= r.rows[0]["average_temperature"] <= hi  # 한 달 합계(수백 도)가 아니라 평균 (M1)


def test_malformed_options_are_tolerated(small_ws, cat):
    r = run_step(small_ws, cat, Step("rank", "1-08", "use_amt", ["bjd"], {}, {"period": "2024-07", "top": None}))
    assert r.rows and r.period == ("2024-07", "2024-07")  # (M4)


def test_weekday_and_time_bands_in_natural_order(tmp_path, cat):
    from app.ingest import Workspace
    from app.synth import generate
    ws = Workspace(cat)
    ws.add_files(generate("1-12", ["2026-01"], tmp_path) + generate("1-14", ["2026-01"], tmp_path, index_offset=5))
    w = [r["week"] for r in run_step(ws, cat, Step("trend", "1-12", "use_cnt", ["week"], {}, {})).rows]
    assert w == ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일", "공휴일"]
    t = [r["time"] for r in run_step(ws, cat, Step("trend", "1-14", "use_cnt", ["time"], {}, {})).rows]
    assert t == ["오전", "점심", "오후", "저녁", "밤"]


def test_natural_key_orders_hours_numerically():
    from app.tools import natural_key
    assert sorted(["10", "2", "0", "23"], key=natural_key) == ["0", "2", "10", "23"]
    assert sorted(["일", "월", "토"], key=natural_key) == ["월", "토", "일"]
