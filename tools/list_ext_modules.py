"""센터 운영자 허용 등록용: 혼디가 쓰는 파이썬 확장 모듈(.pyd/.dll) 목록을 만든다.

센터 PC 보안정책은 디지털 서명이 없는 확장 모듈 실행을 막지만, 운영자가 허용 등록하면 쓸 수 있다(대회 게시판 답변 2026-11-15).
설치.bat이 설치 직후 이 스크립트로 '확장모듈_목록.txt'를 만든다.

사용: python tools/list_ext_modules.py [.venv 경로]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def report(venv: Path) -> str:
    venv = Path(venv).resolve()
    sp = venv / "Lib" / "site-packages"
    files = sorted(p for p in sp.rglob("*") if p.suffix.lower() in (".pyd", ".dll"))
    by_pkg = {}
    for p in files:
        by_pkg.setdefault(p.relative_to(sp).parts[0], []).append(p)
    lines = [
        "혼디 — 센터 PC 허용 등록이 필요한 파이썬 확장 모듈 목록",
        "",
        "센터 보안정책상 디지털 서명이 없는 확장 모듈(.pyd/.dll)은 실행이 제한될 수 있습니다.",
        "아래 폴더(또는 파일)를 보안 프로그램의 허용 목록에 등록해 주세요.",
        f"  허용 등록 폴더: {sp}",
        f"  파이썬 실행 파일: {venv / 'Scripts' / 'python.exe'} (python.org 공식 배포본에서 만든 가상환경)",
        "",
        f"패키지 {len(by_pkg)}개, 파일 {len(files)}개",
    ]
    for pkg, ps in sorted(by_pkg.items(), key=lambda x: x[0].lower()):
        lines.append(f"[{pkg}] {len(ps)}개")
        lines += [f"  {p}" for p in ps]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    v = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".venv"
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(report(v))
