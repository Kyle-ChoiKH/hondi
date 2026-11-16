import json

from app.firewall import Outbound
from app.llm import NoProvider, Reply
from app.model import Plan, Step
from app.planner import CARDS, PlanCache, card_plan, cards_for, fill, needs, plan_from_question, plan_text, validate


class FakeProvider:
    model = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, user, max_tokens=800):
        self.calls.append((system, user))
        return Reply(self.replies.pop(0), 10, 10)


GOOD = {"purpose": "사업계획서", "steps": [
    {"tool": "trend", "dataset": "1-08", "metric": "use_amt", "by": ["base_year_month"],
     "filters": {"bjd": "〔bjd#1〕", "biz_nm": "?"}, "options": {}}], "ask": None}
BAD = {"purpose": "사업계획서", "steps": [
    {"tool": "trend", "dataset": "1-08", "metric": "use_amt", "by": ["bogus_col"], "filters": {}, "options": {}}]}


def test_validate_rejects_bad_column(small_ws, cat):
    errs = validate(Plan.from_dict(BAD), small_ws, cat)
    assert errs and "bogus_col" in errs[0]


def test_validate_rejects_unloaded_dataset(small_ws, cat):
    p = Plan("자유", [Step("share", "1-14", "use_cnt", ["time"], {})])
    assert validate(p, small_ws, cat)


def test_ai_plan_with_retry(small_ws, cat, tmp_path):
    prov = FakeProvider([json.dumps(BAD), json.dumps(GOOD)])
    ob = Outbound(tmp_path / "o.jsonl", prov)
    plan, notes = plan_from_question("애월읍 매출 흐름", "사업계획서", small_ws, cat, ob, PlanCache())
    assert plan.source == "ai"
    assert len(prov.calls) == 2
    assert plan.steps[0].filters["bjd"] == "애월읍"
    assert all("애월읍" not in c[1] and "애월읍" not in c[0] for c in prov.calls)
    assert "bogus_col" in prov.calls[1][1]


def test_plan_cache_hit_skips_call(small_ws, cat, tmp_path):
    prov = FakeProvider([json.dumps(GOOD)])
    ob = Outbound(tmp_path / "o.jsonl", prov)
    cache = PlanCache()
    plan_from_question("애월읍 매출 흐름", "사업계획서", small_ws, cat, ob, cache)
    plan2, notes = plan_from_question("애월읍 매출 흐름", "사업계획서", small_ws, cat, ob, cache)
    assert len(prov.calls) == 1
    assert plan2.steps[0].filters["bjd"] == "애월읍"
    assert any("저장된 계획" in n for n in notes)


def test_falls_back_when_ai_unavailable(small_ws, cat, tmp_path):
    ob = Outbound(tmp_path / "o.jsonl", NoProvider("키 없음"))
    plan, notes = plan_from_question("손님은 누구인가요", "사업계획서", small_ws, cat, ob, PlanCache())
    assert plan.source == "card"
    assert any("AI 없이" in n for n in notes)
    assert plan.steps[0].tool == "share"


def test_non_json_reply_falls_back(small_ws, cat, tmp_path):
    ob = Outbound(tmp_path / "o.jsonl", FakeProvider(["이건 JSON이 아님", "역시 아님"]))
    plan, notes = plan_from_question("매출 흐름", "사업계획서", small_ws, cat, ob, PlanCache())
    assert plan.source == "card"


def test_unknown_value_becomes_question(small_ws, cat, tmp_path):
    bad_value = json.loads(json.dumps(GOOD))
    bad_value["steps"][0]["filters"] = {"bjd": "없는동", "biz_nm": "한식 음식점업"}
    ob = Outbound(tmp_path / "o.jsonl", FakeProvider([json.dumps(bad_value)]))
    plan, _ = plan_from_question("매출", "사업계획서", small_ws, cat, ob, PlanCache())
    assert plan.steps[0].filters["bjd"] == "?"


def test_needs_and_fill(small_ws, cat):
    plan = card_plan("biz_trend", small_ws, cat)
    nd = needs(plan, small_ws, cat)
    keys = {n["key"] for n in nd}
    assert {"bjd", "biz_nm"} <= keys
    assert "애월읍" in next(n for n in nd if n["key"] == "bjd")["options"]
    p2 = fill(plan, {"bjd": "애월읍", "biz_nm": "한식 음식점업"})
    assert not needs(p2, small_ws, cat)
    assert plan_text(p2, cat)


def test_cards_disabled_without_data(small_ws, cat):
    cs = {c["id"]: c for c in cards_for("사업계획서", small_ws, cat)}
    assert cs["biz_trend"]["enabled"] is True
    assert cs["biz_time"]["enabled"] is False and cs["biz_time"]["why"]
    assert set(CARDS) >= {"사업계획서", "현황자료", "논문"}


def test_profile_card_needs_area(small_ws, cat):
    plan = card_plan("area_profile", small_ws, cat)
    assert any(n["key"] == "bjd" for n in needs(plan, small_ws, cat))
    p2 = fill(plan, {"bjd": "애월읍"})
    assert p2.steps[0].options["area"] == "애월읍"


def test_dataset_name_normalized(small_ws, cat, tmp_path):
    named = json.loads(json.dumps(GOOD))
    named["steps"][0]["dataset"] = "[1-08] 카드 이용 현황(읍면동)_v02"
    prov = FakeProvider([json.dumps(named)])
    plan, _ = plan_from_question("매출", "사업계획서", small_ws, cat, Outbound(tmp_path / "o.jsonl", prov), PlanCache())
    assert plan.source == "ai" and plan.steps[0].dataset == "1-08"
    assert len(prov.calls) == 1


def test_schema_includes_public_codes(small_ws, cat):
    from app.planner import schema_text
    s = schema_text(small_ws, cat)
    assert "비알콜 음료점업" in s
    assert "제주시 중부(서)" in s
    assert "애월읍" not in s


def test_system_prompt_has_examples(small_ws, cat, tmp_path):
    prov = FakeProvider([json.dumps(GOOD)])
    plan_from_question("매출", "사업계획서", small_ws, cat, Outbound(tmp_path / "o.jsonl", prov), PlanCache())
    system = prov.calls[0][0]
    assert "예시" in system and '"tool":"compare"' in system and "filters_b" in system


def test_compare_second_condition_is_asked_and_filled(small_ws, cat):
    from app.model import Plan, Step
    from app.planner import fill, needs
    plan = Plan("자유", [Step("compare", "1-08", "use_amt", ["user_type"], {"bjd": "애월읍"}, {"filters_b": {"bjd": "?"}})])
    n = needs(plan, small_ws, cat)
    assert [x["key"] for x in n] == ["b:bjd"] and "노형동" in n[0]["options"] and "비교" in n[0]["label"]
    p = fill(plan, {"b:bjd": "노형동"})
    assert p.steps[0].options["filters_b"] == {"bjd": "노형동"} and p.steps[0].filters == {"bjd": "애월읍"}


def test_unknown_compare_and_area_values_become_questions(small_ws, cat):
    from app.model import Plan, Step
    from app.planner import _normalize_values
    plan = Plan("자유", [Step("compare", "1-08", "use_amt", [], {"bjd": "애월읍"}, {"filters_b": {"bjd": "없는동"}}),
                       Step("profile", "1-08", "use_amt", [], {}, {"area": "없는동"})])
    _normalize_values(plan, small_ws)
    assert plan.steps[0].options["filters_b"] == {"bjd": "?"} and plan.steps[1].options["area"] == "?"
    assert plan.steps[0].filters == {"bjd": "애월읍"}
