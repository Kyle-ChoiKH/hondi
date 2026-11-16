"""받침에 맞는 조사 붙이기: j("추이", "을") → "추이를". 한글이 아니면 "을(를)"처럼 둘 다 적는다."""
from __future__ import annotations

PAIRS = {"을": ("을", "를"), "를": ("을", "를"), "이": ("이", "가"), "가": ("이", "가"),
         "은": ("은", "는"), "는": ("은", "는"), "와": ("과", "와"), "과": ("과", "와"),
         "로": ("으로", "로"), "으로": ("으로", "로"), "예요": ("이에요", "예요"), "이에요": ("이에요", "예요")}
DIGIT_JONG = {"0": 21, "1": 8, "2": 0, "3": 16, "4": 0, "5": 0, "6": 1, "7": 8, "8": 8, "9": 0}  # 영·일·이·삼… 받침


def j(word: str, particle: str) -> str:
    w = str(word)
    with_b, without_b = PAIRS[particle]
    last = w.rstrip().rstrip("'\"’”)」』")[-1:] if w.strip() else ""
    if last in DIGIT_JONG:
        jong = DIGIT_JONG[last]
        if particle in ("로", "으로"):
            return w + ("로" if jong in (0, 8) else "으로")
        return w + (with_b if jong else without_b)
    if not last or not ("가" <= last <= "힣"):
        both = f"{with_b}({without_b})" if particle not in ("로", "으로") else "(으)로"
        return w + both
    jong = (ord(last) - 0xAC00) % 28
    if particle in ("로", "으로"):
        return w + ("로" if jong in (0, 8) else "으로")  # 받침 없음·ㄹ받침 → 로
    return w + (with_b if jong else without_b)
