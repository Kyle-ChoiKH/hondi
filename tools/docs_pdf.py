"""제출용 문서 PDF 만들기: 매뉴얼·데이터 활용 명세·결과 설명자료(Markdown) → docs/제출용/*.pdf

사용: python tools/docs_pdf.py      (개발용 패키지 markdown 필요: requirements-dev.txt)
심사위원이 프로그램을 설치하지 않고도 문서를 바로 열어 볼 수 있게, 원본 Markdown과 같은 내용을 PDF로 만든다.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.report import to_pdf  # noqa: E402

OUT = ROOT / "docs" / "제출용"
DOCS = [  # (원본 Markdown, PDF 이름, 문서 위 작은 제목)
    ("매뉴얼/설치_운영_매뉴얼.md", "설치_운영_매뉴얼.pdf", "실행환경·매뉴얼"),
    ("매뉴얼/사용자_매뉴얼.md", "사용자_매뉴얼.pdf", "실행환경·매뉴얼"),
    ("docs/데이터_활용_명세.md", "데이터_활용_명세.pdf", "데이터 활용 명세"),
    ("docs/결과_설명자료.md", "결과_설명자료.pdf", "결과 설명자료"),
]


def css() -> str:
    fonts = (ROOT / "web" / "fonts").as_uri()
    faces = "".join(f'@font-face{{font-family:"Pretendard";font-weight:{w};src:url({fonts}/Pretendard-{n}.subset.woff2) format("woff2")}}'
                    for w, n in (("400", "Regular"), ("500", "Medium"), ("600", "SemiBold"), ("700 800", "Bold")))
    return faces + """
@page{size:A4;margin:16mm 15mm 16mm}
body{font-family:"Pretendard","Malgun Gothic",sans-serif;color:#191f28;font-size:10pt;line-height:1.65;letter-spacing:-.01em;word-break:keep-all;
  -webkit-print-color-adjust:exact;print-color-adjust:exact;margin:0}
.kicker{font-size:8.5pt;font-weight:700;color:#3182f6;margin-bottom:1mm}
h1{font-size:20pt;font-weight:800;letter-spacing:-.03em;margin:0 0 4mm;padding-bottom:3mm;border-bottom:2px solid #3182f6}
h2{font-size:14pt;font-weight:800;letter-spacing:-.02em;margin:8mm 0 2.5mm;break-after:avoid}
h3{font-size:11.5pt;font-weight:700;margin:5mm 0 2mm;break-after:avoid}
p{margin:1.5mm 0}
ul,ol{margin:1.5mm 0;padding-left:6mm}li{margin:.6mm 0}
table{border-collapse:collapse;width:100%;font-size:8.9pt;margin:2mm 0;break-inside:auto}
tr{break-inside:avoid}
th,td{border-bottom:1px solid #e5e8eb;padding:1.6mm 2.2mm;text-align:left;vertical-align:top}
th{background:#f9fafb;color:#4e5968;font-weight:700;border-bottom:1.4px solid #d1d6db}
code{font-family:Consolas,"D2Coding",monospace;font-size:8.6pt;background:#f2f4f6;border-radius:3px;padding:0 3px}
pre{background:#191f28;color:#e5e8eb;border-radius:3mm;padding:3mm 4mm;font-size:8.4pt;line-height:1.5;white-space:pre-wrap;break-inside:avoid}
pre code{background:none;color:inherit;padding:0}
blockquote{margin:2mm 0;padding:2mm 4mm;background:#e8f3ff;border-radius:2mm;color:#333d4b}
blockquote p{margin:0}
img{max-width:100%;border-radius:2mm;box-shadow:0 0 0 1px #e5e8eb;margin:2mm 0;break-inside:avoid}
strong{font-weight:700}
"""


def build_one(src: Path, pdf: Path, kicker: str) -> Path:
    body = markdown.markdown(src.read_text(encoding="utf-8"), extensions=["tables", "fenced_code", "sane_lists"])
    title = src.stem.replace("_", " ")
    page = (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{css()}</style></head><body><div class='kicker'>혼디 · 팀 Kwang · {html.escape(kicker)}</div>{body}</body></html>")
    tmp = src.with_name(f".__pdf_{src.stem}.html")  # 그림 상대 경로가 그대로 맞도록 원본 옆에 잠깐 만든다
    try:
        tmp.write_text(page, encoding="utf-8")
        out = to_pdf(tmp, pdf)
    finally:
        tmp.unlink(missing_ok=True)
    if not out:
        raise SystemExit("PDF 변환 실패: Edge 또는 Chrome이 필요합니다.")
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for rel, name, kicker in DOCS:
        p = build_one(ROOT / rel, OUT / name, kicker)
        print(f"{p.relative_to(ROOT)} ({p.stat().st_size / 1024:.0f}KB)")


if __name__ == "__main__":
    main()
