import io
import json
import urllib.error

import pytest

from app import llm
from app.llm import OpenAIProvider, ProviderUnavailable, make_provider


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_openai_request_shape(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        seen["body"] = json.loads(req.data)
        return FakeResp(json.dumps({"choices": [{"message": {"content": "{\"ok\":1}"}}],
                                    "usage": {"prompt_tokens": 12, "completion_tokens": 3}}).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    r = OpenAIProvider("sk-test", "gpt-5-nano").complete("SYS", "USER", max_tokens=500)
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    b = seen["body"]
    assert b["model"] == "gpt-5-nano"
    assert b["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
    assert b["response_format"] == {"type": "json_object"}
    assert b["max_completion_tokens"] == 500 and b["reasoning_effort"] == "low"
    assert "max_tokens" not in b
    assert (r.text, r.input_tokens, r.output_tokens) == ('{"ok":1}', 12, 3)


def test_non_gpt5_uses_max_tokens(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["body"] = json.loads(req.data)
        return FakeResp(b'{"choices":[{"message":{"content":"{}"}}],"usage":{}}')

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    OpenAIProvider("k", "gpt-4o-mini").complete("s", "u", max_tokens=300)
    assert seen["body"]["max_tokens"] == 300 and seen["body"]["temperature"] == 0


def test_http_error_raises(monkeypatch):
    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b"bad key"))

    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    with pytest.raises(ProviderUnavailable) as e:
        OpenAIProvider("k", "gpt-5-nano").complete("s", "u")
    assert "401" in str(e.value)


def test_network_error_raises(monkeypatch):
    def boom(req, timeout=0):
        raise urllib.error.URLError("blocked")

    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    with pytest.raises(ProviderUnavailable):
        OpenAIProvider("k", "gpt-5-nano").complete("s", "u")


def test_make_provider():
    assert isinstance(make_provider("openai", "gpt-5-nano", "k"), OpenAIProvider)
    with pytest.raises(ProviderUnavailable):
        make_provider("openai", "gpt-5-nano", "").complete("s", "u")
    with pytest.raises(ProviderUnavailable):
        make_provider("none", "", "").complete("s", "u")


def test_effort_configurable(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["body"] = json.loads(req.data)
        return FakeResp(b'{"choices":[{"message":{"content":"{}"}}],"usage":{}}')

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    OpenAIProvider("k", "gpt-5-nano", effort="minimal").complete("s", "u")
    assert seen["body"]["reasoning_effort"] == "minimal"


def test_401_message_hides_key_echo(monkeypatch):
    import io, json, urllib.error
    body = json.dumps({"error": {"message": "Incorrect API key provided: sk-proj-****abcd."}}).encode()

    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(body))
    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    with pytest.raises(llm.ProviderUnavailable) as e:
        llm.OpenAIProvider("k", "gpt-5-nano").complete("s", "u")
    assert "sk-" not in str(e.value) and "키" in str(e.value)  # (M7)
