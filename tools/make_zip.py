"""제출용 ZIP 만들기.

사용: python tools/docs_pdf.py  →  python tools/make_zip.py [출력.zip] [--with-key]
  기본 출력: dist/혼디_최종결과물_Kwang.zip (+ dist/혼디_기획서_Kwang.pdf)
  --with-key : 로컬 config.ini의 OpenAI 키를 ZIP 안 config.ini에 넣는다(대회 규정: 평가용 외부 AI 키 포함).
               데이터 API 키(허브 프로젝트 키)는 넣지 않는다.
금지: 이름에 '데이터목록'이 들어간 파일(제주데이터허브 데이터목록, 배포 금지)이 하나라도 있으면 실패한다.
"""
from __future__ import annotations

import configparser
import io
import sys
import tempfile
import zipfile
from pathlib import Path

EXCLUDE_DIRS = {".venv", ".git", "work", "out", "dist", "자료", "__pycache__", ".pytest_cache", ".superpowers", "demo",
                "wheels_tmp", "superpowers", "제출용", "기획서"}  # 기획서는 01_기획서에만
PROG = "05_실행_소스코드/hondi/"  # 실행 프로그램(설치.bat·실행.bat이 있는 폴더)
# 심사위원이 항목별로 바로 찾도록 ZIP 맨 위에 번호 폴더로 두는 문서(대회 안내의 최종 결과물 구분 순서)
SUBMISSION = [
    ("docs/제출용/00_제출물_안내.html", "00_제출물_안내.html"),
    ("docs/기획서/기획서.pdf", "01_기획서/기획서.pdf"),
    ("docs/제출용/설치_운영_매뉴얼.pdf", "02_실행환경_매뉴얼/설치_운영_매뉴얼.pdf"),
    ("docs/제출용/사용자_매뉴얼.pdf", "02_실행환경_매뉴얼/사용자_매뉴얼.pdf"),
    ("docs/제출용/데이터_활용_명세.pdf", "03_데이터_활용_명세/데이터_활용_명세.pdf"),
    ("docs/제출용/결과_설명자료.pdf", "04_결과_설명자료/결과_설명자료.pdf"),
]
RESULTS_DIR = ("docs/결과예시", "04_결과_설명자료/결과예시/")
EXCLUDE_FILES = {"config.ini", "design.md"}  # design.md: 개발용 내부 설계 메모(심사 자료 아님)
EXCLUDE_SUFFIX = {".pyc", ".zip"}
FORBIDDEN_WORDS = ("데이터목록", "컬럼확인용", "예시데이터 및")
DEMO_SPEC = [("1-08", "2026-04", "2026-06"), ("1-14", "2026-05", "2026-06")]


class Forbidden(Exception):
    pass


def _files(root: Path):
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in EXCLUDE_DIRS for part in rel.parts[:-1]) or (p.is_dir()):
            continue
        if any(w in p.name for w in FORBIDDEN_WORDS):
            raise Forbidden(f"배포 금지 파일이 저장소 안에 있습니다: {rel}")
        if rel.parts[0] in EXCLUDE_DIRS or p.name in EXCLUDE_FILES or p.suffix in EXCLUDE_SUFFIX:
            continue
        yield p, rel


def _config(root: Path, with_key: bool) -> str:
    text = (root / "config.example.ini").read_text(encoding="utf-8")
    if not with_key:
        return text
    cp = configparser.ConfigParser()
    cp.read(root / "config.ini", encoding="utf-8")
    key = cp.get("ai", "key", fallback="").strip()
    if not key:
        raise SystemExit("--with-key: config.ini에 [ai] key가 없습니다.")
    if "\nkey =\n" not in text:
        raise SystemExit("--with-key: config.example.ini에서 'key =' 줄을 찾지 못해 키를 넣을 수 없습니다.")
    return text.replace("\nkey =\n", f"\nkey = {key}\n", 1)


def _demo(root: Path, zf: zipfile.ZipFile):
    sys.path.insert(0, str(root))
    from app.synth import generate, month_range

    with tempfile.TemporaryDirectory() as d:
        k = 0
        for did, a, b in DEMO_SPEC:
            for f in generate(did, month_range(a, b), Path(d), index_offset=k):
                zf.write(f, f"{PROG}demo/{f.name}")
                k += 1
    zf.writestr(f"{PROG}demo/읽어주세요.txt",
                "이 폴더의 CSV는 혼디 체험용 '예시(가상) 데이터'입니다. 실제 제주빅데이터센터 데이터가 아닙니다.\r\n"
                "센터에서 내려받는 파일과 같은 형식(Results_날짜_시간.csv, UTF-8, 따옴표, NA)으로 만들었습니다.\r\n"
                "카드 이용 현황(읍면동) 2026-04~06, 카드 이용 현황(시간대) 2026-05~06.\r\n"
                "혼디 화면의 '받은 파일' 칸에 끌어다 놓아 보세요. 더 많은 예시는 '예시 데이터로 체험' 버튼으로 만들 수 있습니다.\r\n")


def build(out: Path, root: Path, with_key: bool = False) -> Path:
    root = Path(root).resolve()
    files = list(_files(root))  # 금지 파일 검사를 먼저 끝낸다
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src, dst in SUBMISSION:
            if not (root / src).exists():
                raise SystemExit(f"{src}가 없습니다. 먼저 'python tools/docs_pdf.py'로 제출용 PDF를 만드세요.")
            zf.write(root / src, dst)
        for p in sorted((root / RESULTS_DIR[0]).iterdir()):
            if p.is_file():
                zf.write(p, RESULTS_DIR[1] + p.name)
        for p, rel in files:
            zf.write(p, PROG + rel.as_posix())
        zf.writestr(f"{PROG}config.ini", _config(root, with_key))
        _demo(root, zf)
    for n in zipfile.ZipFile(out).namelist():
        if any(w in n for w in FORBIDDEN_WORDS):
            out.unlink()
            raise Forbidden(n)
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(__file__).resolve().parent.parent
    target = Path(args[0]) if args else root / "dist" / "혼디_최종결과물_Kwang.zip"
    p = build(target, root, with_key="--with-key" in sys.argv)
    print(f"만들었습니다: {p} ({p.stat().st_size / 1048576:.1f}MB)")
    pdf = target.parent / "혼디_기획서_Kwang.pdf"  # 대회 페이지에 따로 올리는 기획서
    pdf.write_bytes((root / "docs" / "기획서" / "기획서.pdf").read_bytes())
    print(f"기획서 복사: {pdf}")
