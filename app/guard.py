"""반출 지킴이: 제주빅데이터센터 데이터 반출 정책(2026.09.01 개정)과 대회 게시판 답변을 규칙으로 옮긴 것.

판정은 "충족 예상"일 뿐이며 최종 반출 여부는 센터 심사가 결정한다.
"""
from __future__ import annotations

import copy
import uuid

from .josa import j
from .catalog import Catalog
from .model import Assessment, Fix, Result
from .tools import is_applied, run_step

LIMIT = 10
DERIVED = ("diff_pct", "change_diff", "contrib_pct")
FINAL_NOTE = "최종 반출 여부는 센터 심사로 결정됩니다."
LIGHT_TEXT = {"green": "충족 예상", "yellow": "고치면 가능", "red": "원본·10 미만 포함"}


def cell_count(row: dict, m: str):
    n = row.get(f"_n:{m}", row.get("_n_count"))
    if n is None:
        n = row.get(f"_r:{m}", row.get("_n_rows"))
    return n


def cell_rows(row: dict, m: str):
    return row.get(f"_r:{m}", row.get("_n_rows"))


def cell_applied(row: dict, m: str) -> bool:
    return is_applied(m) or bool(row.get("_applied"))


def is_small(row: dict, m: str) -> bool:
    """10 미만 판정. 바탕 건수가 10 미만이거나, 단순집계(합계·평균·사칙연산 값)는 최종 값 자체가 10 미만이면 해당.
    (대회 게시판 답변 2026-11-15: '10 미만'은 최종 결과값 기준, 금액에도 적용. 비율·순위·증감률 등 응용집계는 수치 포함 가능)"""
    if (cell_count(row, m) or 0) < LIMIT:
        return True
    v = row.get(m)
    return not cell_applied(row, m) and isinstance(v, (int, float)) and abs(v) < LIMIT


def _cells(result: Result):
    for i, r in enumerate(result.rows):
        for m in result.measures:
            if r.get(m) is None:
                continue
            yield i, m, r


def apply_suppression(result: Result) -> Result:
    out = copy.deepcopy(result)
    out.id = uuid.uuid4().hex[:10]
    masked = set(out.masked)
    parts = [m for m in out.measures if m.endswith(("_a", "_b"))]
    derived = [m for m in out.measures if m in DERIVED]

    def one_pass() -> bool:
        before = len(masked)
        for m in out.measures:
            cells = [(i, r) for i, r in enumerate(out.rows) if r.get(m) is not None]
            small = {i for i, r in cells if is_small(r, m)}
            col_masked = {i for i, mm in masked if mm == m} | small
            if len(col_masked) == 1 and len(cells) > 1:
                rest = [(cell_count(r, m) or 0, i) for i, r in cells if i not in col_masked]
                if rest:
                    col_masked.add(min(rest)[1])
            masked.update((i, m) for i in col_masked)
        # 비교·증감 결과: (가)나 (나)를 가린 행은 차이·증감·기여율도 가려야 남은 칸으로 되살릴 수 없다
        for i in range(len(out.rows)):
            if any((i, p) in masked for p in parts):
                masked.update((i, d) for d in derived)
        return len(masked) != before

    for _ in range(6):
        if not one_pass():
            break
    out.masked = masked
    if "suppressed" not in out.notes:
        out.notes.append("suppressed")
    return out


def assess(result: Result, catalog: Catalog, fmt: str = "png") -> Assessment:
    did = result.step.dataset
    simple = any(not is_applied(m) for m in result.measures)
    kind = "단순집계" if simple else "응용집계"
    if not catalog.is_sensitive(did):
        return Assessment("green", [f"{j(catalog.name(did), '은')} 원본 반출이 가능한 데이터입니다. {FINAL_NOTE}"], [], kind)
    reasons, light = [], "green"

    def worse(level):
        nonlocal light
        order = {"green": 0, "yellow": 1, "red": 2}
        if order[level] > order[light]:
            light = level

    if not result.rows:
        worse("yellow")
        reasons.append("결과가 비어 있습니다. 조건을 넓혀 보세요.")
    if fmt in ("csv", "xlsx", "txt") and simple:
        worse("red")
        reasons.append("이 데이터는 텍스트·스프레드시트(csv, 엑셀) 반출이 원칙적으로 불가합니다. 그림(PNG)이나 보고서(PDF)로 반출하세요.")

    cells = list(_cells(result))
    small_simple = [(i, m) for i, m, r in cells if not cell_applied(r, m) and (i, m) not in result.masked
                    and is_small(r, m)]
    if small_simple:
        worse("red")
        reasons.append(f"10 미만 단순집계 칸이 {len(small_simple)}개 있습니다(반출 불가 — 바탕 건수나 최종 값이 10 미만). "
                       "범주처리·삭제처리·비율 변환이 필요합니다.")
        simple_total = sum(1 for i, m, r in cells if not cell_applied(r, m))
        if simple_total and len(small_simple) / simple_total > 0.5:
            reasons.append("가릴 칸이 너무 많습니다. 상위 단위로 묶는 것을 권합니다.")
    for m in result.measures:
        k = sum(1 for i, mm in result.masked if mm == m)
        n_cells = sum(1 for r in result.rows if r.get(m) is not None)
        if k == 1 and n_cells > 1:
            worse("red")
            reasons.append(f"'{m}' 열에서 가린 칸이 하나뿐이라 합계로 역산될 수 있습니다. 한 칸을 더 가려야 합니다.")
    single = [(i, m) for i, m, r in cells if not cell_applied(r, m) and (i, m) not in result.masked
              and cell_rows(r, m) == 1 and (cell_count(r, m) or 0) >= LIMIT]
    if single:
        worse("yellow")
        reasons.append(f"원본 한 행만 묶인 칸이 {len(single)}개 있습니다. 발췌로 볼 수 있어 묶거나 가리는 것이 안전합니다.")
    small_applied = [(i, m) for i, m, r in cells if cell_applied(r, m) and (i, m) not in result.masked
                     and (cell_count(r, m) or 0) < LIMIT]
    if small_applied:
        worse("yellow")
        reasons.append(f"분모가 10 미만인 비율·순위 칸이 {len(small_applied)}개 있습니다. 작은 값이 유추되지 않게 묶거나 가리세요.")
    if light == "green":
        reasons.append("10 미만 칸이 없고 역산할 수 없는 형태입니다.")
    reasons.append(FINAL_NOTE)
    fixes = fixes_for(result, catalog) if light != "green" else []
    return Assessment(light, reasons, fixes, kind)


def fixes_for(result: Result, catalog: Catalog) -> list:
    did, out = result.step.dataset, []
    for col in result.step.by:
        parent = catalog.rollup_parent(did, col)
        if parent:
            out.append(Fix(f"rollup:{col}>{parent}",
                           f"{j(catalog.label(did, col), '을')} {j(catalog.label(did, parent), '로')} 묶기 (범주처리)",
                           "rollup", {"col": col, "to": parent}))
            break
    time = catalog.time_col(did)
    if any(not is_applied(m) for m in result.measures) and result.step.tool in ("trend", "rank", "compare") \
            and result.step.by and result.step.by[0] != time:
        out.append(Fix("to_share", "금액·건수 대신 비중(%)으로 바꾸기 (응용집계)", "to_share", {}))
    out.append(Fix("suppress", "10 미만 칸 가리기 + 역산 막기 (삭제처리)", "suppress", {}))
    out.append(Fix("no_numbers", "그림에서 수치 빼기", "no_numbers", {}))
    return out


def apply_fix(ws, catalog: Catalog, result: Result, fix: Fix) -> Result:
    if fix.op == "rollup":
        step = copy.deepcopy(result.step)
        step.by = [fix.params["to"] if b == fix.params["col"] else b for b in step.by]
        new = run_step(ws, catalog, step)
        new.notes = [n for n in result.notes if n != "suppressed"] + [f"rollup:{fix.params['col']}>{fix.params['to']}"]
        return new
    if fix.op == "to_share":
        step = copy.deepcopy(result.step)
        step.tool = "share"
        new = run_step(ws, catalog, step)
        new.notes = list(result.notes) + ["to_share"]
        return new
    if fix.op == "suppress":
        return apply_suppression(result)
    if fix.op == "no_numbers":
        out = copy.deepcopy(result)
        out.id = uuid.uuid4().hex[:10]
        if "no_numbers" not in out.notes:
            out.notes.append("no_numbers")
        return out
    raise ValueError(f"알 수 없는 고치기: {fix.op}")
