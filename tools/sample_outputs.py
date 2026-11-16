"""결과 예시 만들기(재현용): 예시(가상) 데이터로 사업계획서 시나리오를 처음부터 끝까지 돌려 docs/결과예시/에 저장한다.

사용: python tools/sample_outputs.py
AI를 쓰지 않는다(질문 카드). 같은 시드로 언제나 같은 결과가 나온다.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.catalog import Catalog  # noqa: E402
from app.export_form import check_memo, draft  # noqa: E402
from app.guard import apply_fix, assess  # noqa: E402
from app.ingest import Workspace  # noqa: E402
from app.model import Step  # noqa: E402
from app.planner import card_plan, fill  # noqa: E402
from app.report import build_report  # noqa: E402
from app.synth import build_demo  # noqa: E402
from app.tools import run_step  # noqa: E402

OUT = ROOT / "docs" / "결과예시"


def main():
    cat = Catalog.load()
    ws = Workspace(cat)
    with tempfile.TemporaryDirectory() as d:
        ws.add_files(build_demo(Path(d)))
    values = {"bjd": "애월읍", "biz_nm": "한식 음식점업"}
    results, log = [], []
    for card in ("biz_trend", "biz_customers", "biz_time", "biz_week", "biz_compare_areas"):
        for s in fill(card_plan(card, ws, cat), values).steps:
            results.append(run_step(ws, cat, s))
    # 일부러 노랑이 나오는 좁은 조건 → 범주처리로 고치기
    narrow = run_step(ws, cat, Step("rank", "1-08", "use_amt", ["user_type"], {"bjd": "우도면", "biz_nm": "한식 음식점업"},
                                    {"period": ["2026-06", "2026-06"], "top": 10}))
    a = assess(narrow, cat)
    log.append({"결과": narrow.title, "처음 신호등": a.light, "이유": a.reasons, "고치기": [f.label for f in a.fixes]})
    fixed = apply_fix(ws, cat, narrow, next(f for f in a.fixes if f.op == "rollup"))
    log.append({"결과": fixed.title, "고친 뒤 신호등": assess(fixed, cat).light, "처리": fixed.notes})
    results.append(fixed)
    ass = [assess(r, cat) for r in results]
    if OUT.exists():
        shutil.rmtree(OUT)
    rep = build_report("사업계획서", results, ass, cat, OUT, {"title": "애월읍 한식 음식점 시장 분석(예시)"}, demo=True)
    d = draft(results, ass, cat, "사업계획서", "애월읍 국수집 창업 사업계획서")
    (OUT / "반출신청서_초안.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "반출점검메모.html").write_text(check_memo(results, ass, cat, "사업계획서", "애월읍 국수집 창업 사업계획서"), encoding="utf-8")
    (OUT / "반출지킴이_고치기_기록.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, png in enumerate(rep["pngs"], 1):  # 기획서·문서가 참조하는 고정 이름 사본
        shutil.copyfile(png, ROOT / "docs" / "img" / f"예시_그림{k:02d}.png")
    print("보고서:", rep["html"].name, rep["pdf"] and rep["pdf"].name, "그림", len(rep["pngs"]))
    print("신호등:", [x.light for x in ass])
    print(json.dumps(log, ensure_ascii=False))


if __name__ == "__main__":
    main()
