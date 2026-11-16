import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from app.server import create_app, make_server
from app.session import load_config


@pytest.fixture
def srv(tmp_path):
    cfg = load_config(tmp_path / "none.ini")
    app = create_app(cfg, tmp_path / "work" / "sessions")
    httpd = make_server(app, 0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, app
    httpd.shutdown()


def call(base, path, body=None, raw=None, headers=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            ct = r.headers.get("Content-Type", "")
            payload = r.read()
            return r.status, (json.loads(payload) if "json" in ct else payload)
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except ValueError:
            return e.code, payload


def test_end_to_end_business_scenario(srv):
    base, app = srv
    st, _ = call(base, "/api/purpose", {"purpose": "사업계획서"})
    assert st == 200
    st, d = call(base, "/api/demo", {})
    assert st == 200 and any(x["id"] == "1-08" for x in d["datasets"])
    ds = next(x for x in d["datasets"] if x["id"] == "1-08")
    assert ds["missing"] == ["2025-11"]
    st, cards = call(base, "/api/cards")
    assert any(c["id"] == "biz_trend" and c["enabled"] for c in cards["cards"])
    st, p = call(base, "/api/plan", {"card": "biz_customers"})
    assert st == 200 and p["plan_text"]
    bjd = next(n for n in p["needs"] if n["key"] == "bjd")
    assert "애월읍" in bjd["options"]
    st, r = call(base, "/api/run", {"plan": p["plan"], "values": {"bjd": "애월읍", "biz_nm": "한식 음식점업"}})
    assert st == 200 and len(r["results"]) == 2
    first = r["results"][0]
    st, png = call(base, first["png"])
    assert st == 200 and png[:4] == b"\x89PNG"
    target = next((x for x in r["results"] if x["light"] != "green"), None)
    if target:
        fix = target["fixes"][0]
        st, f = call(base, "/api/fix", {"result_id": target["id"], "fix_id": fix["id"]})
        assert st == 200 and f["results"][0]["id"] != target["id"]
    ids = [x["id"] for x in call(base, "/api/state")[1]["results"]]
    st, rep = call(base, "/api/report", {"result_ids": ids, "title": "애월읍 한식 시장 분석"})
    assert st == 200
    st, html = call(base, rep["html_url"])
    assert st == 200 and "시장 규모와 추이".encode() in html
    st, form = call(base, "/api/export-form", {"result_ids": ids, "note": "창업 사업계획서"})
    assert st == 200 and form["draft"]["description"]
    st, ob = call(base, "/api/outbound")
    assert st == 200 and ob["records"] == []


def test_question_without_ai_uses_card(srv):
    base, app = srv
    call(base, "/api/demo", {})
    st, p = call(base, "/api/plan", {"question": "손님은 언제 오나요?"})
    assert st == 200 and p["plan"]["source"] == "card"
    assert any("AI 없이" in n for n in p["notes"])


def test_upload_and_unknown_file(srv):
    base, app = srv
    name = urllib.parse.quote("알수없음.csv")
    st, d = call(base, "/api/files/upload", raw=b'"a","b"\n"1","2"\n', headers={"X-Filename": name})
    assert st == 200 and d["files"][0]["status"] == "unknown"


def test_run_rejects_bad_plan(srv):
    base, app = srv
    call(base, "/api/demo", {})
    bad = {"purpose": "자유", "steps": [{"tool": "trend", "dataset": "1-08", "metric": "use_amt", "by": ["nope"],
                                        "filters": {}, "options": {}}]}
    st, d = call(base, "/api/run", {"plan": bad, "values": {}})
    assert st == 400 and "nope" in d["error"]


def test_path_traversal_blocked(srv):
    base, app = srv
    st, _ = call(base, "/out/..%2F..%2Fconfig.ini")
    assert st == 404
    st, _ = call(base, "/web/../app/server.py")
    assert st == 404


def test_bundled_web_font_is_served_as_font(srv):
    # 센터 PC는 인터넷이 막혀 있을 수 있어 글꼴을 함께 넣는다 — 글꼴 형식으로 내려가야 브라우저가 쓴다
    base, app = srv
    req = urllib.request.Request(base + "/web/fonts/Pretendard-Regular.subset.woff2")
    with urllib.request.urlopen(req, timeout=30) as r:
        assert r.status == 200 and r.headers["Content-Type"] == "font/woff2" and len(r.read()) > 100_000
    st, css = call(base, "/web/style.css")
    assert st == 200 and b"Pretendard" in css and b"fonts.googleapis" not in css and b"cdn." not in css


def test_prep_and_hub(srv):
    base, app = srv
    st, d = call(base, "/api/prep", {"purpose": "사업계획서", "question": "애월 국수집", "conditions": {"bjd": "애월읍"},
                                     "name": "홍길동", "visit_date": "2026-11-18"})
    assert st == 200 and d["recs"] and "요청파일" in d["request_text"]
    st, h = call(base, "/api/hub?kind=population&startDate=20251001&endDate=20251003&emd=애월읍".replace("애월읍", urllib.parse.quote("애월읍")))
    assert st == 200 and h["source"] == "sample" and len(h["series"]) == 3


def test_session_end_deletes(srv):
    base, app = srv
    call(base, "/api/demo", {})
    old = app.session.dir
    st, d = call(base, "/api/session/end", {})
    assert st == 200 and not old.exists()
    st, s = call(base, "/api/state")
    assert s["datasets"] == []


def test_selfcheck_and_index(srv):
    base, app = srv
    st, d = call(base, "/api/selfcheck")
    assert st == 200 and d["checks"]
    st, html = call(base, "/")
    assert st == 200 and "혼디".encode() in html


def test_plan_trace_shows_masked_question(srv, monkeypatch):
    base, app = srv
    call(base, "/api/demo", {})

    class P:
        model = "fake"
        effort = "low"

        def complete(self, system, user, max_tokens=800):
            from app.llm import Reply
            return Reply('{"purpose":"사업계획서","steps":[{"tool":"trend","dataset":"1-08","metric":"use_amt",'
                         '"by":["base_year_month"],"filters":{"bjd":"〔bjd#1〕"},"options":{}}]}', 900, 80)

    app.outbound.provider = P()
    st, p = call(base, "/api/plan", {"question": "애월읍 매출 흐름"})
    assert st == 200 and p["plan"]["source"] == "ai"
    assert p["trace"][0]["sent"].startswith("질문: 〔bjd#1〕")
    assert "애월읍" not in p["trace"][0]["sent"]
    assert p["trace"][0]["input_tokens"] == 900


def test_second_server_cannot_share_port(srv):
    base, app = srv
    port = int(base.rsplit(":", 1)[1])
    with pytest.raises(OSError):
        make_server(app, port)


def test_rejects_foreign_host_origin_and_non_json(srv):
    base, app = srv
    st, _ = call(base, "/api/state", headers={"Host": "evil.example"})
    assert st == 403  # DNS 재바인딩
    st, _ = call(base, "/api/settings", {"send_aggregates": True}, headers={"Origin": "https://evil.example"})
    assert st == 403 and app.cfg.send_aggregates is False
    st, _ = call(base, "/api/settings", raw=b'{"send_aggregates":true}', headers={"Content-Type": "text/plain"})
    assert st == 415 and app.cfg.send_aggregates is False
    st, _ = call(base, "/api/settings", {"keep_results": True}, headers={"Origin": base})
    assert st == 200 and app.cfg.keep_results is True


def test_assign_ambiguous_files(srv, cat=None):
    base, app = srv
    h = [c["name"] for c in app.cat.columns("1-02")]
    body = (",".join(f'"{x}"' for x in h) + "\n" + '"202501","제주","면세점","개인","1000","500"\n').encode()
    st, d = call(base, "/api/files/upload", raw=body, headers={"X-Filename": "Results_20261109_000011.csv"})
    f = d["files"][0]
    assert f["status"] == "ambiguous" and {c["id"] for c in f["candidates"]} == {"1-02", "1-05"}
    st, d = call(base, "/api/files/assign", {"dataset": "1-05"})
    assert st == 200 and d["files"][0]["status"] == "ok" and [x["id"] for x in d["datasets"]] == ["1-05"]


def test_state_lists_external_folders_left_after_end(srv, tmp_path):
    base, app = srv
    import sys
    sys.path.insert(0, "tests")
    from conftest import H108, small_rows, write_csv
    dl = tmp_path / "Downloads"
    dl.mkdir()
    p = write_csv(dl / "Results_20261109_000001.csv", H108, [r for r in small_rows() if r[0] == "202407"])
    call(base, "/api/files/load", {"paths": [str(p)]})
    st, s = call(base, "/api/state")
    assert s["external_files"] == [{"folder": str(dl), "count": 1}]
    st, d = call(base, "/api/session/end", {})
    assert p.exists() and d["ended"]["left_outside"] == [{"folder": str(dl), "count": 1}]


def test_demo_files_are_not_reported_as_left_outside(srv):
    base, app = srv
    call(base, "/api/demo", {})
    st, s = call(base, "/api/state")
    assert s["external_files"] == []


# ---- 운영형 기능: 조건 바꿔 다시 실행 · 반출 신청 묶음 · 데이터 상세 · 세션 기록 ----
def _first_result(base):
    call(base, "/api/demo", {})
    p = call(base, "/api/plan", {"card": "biz_trend"})[1]
    return call(base, "/api/run", {"plan": p["plan"], "values": {"bjd": "애월읍", "biz_nm": "한식 음식점업"}})[1]["results"][0]


def test_result_has_edit_options(srv):
    base, app = srv
    r = _first_result(base)
    e = r["edit"]
    assert {f["key"] for f in e["filters"]} == {"bjd", "biz_nm"} and "노형동" in e["filters"][0]["options"] + e["filters"][1]["options"]
    assert e["metric"] == "use_amt" and any(m["key"] == "use_cnt" for m in e["metrics"])
    assert e["months"][0] <= e["period"][0] <= e["period"][1] <= e["months"][-1]


def test_rerun_with_changed_area_period_metric(srv):
    base, app = srv
    r = _first_result(base)
    st, d = call(base, "/api/rerun", {"result_id": r["id"], "filters": {"bjd": "노형동"},
                                      "period": ["2025-07", "2025-12"], "metric": "use_cnt"})
    assert st == 200
    n = d["results"][0]
    assert n["id"] != r["id"] and n["step"]["filters"]["bjd"] == "노형동" and n["step"]["metric"] == "use_cnt"
    assert "2025-07~2025-12" in n["source"]
    st, d = call(base, "/api/rerun", {"result_id": r["id"], "filters": {"bjd": "없는동"}})
    assert st == 400 and "없는" in d["error"]


def test_bundle_zip_has_everything_for_export_application(srv):
    import io
    import zipfile
    base, app = srv
    r = _first_result(base)
    st, d = call(base, "/api/bundle", {"result_ids": [r["id"]], "title": "애월 한식", "note": "창업 사업계획서"})
    assert st == 200 and d["zip_url"].startswith("/out/")
    st, raw = call(base, d["zip_url"])
    names = zipfile.ZipFile(io.BytesIO(raw)).namelist()
    assert any(n.endswith(".png") for n in names) and "반출점검메모.html" in names and "반출신청서_초안.txt" in names
    assert any(n.startswith("보고서") for n in names)
    txt = zipfile.ZipFile(io.BytesIO(raw)).read("반출신청서_초안.txt").decode("utf-8")
    assert "제목" in txt and "설명" in txt and "창업 사업계획서" in txt


def test_dataset_detail(srv):
    base, app = srv
    call(base, "/api/demo", {})
    st, d = call(base, "/api/dataset?id=1-08")
    assert st == 200 and d["name"].startswith("카드 이용 현황(읍면동)")
    cols = {c["key"]: c for c in d["columns"]}
    assert cols["bjd"]["label"] == "법정동" and cols["use_amt"]["role"] == "amount"
    assert cols["bjd"]["top"] and cols["bjd"]["distinct"] > 10
    assert d["months"][0]["rows"] > 0 and any(m["missing"] for m in d["months"])
    assert any("biz_" in c["id"] for c in d["cards"])


def test_activity_timeline_has_no_values(srv):
    base, app = srv
    _first_result(base)
    st, d = call(base, "/api/activity")
    ev = [e["event"] for e in d["events"]]
    assert "load" in ev and "result" in ev
    assert "애월읍" not in json.dumps(d, ensure_ascii=False)


def test_results_carry_friendly_headline_and_how_to_read(srv):
    base, app = srv
    call(base, "/api/demo", {})
    st, p = call(base, "/api/plan", {"card": "biz_customers"})
    st, r = call(base, "/api/run", {"plan": p["plan"], "values": {"bjd": "애월읍", "biz_nm": "한식 음식점업"}})
    first = r["results"][0]
    assert first["headline"].endswith(".") and ("요" in first["headline"])
    assert "100%" in first["howto"]


def test_explore_info_for_non_experts(srv):
    # 파일을 넣으면 데이터마다 '무엇을 알 수 있는지'를 쉬운 말로, 바로 누를 질문 카드와 함께 보여 준다
    base, app = srv
    st, d = call(base, "/api/demo", {})
    ds = next(x for x in d["datasets"] if x["id"] == "1-08")
    assert "이용금액" in ds["about"] and "제공합니다" not in ds["about"]
    assert "이용금액" in ds["measures"] and "법정동" in ds["by"]
    assert "biz_trend" in ds["cards"]


def test_focus_options_list_areas_and_businesses(srv):
    # '관심 조건'(지역·업종)을 한 번 고르면 이후 질문에 자동으로 쓰기 위한 목록 — 불러온 데이터에 있는 값만
    base, app = srv
    st, f = call(base, "/api/focus-options")
    assert st == 200 and f["areas"] == [] and f["businesses"] == []
    call(base, "/api/demo", {})
    st, f = call(base, "/api/focus-options")
    assert "애월읍" in f["areas"] and "한식 음식점업" in f["businesses"]
    assert len(f["areas"]) == len(set(f["areas"]))
