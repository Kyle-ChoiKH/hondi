"""계산 도구: 화이트리스트 컬럼만 쓰고 값은 모두 바인딩한다. AI는 이 도구의 이름과 인자만 고른다."""
from __future__ import annotations

import re
import statistics
import uuid

from .josa import j
from .catalog import Catalog
from .ingest import Workspace
from .model import Result, Step

TOOLS = {
    "trend": "추이", "yoy": "전년 동월 대비", "share": "구성비", "rank": "순위", "compare": "두 조건 비교",
    "contribution": "증감 기여도", "profile": "지역 프로필", "describe": "기술통계",
}
TOOL_HELP = {
    "trend": "by(시간 또는 묶음)별 합계. options.period=[시작월,끝월]",
    "yoy": "월별 합계와 12개월 전 대비 증감률",
    "share": "by별 비중(%)",
    "rank": "by별 합계 순위. options.top(기본 10)",
    "compare": "filters(가) 와 options.filters_b(나) 두 조건을 by별로 비교",
    "contribution": "options.period_a, options.period_b 두 기간 사이 by별 증감액과 기여율",
    "profile": "options.area(법정동 등) 하나의 요약 지표",
    "describe": "by별 월 합계의 평균·중앙값·최소·최대·표준편차",
}
APPLIED_SUFFIX = ("_pct", "_diff")
AVG_HINTS = ("per_", "average", "temperature", "price", "rate", "ratio", "avg", "wind_speed", "direction", "score")


def is_average(measure: str) -> bool:
    """1인당 금액·기온처럼 더하면 뜻이 없는 지표(평균으로 집계)."""
    return any(h in measure for h in AVG_HINTS)


NATURAL_ORDER = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일", "공휴일",
                 "월", "화", "수", "목", "금", "토", "일", "새벽", "오전", "점심", "오후", "저녁", "밤"]
_NAT = {v: i for i, v in enumerate(NATURAL_ORDER)}
NATURAL_DIMS = {"week", "day_of_week", "time", "base_hour", "age", "age_band"}


def natural_key(v):
    """요일·시간대는 달력 순서, 숫자(시각·연령)는 크기 순서, 나머지는 글자 순서."""
    s = str(v)
    if s in _NAT:
        return (0, _NAT[s], "")
    try:
        return (1, float(s), "")
    except ValueError:
        return (2, 0, s)


def is_applied(measure: str) -> bool:
    return measure == "rank" or measure.endswith(APPLIED_SUFFIX)


class Q:
    """한 데이터에 대한 안전한 SQL 조각 생성기."""

    def __init__(self, ws: Workspace, cat: Catalog, did: str):
        if did not in ws.loaded():
            raise ValueError(f"아직 불러오지 않은 데이터입니다: {cat.name(did) if did in cat.ids() else did}")
        self.ws, self.cat, self.did = ws, cat, did
        self.table = ws.table(did)
        self.virtual = cat.virtual_sql(did)
        self.allowed = cat.allowed_cols(did)
        self.time = cat.time_col(did)
        self.count = cat.count_col(did)

    def col(self, name: str) -> str:
        if name not in self.allowed:
            raise ValueError(f"쓸 수 없는 컬럼입니다: {name}")
        return self.virtual.get(name, f'"{name}"')

    def metric(self, name: str) -> str:
        if name not in self.cat.measures(self.did):
            raise ValueError(f"계산할 수 없는 지표입니다: {name}")
        return f'"{name}"'

    def agg(self, name: str) -> str:
        return f"{'avg' if is_average(name) else 'sum'}({self.metric(name)})"

    def where(self, filters: dict, period=None):
        parts, params = [], []
        for k, v in (filters or {}).items():
            expr = self.col(k)
            vals = v if isinstance(v, list) else [v]
            if any(str(x) == "?" or str(x).startswith("〔") for x in vals):
                raise ValueError(f"'{self.cat.label(self.did, k)}' 값을 먼저 골라 주세요.")
            parts.append(f"{expr} in ({', '.join('?' for _ in vals)})")
            params += [str(x) for x in vals]
        if period and self.time:
            a, b = period
            parts.append(f"substr({self.time},1,6) between ? and ?")
            params += [a.replace("-", ""), b.replace("-", "")]
        return (" where " + " and ".join(parts)) if parts else "", params

    def _is_count(self, metric) -> bool:
        c = self.cat.column(self.did, metric) if metric else None
        return bool(c) and (c["role"] == "count" or metric.endswith("_cnt"))

    def nexpr(self, metric=None) -> str:
        """10 미만 판정에 쓸 칸의 건수. 지표 자체가 건수·인원이면 그 합과 건수 컬럼 합 중 작은 값."""
        parts = [f'sum("{self.count}")'] if self.count else []
        if metric and metric != self.count and self._is_count(metric):
            parts.append(f'sum("{metric}")')
        if not parts:
            return "null"
        return parts[0] if len(parts) == 1 else f"least({', '.join(parts)})"

    def group(self, metric: str, by: list, filters: dict, period=None, order: str = "1"):
        exprs = [self.col(b) for b in by]
        w, p = self.where(filters, period)
        sel = ", ".join([f"{e} as \"{b}\"" for e, b in zip(exprs, by)] +
                        [f"{self.agg(metric)} as v", "count(*) as nr", f"{self.nexpr(metric)} as nc"])
        gb = (" group by " + ", ".join(str(i + 1) for i in range(len(by)))) if by else ""
        ob = f" order by {order}" if by else ""
        cur = self.ws.con.execute(f"select {sel} from {self.table}{w}{gb}{ob}", p)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def period_of(self, filters: dict, period=None):
        if not self.time:
            return ("", "")
        w, p = self.where(filters, period)
        a, b = self.ws.con.execute(f"select min(substr({self.time},1,6)), max(substr({self.time},1,6)) "
                                   f"from {self.table}{w}", p).fetchone()
        fmt = lambda x: f"{x[:4]}-{x[4:6]}" if x else ""  # noqa: E731
        return (fmt(a), fmt(b))


_YM = re.compile(r"^\d{4}-?\d{2}$")


def _period(v, name="기간"):
    """'2025-01', '2025-01~2025-06', ['2025-01'] 같은 여러 모양을 [시작, 끝]으로 맞춘다."""
    if v in (None, "", []):
        return None
    if isinstance(v, str):
        v = [x.strip() for x in re.split(r"[~,]", v) if x.strip()]
    if not isinstance(v, (list, tuple)) or not v:
        raise ValueError(f"{name} 형식을 알 수 없습니다(예: 2025-01~2025-06).")
    v = [str(x) for x in v][:2]
    if len(v) == 1:
        v = v * 2
    out = []
    for x in v:
        if not _YM.match(x):
            raise ValueError(f"{name} 형식을 알 수 없습니다: {x} (예: 2025-01)")
        out.append(x if "-" in x else f"{x[:4]}-{x[4:]}")
    return out


def _clean_options(opt: dict) -> dict:
    opt = dict(opt)
    for k, name in (("period", "기간"), ("period_a", "비교 기간(가)"), ("period_b", "비교 기간(나)")):
        if k in opt:
            opt[k] = _period(opt[k], name)
    try:
        opt["top"] = max(1, min(100, int(opt.get("top") or 10)))
    except (TypeError, ValueError):
        opt["top"] = 10
    if not isinstance(opt.get("filters_b") or {}, dict):
        raise ValueError("비교할 조건(filters_b) 형식을 알 수 없습니다.")
    return opt


def _num(v):
    if v is None:
        return None
    return int(v) if float(v).is_integer() else float(v)


def _title(cat, step: Step) -> str:
    by = ", ".join(cat.label(step.dataset, b) for b in step.by) if step.by else ""
    flt = " · ".join(f"{v}" for v in step.filters.values() if not isinstance(v, list))
    head = f"{cat.label(step.dataset, step.metric)} {TOOLS.get(step.tool, step.tool)}"
    return " ".join(x for x in [flt, head, f"({by})" if by else ""] if x)


def run_step(ws: Workspace, cat: Catalog, step: Step) -> Result:
    if step.tool not in TOOLS:
        raise ValueError(f"없는 도구입니다: {step.tool}")
    q = Q(ws, cat, step.dataset)
    opt = _clean_options(step.options or {})
    step.options = opt
    period = opt.get("period")
    if is_average(step.metric) and step.tool in ("share", "contribution", "profile"):
        raise ValueError(f"{j(cat.label(step.dataset, step.metric), '은')} 평균형 지표라 구성비·기여도·합계를 낼 수 없습니다. 추이·순위·비교로 보세요.")
    by = list(step.by)
    m = step.metric
    rows, measures, dims = [], [m], by

    if step.tool == "trend":
        if not by:
            by = dims = [q.time]
        for r in q.group(m, by, step.filters, period):
            rows.append({**{b: r[b] for b in by}, m: _num(r["v"]), "_n_rows": r["nr"], "_n_count": _num(r["nc"])})

    elif step.tool == "share":
        g = q.group(m, by, step.filters, period, order="v desc")
        tot = sum((r["v"] or 0) for r in g) or 1
        measures = [f"{m}_pct"]
        for r in g:
            rows.append({**{b: r[b] for b in by}, f"{m}_pct": round((r["v"] or 0) / tot * 100, 1),
                         "_n_rows": r["nr"], "_n_count": _num(r["nc"])})

    elif step.tool == "rank":
        g = q.group(m, by, step.filters, period, order="v desc")[: int(opt.get("top", 10))]
        measures = ["rank"] if opt.get("rank_only") else ["rank", m]
        for i, r in enumerate(g, 1):
            rows.append({**{b: r[b] for b in by}, "rank": i, m: _num(r["v"]),
                         "_n_rows": r["nr"], "_n_count": _num(r["nc"])})

    elif step.tool == "yoy":
        if not q.time:
            raise ValueError("시간 컬럼이 없는 데이터입니다.")
        key = "base_year_month"
        w, p = q.where(step.filters, None)
        cur = ws.con.execute(f"select substr({q.time},1,6) ym, {q.agg(m)} v, count(*) nr, {q.nexpr(m)} nc "
                             f"from {q.table}{w} group by 1 order by 1", p)
        g = {r[0]: r for r in cur.fetchall()}
        dims, measures = [key], [m, "yoy_pct"]
        for ym, (_, v, nr, nc) in g.items():
            if period and not (period[0].replace("-", "") <= ym <= period[1].replace("-", "")):
                continue
            prev = g.get(f"{int(ym[:4]) - 1}{ym[4:]}")
            pct = round((v - prev[1]) / prev[1] * 100, 1) if prev and prev[1] else None
            n_pct = min(x for x in (nc, prev[3] if prev else None) if x is not None) if (nc is not None or prev) else None
            rows.append({key: ym, m: _num(v), "yoy_pct": pct, "_n_rows": nr, "_n_count": _num(nc),
                         "_n:yoy_pct": _num(n_pct), "_r:yoy_pct": min(nr, prev[2]) if prev else nr})

    elif step.tool == "compare":
        fb = opt.get("filters_b") or {}
        ga = {tuple(r[b] for b in by): r for r in q.group(m, by, step.filters, period)}
        gb = {tuple(r[b] for b in by): r for r in q.group(m, by, fb, period)}
        measures = [f"{m}_a", f"{m}_b", "diff_pct"]
        for k in sorted(set(ga) | set(gb), key=lambda x: tuple(str(i) for i in x)):
            a, b = ga.get(k), gb.get(k)
            va, vb = (a["v"] if a else 0) or 0, (b["v"] if b else 0) or 0
            rows.append({**dict(zip(by, k)), f"{m}_a": _num(va), f"{m}_b": _num(vb),
                         "diff_pct": round((va - vb) / vb * 100, 1) if vb else None,
                         "_n_rows": min(a["nr"] if a else 0, b["nr"] if b else 0),
                         "_n_count": _num(min((a["nc"] or 0) if a else 0, (b["nc"] or 0) if b else 0))
                         if q.count else None,
                         f"_n:{m}_a": _num(a["nc"]) if a else 0, f"_n:{m}_b": _num(b["nc"]) if b else 0,
                         f"_r:{m}_a": a["nr"] if a else 0, f"_r:{m}_b": b["nr"] if b else 0})

    elif step.tool == "contribution":
        pa, pb = opt.get("period_a"), opt.get("period_b")
        if not pa or not pb:
            raise ValueError("비교할 두 기간(period_a, period_b)이 필요합니다.")
        ga = {tuple(r[b] for b in by): r for r in q.group(m, by, step.filters, pa)}
        gb = {tuple(r[b] for b in by): r for r in q.group(m, by, step.filters, pb)}
        total = sum((r["v"] or 0) for r in gb.values()) - sum((r["v"] or 0) for r in ga.values())
        measures = [f"{m}_a", f"{m}_b", "change_diff", "contrib_pct"]
        for k in sorted(set(ga) | set(gb), key=lambda x: tuple(str(i) for i in x)):
            a, b = ga.get(k), gb.get(k)
            va, vb = (a["v"] if a else 0) or 0, (b["v"] if b else 0) or 0
            rows.append({**dict(zip(by, k)), f"{m}_a": _num(va), f"{m}_b": _num(vb),
                         "change_diff": _num(vb - va),
                         "contrib_pct": round((vb - va) / total * 100, 1) if total else None,
                         "_n_rows": min(a["nr"] if a else 0, b["nr"] if b else 0),
                         "_n_count": _num(min((a["nc"] or 0) if a else 0, (b["nc"] or 0) if b else 0))
                         if q.count else None})
        period = [pa[0], pb[1]]

    elif step.tool == "profile":
        area = opt.get("area")
        area_col = next((c for c in ("bjd", "emd_nm", "bjd_nm", "dstrct_se", "city") if c in q.allowed), None)
        if not area or not area_col:
            raise ValueError("프로필을 볼 지역을 골라 주세요.")
        f = {**step.filters, area_col: area}
        dims, measures = ["지표"], ["값"]
        tot = q.group(m, [], f, period)
        t = tot[0] if tot else {"v": 0, "nr": 0, "nc": 0}
        rows.append({"지표": f"{cat.label(step.dataset, m)} 합계", "값": _num(t["v"]), "_n_rows": t["nr"],
                     "_n_count": _num(t["nc"])})
        if q.count and q.count != m:
            rows.append({"지표": f"{cat.label(step.dataset, q.count)} 합계",
                         "값": _num(q.group(q.count, [], f, period)[0]["v"]), "_n_rows": t["nr"],
                         "_n_count": _num(t["nc"])})
        for col, label in (("biz_nm", "업종"), ("user_type", "이용자"), ("age", "연령대")):
            if col in q.allowed:
                g = q.group(m, [col], f, period, order="v desc")
                tv = sum((r["v"] or 0) for r in g) or 1
                for r in g[:3 if col == "biz_nm" else 1]:
                    rows.append({"지표": f"주요 {label}: {r[col]} 비중(%)", "값": round((r["v"] or 0) / tv * 100, 1),
                                 "_n_rows": r["nr"], "_n_count": _num(r["nc"]), "_applied": True})

    elif step.tool == "describe":
        if not q.time:
            raise ValueError("시간 컬럼이 없는 데이터입니다.")
        ym = f"substr({q.time},1,6)"
        exprs = [q.col(b) for b in by]
        w, p = q.where(step.filters, period)
        sel = ", ".join([f"{e} as \"{b}\"" for e, b in zip(exprs, by)] +
                        [f"{ym} ym", f"{q.agg(m)} v", "count(*) nr", f"{q.nexpr(m)} nc"])
        gb = ", ".join(str(i + 1) for i in range(len(by) + 1))
        cur = ws.con.execute(f"select {sel} from {q.table}{w} group by {gb} order by {gb}", p)
        groups = {}
        for r in cur.fetchall():
            groups.setdefault(tuple(r[: len(by)]), []).append(r[len(by):])
        measures = ["mean", "median", "min", "max", "std"]
        for k, items in groups.items():
            vals = [float(x[1] or 0) for x in items]
            rows.append({**dict(zip(by, k)), "mean": _num(round(statistics.mean(vals), 1)),
                         "median": _num(round(statistics.median(vals), 1)), "min": _num(min(vals)),
                         "max": _num(max(vals)), "std": round(statistics.pstdev(vals), 1),
                         "_n_rows": min(x[2] for x in items),
                         "_n_count": _num(min((x[3] or 0) for x in items)) if q.count else None})

    if dims and dims[0] in NATURAL_DIMS and step.tool in ("trend", "describe", "compare", "contribution"):
        rows.sort(key=lambda r: tuple(natural_key(r.get(d)) for d in dims))
    kind = "applied" if all(is_applied(x) for x in measures) else "simple"
    return Result(id=uuid.uuid4().hex[:10], title=_title(cat, step), step=step, dims=list(dims),
                  measures=measures, rows=rows, agg_kind=kind,
                  period=q.period_of(step.filters if step.tool != "profile" else {}, period),
                  masked=set(), notes=[])
