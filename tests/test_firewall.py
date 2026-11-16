import json

import pytest

from app.firewall import Masker, Outbound, Usage, unmask
from app.llm import NoProvider, ProviderUnavailable, Reply

DIMS = {"bjd": {"애월읍", "노형동"}, "biz_nm": {"한식 음식점업"}, "sex": {"남"}, "age": {"10", "20"}}


class FakeProvider:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, user, max_tokens=800):
        self.calls.append((system, user))
        return Reply(self.replies.pop(0), 100, 50)


def test_question_values_masked_and_restored():
    mk = Masker(DIMS)
    text, mapping = mk.mask("애월읍 한식 음식점업 매출 3,250,000원 넘는 달")
    assert "애월읍" not in text and "한식 음식점업" not in text and "3,250,000" not in text
    assert "〔bjd#1〕" in text
    out = unmask(json.loads('{"filters":{"bjd":"〔bjd#1〕","biz_nm":"〔biz_nm#2〕"}}'), mapping)
    assert out == {"filters": {"bjd": "애월읍", "biz_nm": "한식 음식점업"}}


def test_years_and_months_not_masked():
    text, _ = Masker(DIMS).mask("2025년 7월부터 202606까지, 20250701 기준")
    assert text == "2025년 7월부터 202606까지, 20250701 기준"


def test_short_and_numeric_dim_values_ignored():
    text, _ = Masker(DIMS).mask("남녀 10대 비교")
    assert text == "남녀 10대 비교"


def test_allow_numbers():
    text, _ = Masker(DIMS).mask("합계 12,345 와 678", allow_numbers={"12345"})
    assert "12,345" in text and "678" not in text


def test_outbound_logs_every_request(tmp_path):
    p = FakeProvider(['{"a":1}', '{"b":2}'])
    ob = Outbound(tmp_path / "out.jsonl", p)
    ob.send("sys", "애월읍 질문", Masker(DIMS))
    ob.send("sys", "두 번째", Masker(DIMS))
    recs = ob.records()
    assert len(recs) == 2
    assert "애월읍" not in recs[0]["user"] and "〔bjd#1〕" in recs[0]["user"]
    assert all("애월읍" not in c[1] for c in p.calls)
    assert recs[0]["input_tokens"] == 100


def test_reply_is_unmasked(tmp_path):
    ob = Outbound(tmp_path / "out.jsonl", FakeProvider(['{"bjd":"〔bjd#1〕"}']))
    reply, mapping = ob.send("sys", "애월읍", Masker(DIMS))
    assert unmask(json.loads(reply.text), mapping) == {"bjd": "애월읍"}


def test_unavailable_provider(tmp_path):
    ob = Outbound(tmp_path / "out.jsonl", NoProvider("키 없음"))
    with pytest.raises(ProviderUnavailable):
        ob.send("s", "u", Masker({}))


def test_monthly_limit_blocks(tmp_path):
    usage = Usage(tmp_path / "usage.json", price_in=0.05, price_out=0.4, usd_krw=1400, limit_krw=1)
    usage.add(10_000_000, 0)  # 0.5 USD = 700원 > 1원
    p = FakeProvider(['{}'])
    ob = Outbound(tmp_path / "out.jsonl", p, usage=usage)
    with pytest.raises(ProviderUnavailable) as e:
        ob.send("s", "u", Masker({}))
    assert "한도" in str(e.value)
    assert p.calls == []


def test_usage_accumulates(tmp_path):
    u = Usage(tmp_path / "usage.json", price_in=0.05, price_out=0.4, usd_krw=1400, limit_krw=20000)
    u.add(1_000_000, 1_000_000)
    assert u.month_krw() == pytest.approx((0.05 + 0.4) * 1400)
    assert Usage(tmp_path / "usage.json", 0.05, 0.4, 1400, 20000).month_krw() == pytest.approx(630)


def test_protected_words_not_split():
    mk = Masker({"area_type": {"도심", "읍면"}, "bjd": {"애월읍"}}, protected={"도심구분"})
    text, mapping = mk.mask("도심구분 컬럼, 애월읍은 읍면, 도심")
    assert text.startswith("도심구분 컬럼, 〔bjd#1〕")
    assert "도심구분" in text and text.endswith("〔area_type#3〕")
