"""결과 해설(문장 틀)과 데이터 한계·출처 문구. AI 해설은 스위치를 켠 경우 초록 결과에만."""
from __future__ import annotations

import json

from .josa import j
from .catalog import Catalog
from .firewall import Masker, Outbound, unmask
from .llm import ProviderUnavailable
from .model import Assessment, Result
from .tools import TOOLS


def fmt_value(v, col: str, cat: Catalog = None, did: str = "") -> str:
    if v is None:
        return "-"
    role = ""
    if cat and did:
        c = cat.column(did, col.removesuffix("_a").removesuffix("_b"))
        role = c["role"] if c else ""
    if col.endswith("_pct"):
        return f"{v:,.1f}%"
    if role == "amount":
        # 금액은 원 단위 그대로(게시판 답변 2026-11-15: 단위를 줄여 '3.2'처럼 쓰지 않기)
        return f"{v:,.0f}원"
    if isinstance(v, float):
        return f"{v:,.1f}"
    return f"{v:,}"


def _visible(result: Result, m: str):
    return [(i, r) for i, r in enumerate(result.rows) if (i, m) not in result.masked and r.get(m) is not None]


def _lab(r: dict, dims: list) -> str:
    return " ".join(_ym(r.get(d)) if d == "base_year_month" else str(r.get(d)) for d in dims) if dims else "전체"


def _ym(v) -> str:
    s = str(v)
    return f"{s[:4]}년 {int(s[4:6])}월" if len(s) == 6 and s.isdigit() else s


def narrate(result: Result, cat: Catalog) -> list:
    did, t, out = result.step.dataset, result.step.tool, []
    mlabel = cat.label(did, result.step.metric)
    if not result.rows:
        return ["조건에 맞는 데이터가 없습니다. 기간이나 조건을 넓혀 보세요."]
    if t == "trend":
        m = result.measures[0]
        vis = _visible(result, m)
        if len(vis) >= 2 and len(result.dims) == 1:
            (_, a), (_, b) = vis[0], vis[-1]
            d0 = result.dims[0]
            if a[m]:
                pct = (b[m] - a[m]) / a[m] * 100
                out.append(f"{_ym(a[d0])} {fmt_value(a[m], m, cat, did)}에서 {_ym(b[d0])} "
                           f"{fmt_value(b[m], m, cat, did)}로 {abs(pct):.1f}% {'늘었' if pct >= 0 else '줄었'}습니다.")
            top = max(vis, key=lambda x: x[1][m])[1]
            out.append(f"{j(mlabel, '이')} 가장 많은 때는 {_ym(top[d0])}입니다.")
    elif t == "share":
        m = result.measures[0]
        vis = sorted(_visible(result, m), key=lambda x: -x[1][m])
        if vis:
            a = vis[0][1]
            s = f"{mlabel} 기준으로 {j(chr(39) + _lab(a, result.dims) + chr(39), '이')} {a[m]:.1f}%로 가장 큰 비중입니다."
            if len(vis) > 1:
                b = vis[1][1]
                s += f" 다음은 '{_lab(b, result.dims)}'({b[m]:.1f}%)입니다."
            out.append(s)
    elif t == "rank":
        vis = _visible(result, "rank")
        names = [f"{r['rank']}위 {_lab(r, result.dims)}" for _, r in vis[:3]]
        if names:
            out.append(f"{mlabel} 순위는 " + ", ".join(names) + " 순입니다.")
    elif t == "yoy":
        vis = [x for x in _visible(result, "yoy_pct")]
        if vis:
            r = vis[-1][1]
            out.append(f"{_ym(r['base_year_month'])} {j(mlabel, '은')} 1년 전보다 {abs(r['yoy_pct']):.1f}% "
                       f"{'늘었' if r['yoy_pct'] >= 0 else '줄었'}습니다.")
        else:
            out.append("1년 전 같은 달 데이터가 없어 전년 대비를 계산할 수 없습니다. 13개월 이상 불러와 주세요.")
    elif t == "compare":
        m = result.measures[0]
        ma, mb = result.measures[0], result.measures[1]
        sa = sum(r[ma] for i, r in _visible(result, ma))
        sb = sum(r[mb] for i, r in _visible(result, mb))
        fa = ", ".join(str(v) for v in result.step.filters.values())
        fb = ", ".join(str(v) for v in (result.step.options.get("filters_b") or {}).values())
        if sb:
            pct = (sa - sb) / sb * 100
            out.append(f"'{fa}'의 {j(mlabel, '이')} '{fb}'보다 {abs(pct):.1f}% {'많' if pct >= 0 else '적'}습니다.")
    elif t == "contribution":
        vis = _visible(result, "change_diff")
        if vis:
            up = max(vis, key=lambda x: x[1]["change_diff"])[1]
            dn = min(vis, key=lambda x: x[1]["change_diff"])[1]
            out.append(f"가장 크게 늘어난 쪽은 '{_lab(up, result.dims)}'({fmt_value(up['change_diff'], result.step.metric, cat, did)})입니다.")
            if dn["change_diff"] < 0:
                out.append(f"가장 크게 줄어든 쪽은 '{_lab(dn, result.dims)}'({fmt_value(dn['change_diff'], result.step.metric, cat, did)})입니다.")
    elif t == "profile":
        vis = _visible(result, "값")
        if vis:
            r0 = vis[0][1]
            out.append(f"{result.step.options.get('area')}의 {r0['지표']}는 {fmt_value(r0['값'], result.step.metric, cat, did)}입니다.")
            biz = [r for _, r in vis if r["지표"].startswith("주요 업종")]
            if biz:
                out.append("주요 업종은 " + ", ".join(r["지표"].split(": ", 1)[1].replace(" 비중(%)", "") +
                                                    f"({r['값']:.1f}%)" for r in biz) + "입니다.")
    elif t == "describe":
        vis = _visible(result, "mean")
        if vis:
            top = max(vis, key=lambda x: x[1]["mean"])[1]
            out.append(f"월평균 {j(mlabel, '이')} 가장 큰 곳은 '{_lab(top, result.dims)}'"
                       f"({fmt_value(top['mean'], result.step.metric, cat, did)})입니다.")
    if result.masked:
        out.append("10 미만으로 가린 칸은 설명에서 뺐습니다.")
    counts = [r.get("_n_count") for r in result.rows if r.get("_n_count") is not None]
    if counts and sum(counts) < 30:
        out.append("이용 건수가 적어 해석에 주의가 필요합니다.")
    return out[:4]


# ---------- 한 줄 요약: AI를 모르는 이용자도 결과를 바로 알아듣게(화면 맨 위, 해요체) ----------
HOWTO = {
    "trend": "선이 오르면 늘어난 것, 내려가면 줄어든 거예요. 회색 칸은 자료가 없거나 10 미만이라 가린 곳이에요.",
    "yoy": "막대는 그달 값, 해설의 %는 작년 같은 달과 비교한 변화예요. 13개월 이상 넣어야 계산돼요.",
    "share": "막대가 길수록 차지하는 몫이 커요. 모두 더하면 100%예요.",
    "rank": "위에 있을수록 많아요. 빗금 칸은 10 미만이라 가린 곳이에요.",
    "compare": "두 색 막대가 두 조건이에요. 같은 달끼리 높이를 비교해 보세요.",
    "contribution": "파란 막대는 늘어난 쪽, 주황 막대는 줄어든 쪽이에요. 길수록 변화에 크게 영향을 줬어요.",
    "profile": "한 동네의 핵심 숫자를 한 장에 모았어요. 사업계획서·현황 보고의 첫 장으로 쓰기 좋아요.",
    "describe": "평균은 보통 수준, 표준편차가 클수록 달마다 들쭉날쭉하다는 뜻이에요.",
}


def won_friendly(v) -> str:
    """말하듯 읽히는 금액. 줄인 단위의 값이 10보다 작아지지 않게(10만 원 미만은 원 그대로)."""
    if v is None:
        return "-"
    a = abs(v)
    if a >= 1e9:
        return f"약 {v / 1e8:,.1f}억 원"
    if a >= 1e5:
        return f"약 {v / 1e4:,.0f}만 원"
    return f"{v:,.0f}원"


def _amount(v, m: str, cat: Catalog, did: str) -> str:
    c = cat.column(did, m.removesuffix("_a").removesuffix("_b")) if cat and did else None
    return won_friendly(v) if c and c["role"] == "amount" else fmt_value(v, m, cat, did)


def _unit(cat: Catalog, did: str, metric: str) -> str:
    """'10건 중 N건꼴'에 쓸 단위. 사람 수면 명, 건수면 건, 금액 등은 없음."""
    c = cat.column(did, metric) or {}
    if c.get("role") != "count":
        return ""
    lab = cat.label(did, metric)
    return "명" if any(w in lab for w in ("자", "인구", "사람", "명")) else "건"


def _q(r: dict, dims: list) -> str:
    return "'" + _lab(r, dims) + "'"


def _any_masked(result: Result, m: str) -> bool:
    return any(mm == m for _, mm in result.masked)


HIDDEN = "가린 칸을 빼고 보면 "  # 가린 칸이 더 클 수 있으니 '가장'이라고 단정하지 않는다


def headline(result: Result, cat: Catalog) -> str:
    did, t = result.step.dataset, result.step.tool
    mlabel = cat.label(did, result.step.metric)
    if not result.rows:
        return "조건에 맞는 데이터가 없어요. 기간이나 조건을 넓혀 보세요."
    if t == "trend":
        m = result.measures[0]
        vis = _visible(result, m)
        if not vis:
            return ""
        d0 = result.dims[0] if result.dims else ""
        if len(result.dims) == 1 and d0 in ("base_year_month", "quarter", "year", "base_date") and len(vis) >= 2 \
                and vis[0][1][m]:  # 기준이 둘 이상이면 처음·끝 행이 서로 다른 계열이라 비교하지 않는다
            a, b = vis[0][1], vis[-1][1]
            pct = (b[m] - a[m]) / a[m] * 100
            if abs(pct) < 1:
                return f"{_ym(a[d0])}부터 {_ym(b[d0])}까지 {j(mlabel, '이')} 거의 그대로예요."
            return (f"{_ym(a[d0])}보다 {_ym(b[d0])}에 {j(mlabel, '이')} {abs(pct):,.0f}% "
                    f"{'늘었어요' if pct > 0 else '줄었어요'}.")
        top = max(vis, key=lambda x: x[1][m])[1]
        pre = HIDDEN if _any_masked(result, m) else ""
        return f"{pre}{j(mlabel, '이')} 가장 많은 때는 {j(_q(top, result.dims), '예요')} ({_amount(top[m], m, cat, did)})."
    if t == "share":
        m = result.measures[0]
        vis = sorted(_visible(result, m), key=lambda x: -x[1][m])
        if not vis:
            return ""
        a = vis[0][1]
        if _any_masked(result, m):
            return f"{HIDDEN}{j(_q(a, result.dims), '이')} 가장 큰 몫이에요 ({a[m]:.1f}%)."
        unit = _unit(cat, did, result.step.metric)
        k = round(a[m] / 10)
        if unit and k >= 10:
            return f"거의 다 {j(_q(a, result.dims), '예요')} ({a[m]:.1f}%)."
        if unit and k >= 1:
            return f"가장 많은 건 {j(_q(a, result.dims), '예요')}. 10{unit} 중 {k}{unit}꼴이에요 ({a[m]:.1f}%)."
        return f"가장 큰 몫은 {j(_q(a, result.dims), '예요')}. {mlabel}의 {a[m]:.1f}%를 차지해요."
    if t == "rank":
        m = next((x for x in result.measures if x != "rank"), None)
        vis = [r for i, r in enumerate(result.rows) if (i, "rank") not in result.masked and r.get("rank") is not None
               and (m is None or ((i, m) not in result.masked and r.get(m) is not None))]
        if not vis:
            return ""
        first = vis[0]
        if first.get("rank") != 1:
            return f"{HIDDEN}{mlabel} {first.get('rank')}위인 {j(_q(first, result.dims), '이')} 가장 높아요."
        s = f"{mlabel} 1위는 {j(_q(first, result.dims), '예요')}"
        second = next((r for r in vis[1:] if r.get("rank") == 2), None)
        if m and second and second.get(m):
            ratio = first[m] / second[m]
            s += (f". 2위 {_q(second, result.dims)}보다 {ratio:.1f}배 많아요" if ratio >= 1.1
                  else f". 2위 {j(_q(second, result.dims), '와')} 거의 비슷해요")
        return s + "."
    if t == "yoy":
        vis = _visible(result, "yoy_pct")
        if not vis:
            return "1년 전 같은 달 자료가 없어 작년과 비교할 수 없어요. 13개월 이상 넣어 주세요."
        r = vis[-1][1]
        return (f"{_ym(r['base_year_month'])} {j(mlabel, '은')} 작년 같은 달보다 {abs(r['yoy_pct']):.1f}% "
                f"{'늘었어요' if r['yoy_pct'] >= 0 else '줄었어요'}.")
    if t == "compare":
        ma, mb = result.measures[0], result.measures[1]
        both = [r for i, r in enumerate(result.rows) if (i, ma) not in result.masked and (i, mb) not in result.masked
                and r.get(ma) is not None and r.get(mb) is not None]  # 양쪽 모두 보이는 행끼리만 비교
        sa, sb = sum(r[ma] for r in both), sum(r[mb] for r in both)
        fa = ", ".join(str(v) for v in result.step.filters.values())
        fb = ", ".join(str(v) for v in (result.step.options.get("filters_b") or {}).values())
        if not sb or not sa:
            return ""
        big, small, ratio = (fa, fb, sa / sb) if sa >= sb else (fb, fa, sb / sa)
        return f"{j(mlabel, '은')} '{big}' 쪽이 '{small}'보다 {ratio:.1f}배 많아요." if ratio >= 1.1 \
            else f"{j(chr(39) + fa + chr(39), '와')} '{fb}'의 {j(mlabel, '은')} 거의 비슷해요."
    if t == "contribution":
        vis = _visible(result, "change_diff")
        if not vis:
            return ""
        up = max(vis, key=lambda x: x[1]["change_diff"])[1]
        dn = min(vis, key=lambda x: x[1]["change_diff"])[1]
        if up["change_diff"] > 0:
            return f"가장 크게 늘어난 건 {j(_q(up, result.dims), '예요')} (+{_amount(up['change_diff'], result.step.metric, cat, did)})."
        return f"가장 크게 줄어든 건 {j(_q(dn, result.dims), '예요')} ({_amount(dn['change_diff'], result.step.metric, cat, did)})."
    if t == "profile":
        vis = [r for _, r in _visible(result, "값")]
        biz = [r for r in vis if str(r["지표"]).startswith("주요 업종")]
        area = result.step.options.get("area")
        top_hidden = any((i, "값") in result.masked for i, r in enumerate(result.rows)
                         if str(r.get("지표", "")).startswith("주요 업종"))
        if biz and not top_hidden:
            top = biz[0]
            name = top["지표"].split(": ", 1)[1].replace(" 비중(%)", "")
            return f"{area}에서 가장 큰 업종은 {j(chr(39) + name + chr(39), '예요')}. 전체의 {top['값']:.1f}%를 차지해요."
        return f"{area}의 핵심 숫자를 한 장에 모았어요." if area else ""
    if t == "describe":
        vis = _visible(result, "mean")
        if not vis:
            return ""
        top = max(vis, key=lambda x: x[1]["mean"])[1]
        return f"월평균 {j(mlabel, '이')} 가장 큰 곳은 {j(_q(top, result.dims), '예요')} ({_amount(top['mean'], result.step.metric, cat, did)})."
    return ""


def caveats(result: Result, cat: Catalog, demo: bool = False) -> list:
    d = cat.get(result.step.dataset)
    out = []
    if demo:
        out.append("예시(가상) 데이터로 만든 결과입니다. 실제 센터 데이터가 아닙니다.")
    if "비씨카드" in d.get("provider", ""):
        out.append("비씨카드 결제 기준으로, 전체 소비가 아닌 표본입니다.")
    if result.step.dataset in ("1-11", "1-12"):
        out.append("공휴일은 원래 요일에도 함께 집계되어 요일 합계가 실제보다 클 수 있습니다.")
    if d.get("category") == "통신" and "유동인구" in d["name"]:
        out.append("유동인구는 시간대별 인구를 더한 값(연인원)이라 실제 인구 수보다 큽니다.")
    if "나이스" in d.get("provider", ""):
        out.append("외식업 포스(POS) 표본 점포 기준입니다.")
    if result.step.dataset == "1-30":
        out.append("제주도민의 온라인 결제 전체(비씨카드 한정)입니다.")
    return out


def source_line(result: Result, cat: Catalog) -> str:
    a, b = result.period
    per = f"({a}~{b})" if a else ""
    return f"출처: 제주빅데이터센터, {cat.name(result.step.dataset)}{per}"


def narrate_ai(result: Result, assessment: Assessment, cat: Catalog, outbound: Outbound, masker: Masker,
               send_aggregates: bool):
    """집계값 전송 스위치가 켜져 있고, 반출 기준 충족 예상(초록)이며 30행 이하인 표만 AI에 보낸다."""
    if not send_aggregates or assessment.light != "green" or len(result.rows) > 30 or not result.rows:
        return None
    lines, nums = [], set()
    for i, r in enumerate(result.rows):  # 가린 칸은 값 대신 '가림'으로만 보낸다
        shown = [m for m in result.measures if (i, m) not in result.masked]
        cells = [f"{d}={r.get(d)}" for d in result.dims] +                 [f"{m}={r.get(m)}" if m in shown else f"{m}=가림" for m in result.measures]
        nums |= {str(r.get(m)) for m in shown if r.get(m) is not None}
        lines.append(", ".join(cells))
    system = ("당신은 분석 결과를 비전문가에게 설명합니다. 표의 수치만 근거로 쉬운 한국어 2~3문장을 쓰세요. "
              "〔...〕 자리표시자는 그대로 쓰세요. JSON {\"sentences\":[...]} 로만 답하세요.")
    user = f"{result.title} ({TOOLS[result.step.tool]})\n" + "\n".join(lines)
    try:
        reply, mapping = outbound.send(system, user, masker, allow_numbers=nums, max_tokens=1500)
        data = unmask(json.loads(reply.text), mapping)
        sents = [str(s) for s in data.get("sentences", [])][:3]
        return sents or None
    except (ProviderUnavailable, ValueError, AttributeError, TypeError):
        return None
