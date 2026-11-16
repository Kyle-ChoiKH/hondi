"""길잡이: 질문을 분석 계획으로 바꾼다.

AI(OpenAI)는 데이터의 구조(컬럼 이름·설명)와 가려진 질문만 보고 계획 JSON을 만든다.
AI를 쓸 수 없거나 계획이 검사를 통과하지 못하면 질문 카드(규칙 기반)로 대신한다.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass

from .josa import j
from .catalog import VIRTUAL_LABEL, Catalog
from .firewall import Masker, Outbound, unmask
from .ingest import Workspace
from .llm import ProviderUnavailable
from .model import Plan, Step
from .tools import TOOL_HELP, TOOLS

PURPOSES = ["사업계획서", "현황자료", "논문", "자유"]


@dataclass
class Card:
    id: str
    purpose: str
    label: str
    datasets: tuple
    steps: tuple
    keywords: tuple = ()


def _s(tool, did, metric, by, filters=None, **options):
    return Step(tool, did, metric, list(by), dict(filters or {}), dict(options))


AREA_BIZ = {"bjd": "?", "biz_nm": "?"}
CARD_LIST = [
    Card("biz_trend", "사업계획서", "이 동네 이 업종, 장사는 잘되고 있나요? (월별 매출 흐름)", ("1-08",),
         (_s("trend", "1-08", "use_amt", ["base_year_month"], AREA_BIZ),), ("매출", "흐름", "추이", "장사", "잘")),
    Card("biz_customers", "사업계획서", "손님은 누구인가요? (이용자·연령 구성)", ("1-08",),
         (_s("share", "1-08", "use_amt", ["user_type"], AREA_BIZ),
          _s("share", "1-08", "use_cnt", ["age_band"], AREA_BIZ)), ("손님", "고객", "누구", "연령", "관광객", "도민")),
    Card("biz_time", "사업계획서", "손님은 언제 오나요? (시간대별 이용)", ("1-14",),
         (_s("share", "1-14", "use_cnt", ["time"], AREA_BIZ),), ("시간", "언제", "몇 시", "영업시간")),
    Card("biz_week", "사업계획서", "어느 요일이 붐비나요? (요일별 이용)", ("1-12",),
         (_s("share", "1-12", "use_cnt", ["week"], AREA_BIZ),), ("요일", "주말", "휴무")),
    Card("biz_compare_areas", "사업계획서", "이 업종은 어느 동네에서 잘되나요? (법정동 순위)", ("1-08",),
         (_s("rank", "1-08", "use_amt", ["bjd"], {"biz_nm": "?"}, top=10),), ("비교", "어디", "후보", "입지", "순위")),
    Card("biz_yoy", "사업계획서", "작년보다 늘었나요? (전년 동월 대비)", ("1-08",),
         (_s("yoy", "1-08", "use_amt", [], AREA_BIZ),), ("전년", "작년", "늘었", "줄었", "증가", "감소")),
    Card("area_profile", "현황자료", "우리 동네 한 장 프로필", ("1-08",),
         (_s("profile", "1-08", "use_amt", [], {}, area="?"),), ("프로필", "현황", "요약", "한 장")),
    Card("area_rank_biz", "현황자료", "우리 동네 업종 순위", ("1-08",),
         (_s("rank", "1-08", "use_amt", ["biz_nm"], {"bjd": "?"}, top=10),), ("업종 순위", "어떤 업종")),
    Card("area_change", "현황자료", "무엇 때문에 늘고 줄었나요? (업종별 증감 기여)", ("1-08",),
         (_s("contribution", "1-08", "use_amt", ["biz_group"], {"bjd": "?"}, period_a="auto", period_b="auto"),),
         ("왜", "기여", "변화", "원인", "늘고")),
    Card("area_population", "현황자료", "우리 동네 시간대별 인구", ("4-11",),
         (_s("trend", "4-11", "visit_pop_cnt", ["time"], {"emd_nm": "?"}),), ("인구", "유동", "사람")),
    Card("paper_describe", "논문", "권역별 기술통계표", ("1-08",),
         (_s("describe", "1-08", "use_amt", ["dstrct_se"]),), ("기술통계", "통계표", "평균", "표준편차")),
    Card("paper_trend_quarter", "논문", "분기별 추이(권역)", ("1-08",),
         (_s("trend", "1-08", "use_amt", ["quarter"]),), ("분기",)),
]
CARDS = {}
for _c in CARD_LIST:
    CARDS.setdefault(_c.purpose, []).append(_c)
CARD_BY_ID = {c.id: c for c in CARD_LIST}


class PlanCache:
    """같은(가려진) 질문 + 같은 데이터 조합이면 AI를 다시 부르지 않는다."""

    def __init__(self):
        self._d = {}

    @staticmethod
    def key(masked_question: str, purpose: str, loaded: list) -> str:
        return hashlib.sha256(json.dumps([masked_question, purpose, sorted(loaded)],
                                         ensure_ascii=False).encode()).hexdigest()

    def get(self, k):
        return self._d.get(k)

    def put(self, k, v):
        self._d[k] = v


def _auto_periods(ws: Workspace, did: str):
    ds = next((d for d in ws.datasets() if d.id == did), None)
    months = ds.months if ds else []
    if len(months) < 2:
        return None, None
    half = len(months) // 2
    return [months[0], months[half - 1]], [months[half], months[-1]]


def card_plan(card_id: str, ws: Workspace, cat: Catalog) -> Plan:
    c = CARD_BY_ID[card_id]
    steps = []
    for s in c.steps:
        s = copy.deepcopy(s)
        if s.options.get("period_a") == "auto":
            s.options["period_a"], s.options["period_b"] = _auto_periods(ws, s.dataset)
        steps.append(s)
    return Plan(c.purpose, steps, None, "card")


def cards_for(purpose: str, ws: Workspace, cat: Catalog) -> list:
    out = []
    for c in CARDS.get(purpose, []):
        missing = [d for d in c.datasets if d not in ws.loaded()]
        out.append({"id": c.id, "label": c.label, "enabled": not missing,
                    "why": ("필요한 파일: " + ", ".join(cat.name(d) for d in missing)) if missing else ""})
    return out


def _area_col(s: Step) -> str:
    return "emd_nm" if s.dataset.startswith("4-") else "bjd"


def _step_keys(s: Step):
    """(종류, 값 고르기 키, 컬럼, 값). 비교 대상(filters_b)은 같은 컬럼이라도 'b:컬럼' 키로 따로 묻는다."""
    for k, v in s.filters.items():
        yield ("filters", k, k, v)
    for k, v in (s.options.get("filters_b") or {}).items():
        yield ("filters_b", f"b:{k}", k, v)
    if "area" in s.options:
        yield ("area", _area_col(s), _area_col(s), s.options["area"])


def needs(plan: Plan, ws: Workspace, cat: Catalog) -> list:
    seen, out = set(), []
    for s in plan.steps:
        for kind, key, col, v in _step_keys(s):
            if str(v) == "?" and key not in seen:
                seen.add(key)
                label = cat.label(s.dataset, col) + (" (비교할 쪽)" if kind == "filters_b" else "")
                out.append({"key": key, "label": label, "dataset": s.dataset,
                            "options": ws.distinct(s.dataset, col), "top": ws.popular(s.dataset, col)})
    return out


def fill(plan: Plan, values: dict) -> Plan:
    p = copy.deepcopy(plan)
    for s in p.steps:
        for k, v in list(s.filters.items()):
            if str(v) == "?" and values.get(k):
                s.filters[k] = values[k]
        fb = s.options.get("filters_b") or {}
        for k, v in list(fb.items()):
            if str(v) == "?" and values.get(f"b:{k}"):
                fb[k] = values[f"b:{k}"]
        if str(s.options.get("area")) == "?":
            col = _area_col(s)
            if values.get(col):
                s.options["area"] = values[col]
    return p


def validate(plan: Plan, ws: Workspace, cat: Catalog) -> list:
    errs = []
    if not plan.steps:
        errs.append("계획에 단계가 없습니다.")
    for i, s in enumerate(plan.steps, 1):
        if s.tool not in TOOLS:
            errs.append(f"{i}단계: 없는 도구 '{s.tool}'")
            continue
        if s.dataset not in cat.ids():
            errs.append(f"{i}단계: 없는 데이터 '{s.dataset}'")
            continue
        if s.dataset not in ws.loaded():
            errs.append(f"{i}단계: 불러오지 않은 데이터 '{s.dataset}' — 불러온 데이터만 쓰세요: {ws.loaded()}")
            continue
        if s.metric not in cat.measures(s.dataset):
            errs.append(f"{i}단계: '{s.metric}'은(는) 지표 컬럼이 아님. 가능: {cat.measures(s.dataset)}")
        allowed = cat.allowed_cols(s.dataset)
        for b in s.by:
            if b not in allowed:
                errs.append(f"{i}단계: by의 '{b}'은(는) 없는 컬럼")
        for k in s.filters:
            if k not in allowed:
                errs.append(f"{i}단계: filters의 '{k}'은(는) 없는 컬럼")
        for k in (s.options.get("filters_b") or {}):
            if k not in allowed:
                errs.append(f"{i}단계: filters_b의 '{k}'은(는) 없는 컬럼")
        if s.tool == "contribution" and not (s.options.get("period_a") and s.options.get("period_b")):
            errs.append(f"{i}단계: contribution에는 options.period_a, period_b가 필요")
    return errs


def _normalize_values(plan: Plan, ws: Workspace):
    """데이터에 없는 필터 값은 '?'로 바꿔 이용자가 고르게 한다."""
    for s in plan.steps:
        if s.dataset not in ws.loaded():
            continue
        allowed = ws.cat.allowed_cols(s.dataset)
        targets = [s.filters, s.options.get("filters_b") or {}]
        for d in targets:
            for k, v in list(d.items()):
                if str(v) in ("?", "") or isinstance(v, list) or k not in allowed:
                    continue
                if str(v) not in ws.distinct(s.dataset, k, limit=5000):
                    d[k] = "?"
        area = s.options.get("area")
        if area not in (None, "?", "") and _area_col(s) in allowed and                 str(area) not in ws.distinct(s.dataset, _area_col(s), limit=5000):
            s.options["area"] = "?"


CODE_COLS = {"업종코드 및 업종명": "biz_nm"}


def _code_values(cat: Catalog, did: str) -> dict:
    """명세서(공개 자료) 참고표의 값 목록. 법정동처럼 긴 목록은 넣지 않는다(질문 속 값은 가려서 전달)."""
    out = {}
    for title, vals in cat.get(did).get("codes", {}).items():
        col = CODE_COLS.get(title)
        if col:
            out[col] = [v[1] if isinstance(v, list) else v for v in vals]
    return out


def schema_text(ws: Workspace, cat: Catalog) -> str:
    lines = []
    for did in ws.loaded():
        lines.append(f'데이터 id "{did}": {cat.name(did)}')
        codes = _code_values(cat, did)
        for c in cat.columns(did):
            note = re.sub(r"\s+", " ", c.get("note", ""))[:110]
            extra = f" 값: {', '.join(codes[c['name']])}" if c["name"] in codes else ""
            lines.append(f"  {c['name']} ({c['ko']}, {c['role']}) {note}{extra}".rstrip())
        for v in cat.virtual_sql(did):
            lines.append(f"  {v} ({VIRTUAL_LABEL[v]}, 가상 묶음 컬럼)")
        ds = next(d for d in ws.datasets() if d.id == did)
        if ds.months:
            lines.append(f"  기간: {ds.months[0]} ~ {ds.months[-1]}")
    return "\n".join(lines)


def _fix_dataset_ids(plan: Plan, cat: Catalog):
    for s in plan.steps:
        if s.dataset not in cat.ids():
            m = re.search(r"\d-\d\d", s.dataset)
            if m and m.group(0) in cat.ids():
                s.dataset = m.group(0)


SYSTEM = """당신은 제주빅데이터센터 데이터 분석 계획을 세우는 도우미입니다. 실제 데이터 값은 볼 수 없고, 아래 구조만 압니다.
계산은 PC 안의 도구가 합니다. 당신은 JSON 계획만 출력합니다.

도구:
{tools}

불러온 데이터:
{schema}

출력 형식(JSON 객체 하나):
{{"purpose":"{purpose}","steps":[{{"tool":"...","dataset":"1-08 같은 데이터 id만","metric":"지표 컬럼(count/amount/measure)","by":["묶음 컬럼"],"filters":{{"컬럼":"값"}},"options":{{}}}}],"ask":null}}
규칙:
- 질문 속 〔컬럼#번호〕는 가려진 실제 값입니다. 그 컬럼의 filters 값으로 그대로 쓰세요.
- 값을 모르면 "?"를 쓰면 이용자가 고릅니다. 〔수치#번호〕는 쓰지 마세요.
- 기간은 options.period=["YYYY-MM","YYYY-MM"]. 단계는 1~3개. 위에 있는 컬럼 이름만 쓰세요.
- metric은 반드시 role이 count/amount/measure인 컬럼 이름(예: use_amt 이용금액, use_cnt 이용건수). by는 1~2개.
- '언제·몇 시' 질문은 시간대 데이터(1-14의 time), '요일' 질문은 1-12의 week을 쓰세요(불러와 있을 때). 월별 흐름은 trend.
- 불러온 데이터 id만 쓰세요. 예시의 데이터가 불러와져 있지 않으면 그 단계는 빼세요.

예시 1) 질문: 〔bjd#1〕 〔biz_nm#2〕 손님은 누구이고 언제 오나요?
{{"purpose":"사업계획서","steps":[{{"tool":"share","dataset":"1-08","metric":"use_amt","by":["user_type"],"filters":{{"bjd":"〔bjd#1〕","biz_nm":"〔biz_nm#2〕"}},"options":{{}}}},{{"tool":"share","dataset":"1-08","metric":"use_cnt","by":["age_band"],"filters":{{"bjd":"〔bjd#1〕","biz_nm":"〔biz_nm#2〕"}},"options":{{}}}},{{"tool":"share","dataset":"1-14","metric":"use_cnt","by":["time"],"filters":{{"bjd":"〔bjd#1〕","biz_nm":"〔biz_nm#2〕"}},"options":{{}}}}],"ask":null}}
예시 2) 질문: 〔bjd#1〕과 〔bjd#2〕의 커피 매출 비교
{{"purpose":"사업계획서","steps":[{{"tool":"compare","dataset":"1-08","metric":"use_amt","by":["base_year_month"],"filters":{{"bjd":"〔bjd#1〕","biz_nm":"비알콜 음료점업"}},"options":{{"filters_b":{{"bjd":"〔bjd#2〕","biz_nm":"비알콜 음료점업"}}}}}}],"ask":null}}
예시 3) 질문: 2025년 6월 권역별 매출 순위
{{"purpose":"현황자료","steps":[{{"tool":"rank","dataset":"1-08","metric":"use_amt","by":["dstrct_se"],"filters":{{}},"options":{{"period":["2025-06","2025-06"],"top":10}}}}],"ask":null}}"""


def _ask_ai(question, purpose, ws, cat, outbound: Outbound, cache: PlanCache, notes: list):
    masker = Masker(ws.dim_values(), protected=_protected(ws, cat))
    tools = "\n".join(f"- {k}: {v}" for k, v in TOOL_HELP.items())
    system = SYSTEM.format(tools=tools, schema=schema_text(ws, cat), purpose=purpose)
    masked_q, _ = masker.mask(question)
    ck = PlanCache.key(masked_q, purpose, ws.loaded())
    hit = cache.get(ck)
    if hit:
        _, mapping = masker.mask(question)
        plan = Plan.from_dict(unmask(hit, mapping))
        plan.source = "ai"
        notes.append("같은 질문의 저장된 계획을 다시 썼습니다(AI 호출 없음).")
        return plan
    user = f"질문: {question}"
    for attempt in range(2):
        reply, mapping = outbound.send(system, user, masker, max_tokens=2500)
        try:
            raw = json.loads(reply.text)
            plan = Plan.from_dict(unmask(raw, mapping))
        except (ValueError, TypeError, AttributeError):
            user = f"질문: {question}\n이전 응답이 JSON이 아니었습니다. JSON 객체 하나만 출력하세요."
            continue
        plan.purpose = purpose if purpose in PURPOSES else plan.purpose
        plan.source = "ai"
        _fix_dataset_ids(plan, cat)
        errs = validate(plan, ws, cat)
        if not errs:
            cache.put(ck, raw)
            return plan
        user = f"질문: {question}\n이전 계획의 오류를 고쳐 다시 출력하세요:\n- " + "\n- ".join(errs)
    return None


def _protected(ws, cat) -> set:
    out = {cat.name(d) for d in cat.ids()}
    for did in ws.loaded():
        for c in cat.columns(did):
            out |= {c["name"], c["ko"]}
    return out


def _card_for_question(question: str, purpose: str, ws: Workspace, cat: Catalog):
    enabled = [c for c in CARD_LIST if all(d in ws.loaded() for d in c.datasets)]
    if not enabled:
        return None
    def score(c):
        hit = sum(1 for k in c.keywords if k in question)
        return (hit, c.purpose == purpose)
    best = max(enabled, key=score)
    return best


def plan_from_question(question: str, purpose: str, ws: Workspace, cat: Catalog, outbound: Outbound,
                       cache: PlanCache):
    notes = []
    plan = None
    try:
        plan = _ask_ai(question, purpose, ws, cat, outbound, cache, notes)
        if plan is None:
            notes.append("AI 계획이 검사를 통과하지 못해 비슷한 질문 카드로 대신합니다.")
    except ProviderUnavailable as e:
        notes.append(f"AI 없이 질문 카드로 진행합니다({e}).")
    if plan is None:
        card = _card_for_question(question, purpose, ws, cat)
        if card is None:
            raise ValueError("먼저 센터에서 받은 CSV 파일을 불러와 주세요.")
        plan = card_plan(card.id, ws, cat)
        notes.append(f"선택된 카드: {card.label}")
        return plan, notes
    _normalize_values(plan, ws)
    if plan.ask:
        notes.append(plan.ask)
    return plan, notes


def plan_text(plan: Plan, cat: Catalog) -> list:
    out = []
    for i, s in enumerate(plan.steps, 1):
        flt = ", ".join(f"{cat.label(s.dataset, k)}={'(고르기)' if str(v) == '?' else v}"
                        for k, v in s.filters.items())
        if "area" in s.options:
            flt = (flt + ", " if flt else "") + f"지역={'(고르기)' if s.options['area'] == '?' else s.options['area']}"
        by = "·".join(cat.label(s.dataset, b) for b in s.by)
        fb = s.options.get("filters_b")
        if fb:
            flt += " ↔ " + ", ".join(f"{cat.label(s.dataset, k)}={v}" for k, v in fb.items())
        per = s.options.get("period")
        out.append(f"{i}. 「{cat.name(s.dataset)}」에서 " + (f"[{flt}] 조건으로 " if flt else "") +
                   (f"{by}별 " if by else "") + f"{cat.label(s.dataset, s.metric)}의 {j(TOOLS[s.tool], '을')} 계산합니다"
                   + (f" (기간 {per[0]}~{per[1]})" if per else "") + ".")
    return out
