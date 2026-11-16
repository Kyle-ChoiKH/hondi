import io
import json
from datetime import date

from app import hub
from app.prep import operator_request, order_sheet, recommend


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_uses_url_and_parses_first_list(monkeypatch, tmp_path):
    seen = []

    def fake(req, timeout=0):
        seen.append(req.full_url if hasattr(req, "full_url") else req)
        return FakeResp(json.dumps({"totCnt": 2, "data": [{"baseDate": "20251020", "emd": "한림읍", "visitPop": 5},
                                                         {"baseDate": "20251020", "emd": "애월읍", "visitPop": 7}]}).encode())

    monkeypatch.setattr(hub.urllib.request, "urlopen", fake)
    r = hub.fetch("population", {"startDate": "20251020", "endDate": "20251020"}, "PK", tmp_path)
    assert r.source == "live" and len(r.rows) == 2
    assert seen[0].startswith("https://open.jejudatahub.net/api/proxy/Daaa1t3at3tt8a8DD3t55538t35Dab1t/PK?")
    assert "startDate=20251020" in seen[0]


def test_fetch_uses_cache_when_offline(monkeypatch, tmp_path):
    monkeypatch.setattr(hub.urllib.request, "urlopen",
                        lambda req, timeout=0: FakeResp(b'{"data":[{"baseDate":"20251020","visitPop":1}]}'))
    hub.fetch("population", {"startDate": "20251020", "endDate": "20251020"}, "PK", tmp_path)

    def boom(req, timeout=0):
        raise hub.urllib.error.URLError("x")

    monkeypatch.setattr(hub.urllib.request, "urlopen", boom)
    r = hub.fetch("population", {"startDate": "20251020", "endDate": "20251020"}, "PK", tmp_path)
    assert r.source == "cache" and r.rows[0]["visitPop"] == 1


def test_fetch_falls_back_to_sample_without_key(tmp_path):
    r = hub.fetch("weather", {"searchDate": "20251020"}, None, tmp_path)
    assert r.source == "sample" and r.rows and "예시" in r.note
    p = hub.fetch("population", {"startDate": "20251001", "endDate": "20251007", "emd": "애월읍"}, "", tmp_path)
    assert p.source == "sample" and {x["emd"] for x in p.rows} == {"애월읍"}
    assert {x["baseDate"] for x in p.rows} == {f"202510{d:02d}" for d in range(1, 8)}


def test_recommend_business():
    recs = recommend("사업계획서", "애월읍에 국수집을 내려고 합니다", today=date(2026, 11, 15))
    ids = [r["id"] for r in recs]
    assert ids[:3] == ["1-08", "1-14", "1-12"]
    assert recs[0]["months"][-1] == "2026-09" and len(recs[0]["months"]) == 12
    assert all(r["why"] for r in recs)


def test_recommend_keywords():
    ids = [r["id"] for r in recommend("현황자료", "유동인구와 버스 이용", today=date(2026, 11, 15))]
    assert "4-11" in ids and "3-04" in ids


def test_order_sheet_lists_each_month():
    recs = recommend("사업계획서", "", today=date(2026, 11, 15))[:3]
    html = order_sheet(recs, {"bjd": "애월읍"})
    assert html.count("☐") == 36
    assert "1개월" in html and "36번" in html and "애월읍" in html


def test_operator_request_mentions_folder():
    recs = recommend("사업계획서", "", today=date(2026, 11, 15))[:2]
    text = operator_request(recs, "홍길동", "2026-11-18")
    assert "요청파일" in text and "2026-11-18" in text and "카드 이용 현황(읍면동)_v02" in text


def test_sample_unknown_emd_does_not_crash(tmp_path):
    r = hub.fetch("population", {"startDate": "20251001", "endDate": "20251001", "emd": "애월"}, None, tmp_path)
    assert r.source == "sample" and r.rows and r.rows[0]["emd"] == "애월"
