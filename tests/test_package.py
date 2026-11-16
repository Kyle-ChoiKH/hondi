import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import make_zip  # noqa: E402


def test_zip_has_required(tmp_path):
    out = make_zip.build(tmp_path / "hondi.zip", ROOT)
    names = set(zipfile.ZipFile(out).namelist())
    for need in [make_zip.PROG + "README.md", make_zip.PROG + "설치.bat", make_zip.PROG + "실행.bat", make_zip.PROG + "app/server.py", make_zip.PROG + "web/index.html",
                 make_zip.PROG + "매뉴얼/사용자_매뉴얼.md", make_zip.PROG + "매뉴얼/설치_운영_매뉴얼.md", make_zip.PROG + "docs/데이터_활용_명세.md",
                 make_zip.PROG + "docs/결과_설명자료.md", make_zip.PROG + "config.ini", make_zip.PROG + "requirements.txt",
                 make_zip.PROG + "app/data/catalog.json"]:
        assert need in names, need
    assert any(n.startswith(make_zip.PROG + "demo/") and n.endswith(".csv") for n in names)
    assert not any("/.venv/" in n or "__pycache__" in n or "/.git/" in n or "/.superpowers/" in n for n in names)
    assert make_zip.PROG + "tests/test_guard.py" in names  # 재현성: 테스트도 함께 제출


def test_zip_config_has_no_key_unless_given(tmp_path):
    out = make_zip.build(tmp_path / "hondi.zip", ROOT)
    import configparser
    cp = configparser.ConfigParser()
    cp.read_string(zipfile.ZipFile(out).read(make_zip.PROG + "config.ini").decode("utf-8"))
    assert cp.get("ai", "key") == "" and cp.get("hub", "project_key") == ""


def test_zip_excludes_forbidden(tmp_path):
    src = tmp_path / "src"
    shutil.copytree(ROOT, src, ignore=shutil.ignore_patterns(".venv", ".git", "work", "자료", "__pycache__", ".pytest_cache",
                                                              ".superpowers", "demo", "dist", "config.ini"))
    (src / "docs" / "제주데이터허브 데이터목록_20261105.xlsx").write_bytes(b"x")
    with pytest.raises(make_zip.Forbidden):
        make_zip.build(tmp_path / "bad.zip", src)


def test_bat_files_are_crlf_and_set_utf8():
    for name in ("설치.bat", "실행.bat"):
        raw = (ROOT / name).read_bytes()
        assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
        assert raw.startswith(b"@echo off\r\nchcp 65001")


def test_with_key_fails_loudly_when_key_line_missing(tmp_path):
    (tmp_path / "config.example.ini").write_text("[ai]\nkey=\n", encoding="utf-8")
    (tmp_path / "config.ini").write_text("[ai]\nkey = sk-test\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        make_zip._config(tmp_path, True)  # (M5)
    (tmp_path / "config.example.ini").write_text("[ai]\nkey =\n", encoding="utf-8")
    assert "key = sk-test" in make_zip._config(tmp_path, True)


def test_extension_module_list_for_center_allowlist():
    import list_ext_modules
    text = list_ext_modules.report(ROOT / ".venv")
    assert "_duckdb" in text and ".pyd" in text and "numpy" in text
    assert "허용 등록" in text


def test_zip_leaves_out_internal_development_notes(tmp_path):
    # 개발 과정 메모(설계 노트·아이디어 선정 과정)는 심사 자료가 아니므로 제출 ZIP에 넣지 않는다
    out = tmp_path / "h.zip"
    make_zip.build(out, ROOT)
    names = zipfile.ZipFile(out).namelist()
    assert make_zip.PROG + "docs/design.md" not in names
    for n in names:
        if n.endswith((".md", ".html", ".txt")):
            text = zipfile.ZipFile(out).read(n).decode("utf-8", "ignore")
            assert "아이디어 525" not in text and "융합" not in text, n


def test_zip_top_level_is_organized_by_required_items(tmp_path):
    # 대회 안내의 최종 결과물 구분(실행 소스 코드·실행환경/매뉴얼·데이터 활용 명세·결과 설명자료)대로 번호 폴더
    names = zipfile.ZipFile(make_zip.build(tmp_path / "h.zip", ROOT)).namelist()
    for need in ["00_제출물_안내.html", "01_기획서/기획서.pdf", "02_실행환경_매뉴얼/설치_운영_매뉴얼.pdf",
                 "02_실행환경_매뉴얼/사용자_매뉴얼.pdf", "03_데이터_활용_명세/데이터_활용_명세.pdf",
                 "04_결과_설명자료/결과_설명자료.pdf", "04_결과_설명자료/결과예시/보고서.pdf",
                 make_zip.PROG + "설치.bat", make_zip.PROG + "실행.bat"]:
        assert need in names, need
    tops = {n.split("/")[0] for n in names}
    assert tops == {"00_제출물_안내.html", "01_기획서", "02_실행환경_매뉴얼", "03_데이터_활용_명세", "04_결과_설명자료", "05_실행_소스코드"}
    assert not any("/docs/제출용/" in n or "/docs/기획서/" in n for n in names)  # PDF는 위쪽 폴더에만(중복 없음)
    guide = zipfile.ZipFile(tmp_path / "h.zip").read("00_제출물_안내.html").decode("utf-8")
    for link in ["01_기획서", "02_실행환경_매뉴얼/설치_운영_매뉴얼.pdf", "03_데이터_활용_명세/데이터_활용_명세.pdf",
                 "04_결과_설명자료/결과_설명자료.pdf", make_zip.PROG + "README.md"]:
        assert link in guide and any(n.startswith(link) for n in names), link
