"""값 방화벽: 외부 AI로 나가는 모든 글에서 불러온 데이터의 값을 가리고, 보낸 내용을 전부 기록한다.

- 문자열 값(지역명·업종명 등)은 〔컬럼#번호〕 자리표시자로 바꾸고, 응답은 PC 안에서 원래 값으로 되돌린다.
- 3자리 이상 수치는 연도·연월·날짜가 아니면 〔수치#번호〕로 가린다.
- 월 사용 한도를 넘으면 호출하지 않는다.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from .llm import ProviderUnavailable, Reply

NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def _is_date_like(digits: str) -> bool:
    if not digits.isdigit():
        return False
    if len(digits) == 4 and digits[:2] in ("19", "20"):
        return True
    if len(digits) == 6 and digits[:2] == "20" and 1 <= int(digits[4:6]) <= 12:
        return True
    if len(digits) == 8 and digits[:2] == "20" and 1 <= int(digits[4:6]) <= 12 and 1 <= int(digits[6:8]) <= 31:
        return True
    return False


class Masker:
    def __init__(self, dim_values: dict, protected: set = frozenset()):
        pairs = []
        for col, vals in (dim_values or {}).items():
            for v in vals:
                v = str(v).strip()
                if len(v) < 2 or re.fullmatch(r"[\d.,]+", v) or v in protected or v.upper() == "NA":
                    continue
                pairs.append((v, col))
        pairs.sort(key=lambda x: -len(x[0]))
        self._pairs = pairs
        self._protected = sorted({p for p in protected if len(p) >= 2}, key=len, reverse=True)

    def mask(self, text: str, allow_numbers=frozenset()):
        keep = []
        for w in self._protected:
            start = 0
            while (i := text.find(w, start)) >= 0:
                keep.append((i, i + len(w)))
                start = i + len(w)
        spans = []
        for v, col in self._pairs:
            start = 0
            while True:
                i = text.find(v, start)
                if i < 0:
                    break
                j = i + len(v)
                inside_keep = any(a <= i and j <= b and (b - a) > (j - i) for a, b in keep)
                if not inside_keep and not any(a < j and i < b for a, b, _, _ in spans):
                    spans.append((i, j, v, col))
                start = j
        spans.sort()
        mapping, back, n, parts, pos = {}, {}, 0, [], 0
        for i, j, v, col in spans:
            if v not in back:
                n += 1
                back[v] = f"〔{col}#{n}〕"
                mapping[back[v]] = (col, v)
            parts.append(text[pos:i])
            parts.append(back[v])
            pos = j
        parts.append(text[pos:])
        text = "".join(parts)
        allow = {str(a).replace(",", "") for a in allow_numbers}

        def num(m):
            nonlocal n
            tok = m.group(0)
            digits = tok.replace(",", "").split(".")[0]
            if len(digits) < 3 or _is_date_like(tok) or tok.replace(",", "") in allow:
                return tok
            if m.start() > 0 and text[m.start() - 1] == "#":
                return tok
            n += 1
            ph = f"〔수치#{n}〕"
            mapping[ph] = ("수치", tok)
            return ph

        text = NUM.sub(num, text)
        return text, mapping


def unmask(obj, mapping: dict):
    if isinstance(obj, str):
        if obj in mapping:
            return mapping[obj][1]
        for ph, (_, v) in mapping.items():
            obj = obj.replace(ph, v)
        return obj
    if isinstance(obj, list):
        return [unmask(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {k: unmask(v, mapping) for k, v in obj.items()}
    return obj


class Usage:
    """월별 사용량(토큰·추정 비용). 세션을 지워도 남는 운영용 기록이며 데이터 값은 담지 않는다."""

    def __init__(self, path: Path, price_in: float, price_out: float, usd_krw: float, limit_krw: float):
        self.path = Path(path)
        self.price_in, self.price_out = float(price_in or 0), float(price_out or 0)
        self.usd_krw, self.limit = float(usd_krw or 1400), float(limit_krw or 0)
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def add(self, input_tokens: int, output_tokens: int) -> float:
        krw = (input_tokens * self.price_in + output_tokens * self.price_out) / 1_000_000 * self.usd_krw
        with self._lock:
            d = self._load()
            key = datetime.now().strftime("%Y-%m")
            m = d.setdefault(key, {"input_tokens": 0, "output_tokens": 0, "krw": 0.0, "calls": 0})
            m["input_tokens"] += input_tokens
            m["output_tokens"] += output_tokens
            m["krw"] += krw
            m["calls"] += 1
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return krw

    def month(self) -> dict:
        return self._load().get(datetime.now().strftime("%Y-%m"),
                                {"input_tokens": 0, "output_tokens": 0, "krw": 0.0, "calls": 0})

    def month_krw(self) -> float:
        return float(self.month()["krw"])

    def blocked(self) -> bool:
        return bool(self.limit) and self.month_krw() >= self.limit


class Outbound:
    def __init__(self, log_path: Path, provider, usage: Usage | None = None):
        self.log_path = Path(log_path)
        self.provider = provider
        self.usage = usage
        self._lock = threading.Lock()

    def send(self, system: str, user: str, masker: Masker, allow_numbers=frozenset(), max_tokens: int = 800):
        if self.usage and self.usage.blocked():
            raise ProviderUnavailable("이번 달 AI 사용 한도에 도달해 AI 없이 진행합니다")
        # 시스템 글은 코드가 공개 명세서로만 만든 것(값 없음)이고, 이용자 글은 반드시 가린다.
        msys = system
        muser, mapping = masker.mask(user, allow_numbers)
        rec = {"time": datetime.now().isoformat(timespec="seconds"), "model": getattr(self.provider, "model", ""),
               "system": msys, "user": muser, "masked": len(mapping)}
        t0 = time.time()
        try:
            reply = self.provider.complete(msys, muser, max_tokens=max_tokens)
        except ProviderUnavailable as e:
            rec.update(error=str(e))
            self._log(rec)
            raise
        cost = self.usage.add(reply.input_tokens, reply.output_tokens) if self.usage else 0.0
        rec.update(reply=reply.text, input_tokens=reply.input_tokens, output_tokens=reply.output_tokens,
                   krw=round(cost, 3), seconds=round(time.time() - t0, 2))
        self._log(rec)
        return reply, mapping

    def _log(self, rec: dict):
        with self._lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def records(self) -> list:
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for ln in lines:
            try:
                rec = json.loads(ln)
            except ValueError:
                continue
            if "error" not in rec:
                out.append(rec)
        return out

    def all_records(self) -> list:
        try:
            return [json.loads(x) for x in self.log_path.read_text(encoding="utf-8").splitlines() if x.strip()]
        except (OSError, ValueError):
            return []
