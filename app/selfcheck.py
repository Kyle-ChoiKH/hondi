"""설치 자가 진단: 센터 담당자(비개발자)가 설치 직후 문제를 스스로 확인하도록 쉬운 말로 보여 준다."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .session import Config

DATA = Path(__file__).parent / "data"
EXTERNAL_URLS = ["https://api.openai.com/v1/chat/completions", "https://open.jejudatahub.net/api/proxy",
                 "https://www.jejudatahub.net/data/view/data"]  # 마지막은 미리보기의 원문 링크


@dataclass
class Check:
    name: str
    level: str  # ok | warn | fail
    detail: str
    fix: str = ""

    def to_dict(self):
        return {"name": self.name, "level": self.level, "detail": self.detail, "fix": self.fix}


def blocked_hits(urls: list) -> list:
    kws = json.loads((DATA / "blocked_keywords.json").read_text(encoding="utf-8"))["keywords"]
    out = []
    for u in urls:
        low = u.lower()
        for k in kws:
            if k["use_yn"] == "Y" and k["keyword"].lower() in low:
                out.append((u, k["keyword"]))
    return out


def run(cfg: Config, base: Path) -> list:
    out = []
    v = sys.version_info
    ok = (3, 11) <= (v.major, v.minor) <= (3, 13)
    out.append(Check("파이썬 버전", "ok" if ok else "warn", f"{v.major}.{v.minor}.{v.micro}",
                     "" if ok else "파이썬 3.12 설치를 권장합니다(설치.bat이 자동으로 찾습니다)."))
    try:
        import duckdb
        out.append(Check("분석 엔진(duckdb)", "ok", duckdb.__version__))
    except Exception as e:  # noqa: BLE001
        out.append(Check("분석 엔진(duckdb)", "fail", f"불러오기 실패: {e}",
                         "보안 프로그램이 확장 모듈(.pyd)을 막았을 수 있습니다. 설치 폴더를 허용 목록에 등록해 주세요."))
    try:
        import matplotlib
        out.append(Check("그림(matplotlib)", "ok", matplotlib.__version__))
    except Exception as e:  # noqa: BLE001
        out.append(Check("그림(matplotlib)", "fail", f"불러오기 실패: {e}", "설치.bat을 다시 실행하거나 허용 목록 등록이 필요합니다."))
    try:
        from .catalog import Catalog
        n = len(Catalog.load().ids())
        out.append(Check("데이터 카탈로그", "ok", f"센터 데이터 {n}종 명세 로드"))
    except Exception as e:  # noqa: BLE001
        out.append(Check("데이터 카탈로그", "fail", str(e), "app/data/catalog.json 파일이 있는지 확인해 주세요."))
    try:
        Path(base).mkdir(parents=True, exist_ok=True)
        t = Path(base) / ".write_test"
        t.write_text("ok", encoding="utf-8")
        t.unlink()
        out.append(Check("작업 폴더 쓰기", "ok", str(base)))
    except OSError as e:
        out.append(Check("작업 폴더 쓰기", "fail", str(e), "사용자 폴더 쓰기 권한을 확인해 주세요."))
    from .report import find_browser
    b = find_browser()
    out.append(Check("PDF 변환(Edge)", "ok" if b else "warn", b or "Edge/Chrome을 찾지 못함",
                     "" if b else "보고서는 HTML로 저장됩니다. 브라우저에서 인쇄 → PDF로 저장하세요."))
    from .charts import _FONT  # 동봉한 Pretendard를 먼저 쓰고, 없으면 맑은 고딕
    has = bool(_FONT)
    out.append(Check("한글 글꼴", "ok" if has else "warn", f"{_FONT}(그림용)" if has else "한글 글꼴 없음",
                     "" if has else "app/data/fonts 폴더가 빠졌는지 확인하세요. 그림의 한글이 깨질 수 있습니다."))
    if cfg.ai_provider == "openai" and cfg.ai_key:
        out.append(Check("AI 설정", "ok", f"OpenAI {cfg.ai_model}, 월 한도 {cfg.monthly_limit_krw:,.0f}원"))
    else:
        out.append(Check("AI 설정", "warn", "AI 키 없음 — 질문 카드로 모든 기능을 쓸 수 있습니다",
                         "config.ini의 [ai] key에 OpenAI 키를 넣으면 말로 묻기를 쓸 수 있습니다."))
    out.append(Check("허브 키", "ok" if cfg.hub_project_key else "warn",
                     "설정됨" if cfg.hub_project_key else "없음 — 방문 전 미리보기는 예시 데이터로 표시",
                     "" if cfg.hub_project_key else "제주데이터허브에서 프로젝트 키를 발급해 config.ini [hub]에 넣으세요."))
    hits = blocked_hits(EXTERNAL_URLS)
    out.append(Check("외부 주소 차단 점검", "fail" if hits else "ok",
                     ", ".join(f"{u} ← '{k}'" for u, k in hits) if hits else
                     "사용하는 외부 주소에 행안부 차단 키워드 없음: " + ", ".join(EXTERNAL_URLS)))
    return out
