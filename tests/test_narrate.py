import json

from app.charts import render
from app.firewall import Masker, Outbound
from app.guard import apply_suppression, assess
from app.llm import Reply
from app.model import Step
from app.narrate import caveats, narrate, narrate_ai, source_line
from app.tools import run_step


class FakeProvider:
    model = "fake"

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def complete(self, system, user, max_tokens=800):
        self.calls.append((system, user))
        return Reply(self.replies.pop(0), 5, 5)


def trend(ws, cat):
    return run_step(ws, cat, Step("trend", "1-08", "use_amt", ["base_year_month"],
                                  {"bjd": "애월읍", "biz_nm": "한식 음식점업"}, {"period": ["2024-07", "2024-09"]}))


def test_trend_sentence_mentions_change_percent(small_ws, cat):
    text = " ".join(narrate(trend(small_ws, cat), cat))
    # 1,100 → 3,100 : +181.8%
    assert "181.8%" in text and "늘었" in text


def test_share_sentence(small_ws, cat):
    r = run_step(small_ws, cat, Step("share", "1-08", "use_cnt", ["user_type"], {"bjd": "애월읍"}))
    assert "제주도민" in " ".join(narrate(r, cat))


def test_masked_sentence_present(small_ws, cat):
    r = run_step(small_ws, cat, Step("share", "1-08", "use_cnt", ["age"], {"bjd": "애월읍"},
                                     {"period": ["2024-07", "2024-07"]}))
    text = " ".join(narrate(apply_suppression(r), cat))
    assert "10 미만" in text


def test_caveat_card_dataset(small_ws, cat):
    cv = " ".join(caveats(trend(small_ws, cat), cat))
    assert "비씨카드" in cv
    assert source_line(trend(small_ws, cat), cat) == "출처: 제주빅데이터센터, 카드 이용 현황(읍면동)_v02(2024-07~2024-09)"


def test_render_creates_png(small_ws, cat, tmp_path):
    p = render(trend(small_ws, cat), cat, tmp_path / "a.png")
    assert p.exists() and p.stat().st_size > 10_000
    r = run_step(small_ws, cat, Step("share", "1-08", "use_cnt", ["age"], {"bjd": "애월읍"},
                                     {"period": ["2024-07", "2024-07"]}))
    assert render(apply_suppression(r), cat, tmp_path / "b.png").exists()
    c = run_step(small_ws, cat, Step("compare", "1-08", "use_amt", ["biz_nm"], {"bjd": "애월읍"},
                                     {"filters_b": {"bjd": "노형동"}}))
    assert render(c, cat, tmp_path / "c.png").exists()
    pr = run_step(small_ws, cat, Step("profile", "1-08", "use_amt", [], {}, {"area": "애월읍"}))
    assert render(pr, cat, tmp_path / "d.png").exists()


def test_render_no_numbers(small_ws, cat, tmp_path):
    a = render(trend(small_ws, cat), cat, tmp_path / "a.png", numbers=True).stat().st_size
    b = render(trend(small_ws, cat), cat, tmp_path / "b.png", numbers=False).stat().st_size
    assert a != b


def test_narrate_ai_skipped_when_switch_off(small_ws, cat, tmp_path):
    r = trend(small_ws, cat)
    prov = FakeProvider(['{"sentences":["x"]}'])
    out = narrate_ai(r, assess(r, cat), cat, Outbound(tmp_path / "o.jsonl", prov), Masker({}), send_aggregates=False)
    assert out is None and prov.calls == []


def test_narrate_ai_sends_only_green(small_ws, cat, tmp_path):
    r = run_step(small_ws, cat, Step("share", "1-08", "use_cnt", ["user_type"], {"bjd": "애월읍"},
                                     {"period": ["2024-07", "2024-07"]}))
    prov = FakeProvider(['{"sentences":["x"]}'])
    a = assess(r, cat)
    assert a.light != "green"
    assert narrate_ai(r, a, cat, Outbound(tmp_path / "o.jsonl", prov), Masker({}), send_aggregates=True) is None
    assert prov.calls == []


def test_narrate_ai_green_masks_dims(small_ws, cat, tmp_path):
    r = trend(small_ws, cat)
    a = assess(r, cat)
    assert a.light == "green"
    prov = FakeProvider([json.dumps({"sentences": ["〔bjd#1〕 매출이 늘었습니다."]})])
    out = narrate_ai(r, a, cat, Outbound(tmp_path / "o.jsonl", prov), Masker(small_ws.dim_values()),
                     send_aggregates=True)
    assert out == ["애월읍 매출이 늘었습니다."]
    assert "애월읍" not in prov.calls[0][1]


def test_month_slots_insert_missing_months():
    from app.charts import month_slots
    rows = [{"base_year_month": "202510"}, {"base_year_month": "202512"}, {"base_year_month": "202601"}]
    assert month_slots(rows, "base_year_month") == [("202510", 0), ("202511", None), ("202512", 1), ("202601", 2)]
    assert month_slots([{"time": "점심"}], "time") == [("점심", 0)]


def test_narrate_ai_never_sends_masked_cells(small_ws, cat, tmp_path):
    r = run_step(small_ws, cat, Step("share", "1-08", "use_cnt", ["user_type"], {"bjd": "애월읍"}))
    r.measures = ["use_cnt_pct"]
    r.rows[1]["use_cnt_pct"] = 12.3456
    r.masked = {(1, "use_cnt_pct"), (0, "use_cnt_pct")}
    from app.model import Assessment
    prov = FakeProvider([json.dumps({"sentences": ["ok"]})])
    narrate_ai(r, Assessment("green", [], [], "응용집계"), cat, Outbound(tmp_path / "o.jsonl", prov),
               Masker(small_ws.dim_values()), send_aggregates=True)
    sent = prov.calls[0][1] if prov.calls else ""
    assert "12.3456" not in sent and str(r.rows[0]["use_cnt_pct"]) not in sent  # (C2)


def test_amounts_are_shown_in_won(cat):
    from app.narrate import fmt_value
    assert fmt_value(320000000, "use_amt", cat, "1-08") == "320,000,000원"
    assert fmt_value(-72110000, "use_amt", cat, "1-08") == "-72,110,000원"  # 증감값은 원래 지표(금액)로 표시
    assert fmt_value(120, "use_cnt", cat, "1-08") == "120"  # 건수 증감에는 원을 붙이지 않음


def test_charts_use_bundled_pretendard_font():
    # 센터 PC에 글꼴을 설치하지 않아도 화면과 같은 글꼴로 그림을 그린다
    from app import charts
    assert charts._FONT == "Pretendard"


# ---------- 한 줄 요약(비전문가용, 화면 맨 위) ----------
def test_headline_trend_says_how_much_it_grew(small_ws, cat):
    from app.narrate import headline
    h = headline(trend(small_ws, cat), cat)
    assert "182%" in h and "늘었어요" in h and "2024년 7월" in h


def test_headline_share_uses_out_of_ten(small_ws, cat):
    from app.narrate import headline
    r = run_step(small_ws, cat, Step("share", "1-08", "use_cnt", ["user_type"], {"bjd": "애월읍"}))
    h = headline(r, cat)
    assert h == "거의 다 '제주도민'이에요 (95.7%)."
    r2 = run_step(small_ws, cat, Step("share", "1-08", "use_cnt", ["bjd"], {}))
    assert "10건 중" in headline(r2, cat) and "건꼴이에요" in headline(r2, cat)


def test_headline_rank_compares_first_and_second(small_ws, cat):
    from app.narrate import headline
    r = run_step(small_ws, cat, Step("rank", "1-08", "use_amt", ["bjd"], {"biz_nm": "한식 음식점업"}, {"top": 10}))
    h = headline(r, cat)
    assert "1위는 '애월읍'" in h and "3.8배" in h


def test_headline_never_uses_masked_cells(small_ws, cat):
    from app.narrate import headline
    r = apply_suppression(run_step(small_ws, cat, Step("share", "1-08", "use_cnt", ["age"], {"bjd": "애월읍"},
                                                       {"period": ["2024-07", "2024-07"]})))
    hidden = {str(r.rows[i][r.dims[0]]) for i, _ in r.masked}
    h = headline(r, cat)
    assert h and not any(f"'{v}'" in h for v in hidden)


def test_friendly_won_reads_like_speech():
    from app.narrate import won_friendly
    assert won_friendly(35181580) == "약 3,518만 원"
    assert won_friendly(1234567890) == "약 12.3억 원"
    assert won_friendly(52000) == "52,000원"


def test_howto_explains_chart_for_every_tool():
    from app.narrate import HOWTO
    from app.tools import TOOLS
    assert set(TOOLS) <= set(HOWTO) and all("요" in v for v in HOWTO.values())


def _res(tool, metric, dims, measures, rows, masked=(), filters=None, options=None, did="1-08"):
    from app.model import Result
    return Result("t", "t", Step(tool, did, metric, dims, filters or {}, options or {}), dims, measures, rows,
                  "simple", ("202507", "202508"), set(masked))


def test_headline_rank_does_not_crown_second_when_first_is_masked(cat):
    from app.narrate import headline
    r = _res("rank", "use_amt", ["biz_nm"], ["rank", "use_amt"],
             [{"biz_nm": "기타", "rank": 1, "use_amt": 900}, {"biz_nm": "한식", "rank": 2, "use_amt": 500},
              {"biz_nm": "카페", "rank": 3, "use_amt": 100}], masked={(0, "rank"), (0, "use_amt")})
    h = headline(r, cat)
    assert "1위는 '한식'" not in h and "'한식'" in h and "가린 칸" in h


def test_headline_share_and_profile_say_masked_top_may_be_hidden(cat):
    from app.narrate import headline
    r = _res("share", "use_amt", ["biz_nm"], ["share_pct"],
             [{"biz_nm": "기타", "share_pct": 60.0}, {"biz_nm": "한식", "share_pct": 25.0}, {"biz_nm": "카페", "share_pct": 15.0}],
             masked={(0, "share_pct"), (2, "share_pct")})
    h = headline(r, cat)
    assert "가장 큰 몫은 '한식'" not in h and "가린 칸" in h
    p = _res("profile", "use_amt", [], ["값"],
             [{"지표": "주요 업종: 기타 비중(%)", "값": 50.0}, {"지표": "주요 업종: 한식 비중(%)", "값": 30.0}],
             masked={(0, "값")}, options={"area": "애월읍"})
    assert "가장 큰 업종은 '한식'" not in headline(p, cat)


def test_headline_trend_with_two_dims_does_not_mix_series(cat):
    from app.narrate import headline
    r = _res("trend", "use_amt", ["base_year_month", "bjd"], ["use_amt"],
             [{"base_year_month": "202506", "bjd": "노형동", "use_amt": 2000}, {"base_year_month": "202506", "bjd": "애월읍", "use_amt": 14100},
              {"base_year_month": "202508", "bjd": "노형동", "use_amt": 2340}, {"base_year_month": "202508", "bjd": "애월읍", "use_amt": 14100}])
    h = headline(r, cat)
    assert "605%" not in h and "%" not in h and "애월읍" in h


def test_headline_contribution_of_counts_is_not_in_won(cat):
    from app.narrate import headline
    r = _res("contribution", "use_cnt", ["biz_nm"], ["change_diff"],
             [{"biz_nm": "카페", "change_diff": 120}, {"biz_nm": "한식", "change_diff": -30}])
    h = headline(r, cat)
    assert "원" not in h and "120" in h


def test_headline_compare_uses_rows_visible_on_both_sides(cat):
    from app.narrate import headline
    r = _res("compare", "use_amt", ["base_year_month"], ["use_amt_a", "use_amt_b"],
             [{"base_year_month": "202507", "use_amt_a": 100, "use_amt_b": 100},
              {"base_year_month": "202508", "use_amt_a": 100, "use_amt_b": 5000}],
             masked={(1, "use_amt_a")}, filters={"bjd": "애월읍"}, options={"filters_b": {"bjd": "노형동"}})
    assert "배 많아요" not in headline(r, cat)  # 둘 다 보이는 202507만 비교 → 같음
