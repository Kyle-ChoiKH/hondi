"""AI 제공자 어댑터(OpenAI). 표준 라이브러리 urllib만 쓴다.

이 모듈을 직접 부르지 말고 firewall.Outbound.send()를 거쳐야 한다(값 가림·기록·한도).
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
TIMEOUT = 30


class ProviderUnavailable(Exception):
    """AI를 쓸 수 없음(키 없음, 네트워크·보안 차단, 오류, 한도). 호출 측은 질문 카드로 대체한다."""


@dataclass
class Reply:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class NoProvider:
    def __init__(self, reason: str = "AI가 설정되지 않았습니다"):
        self.reason = reason
        self.model = ""

    def complete(self, system: str, user: str, max_tokens: int = 800) -> Reply:
        raise ProviderUnavailable(self.reason)


class OpenAIProvider:
    def __init__(self, key: str, model: str, effort: str = "low"):
        self.key, self.model, self.effort = key, model, effort

    def __repr__(self):
        return f"OpenAIProvider(model={self.model!r}, key=***)"

    def complete(self, system: str, user: str, max_tokens: int = 800) -> Reply:
        body = {"model": self.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_object"}}
        if self.model.startswith("gpt-5"):
            body["max_completion_tokens"] = max_tokens
            body["reasoning_effort"] = self.effort
        else:
            body["max_tokens"] = max_tokens
            body["temperature"] = 0
        req = urllib.request.Request(OPENAI_URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Authorization": f"Bearer {self.key}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ProviderUnavailable("AI 키가 올바르지 않습니다(401). config.ini의 [ai] key를 확인해 주세요.") from None
            detail = ""
            try:
                detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")[:120]
            except Exception:  # noqa: BLE001
                pass
            detail = re.sub(r"sk-[A-Za-z0-9_*\-]+", "sk-…", detail)  # 오류 문구에 키 일부가 섞여 오면 지움
            raise ProviderUnavailable(f"AI 응답 오류 {e.code} {detail}".strip()) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ProviderUnavailable(f"인터넷 연결 또는 보안 정책으로 AI에 접속하지 못했습니다 ({e})") from None
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderUnavailable("AI 응답 형식을 읽지 못했습니다") from None
        u = data.get("usage") or {}
        return Reply(text, int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0))


def make_provider(provider: str, model: str, key: str):
    if (provider or "").lower() != "openai":
        return NoProvider("AI 사용 안 함으로 설정되어 있습니다")
    if not key:
        return NoProvider("config.ini에 AI 키가 없습니다")
    return OpenAIProvider(key, model or "gpt-5-nano")
