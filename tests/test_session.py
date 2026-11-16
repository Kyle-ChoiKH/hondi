import pytest

from app.selfcheck import blocked_hits, run
from app.session import Session, load_config

INI = """[ai]
provider = openai
model = gpt-5-nano
key = sk-secret-123
monthly_limit_krw = 5000
[hub]
project_key = HUBKEY
[privacy]
send_aggregates = false
auto_delete = true
keep_results = false
[server]
port = 8770
"""


def test_defaults(tmp_path):
    cfg = load_config(tmp_path / "missing.ini")
    assert cfg.ai_provider == "none" and cfg.send_aggregates is False and cfg.auto_delete is True
    assert cfg.port == 8765 and cfg.ai_effort == "low"


def test_load_values(tmp_path):
    p = tmp_path / "config.ini"
    p.write_text(INI, encoding="utf-8")
    cfg = load_config(p)
    assert cfg.ai_key == "sk-secret-123" and cfg.hub_project_key == "HUBKEY"
    assert cfg.monthly_limit_krw == 5000 and cfg.port == 8770


def test_key_not_in_repr(tmp_path):
    p = tmp_path / "config.ini"
    p.write_text(INI, encoding="utf-8")
    cfg = load_config(p)
    assert "sk-secret-123" not in repr(cfg) and "HUBKEY" not in repr(cfg)
    assert "sk-secret-123" not in str(cfg.public())


def test_end_deletes(tmp_path):
    cfg = load_config(tmp_path / "none.ini")
    s = Session(tmp_path / "sessions", cfg)
    (s.uploads / "a.csv").write_text("x", encoding="utf-8")
    (s.outbox / "r.png").write_text("x", encoding="utf-8")
    s.activity("load", dataset="1-08", files=1)
    summary = s.end()
    assert not s.dir.exists() and summary["deleted"] >= 3


def test_keep_results(tmp_path):
    cfg = load_config(tmp_path / "none.ini")
    cfg.keep_results = True
    s = Session(tmp_path / "sessions", cfg)
    (s.uploads / "a.csv").write_text("x", encoding="utf-8")
    (s.outbox / "r.png").write_text("x", encoding="utf-8")
    s.end()
    assert (s.outbox / "r.png").exists() and not (s.uploads / "a.csv").exists()


def test_activity_has_no_values(tmp_path):
    s = Session(tmp_path / "sessions", load_config(tmp_path / "n.ini"))
    with pytest.raises(ValueError):
        s.activity("run", bjd="애월읍")
    s.activity("run", dataset="1-08", tool="trend", light="green")
    assert "애월읍" not in s.activity_path.read_text(encoding="utf-8")


def test_selfcheck_flags_blocked_url():
    assert blocked_hits(["https://api.openai.com/v1/chat/completions"]) == []
    hits = blocked_hits(["https://example.com/코인시세"])
    assert hits and hits[0][1] == "코인"


def test_selfcheck_all_pass_in_dev(tmp_path):
    checks = run(load_config(tmp_path / "n.ini"), tmp_path / "sessions")
    names = {c.name for c in checks}
    assert {"파이썬 버전", "분석 엔진(duckdb)", "그림(matplotlib)", "데이터 카탈로그", "PDF 변환(Edge)", "외부 주소 차단 점검"} <= names
    assert not [c for c in checks if c.level == "fail"], [c for c in checks if c.level == "fail"]


def test_sweep_removes_dead_sessions_only(tmp_path):
    import os
    from app.session import sweep_stale
    base = tmp_path / "sessions"
    cfg = load_config(tmp_path / "n.ini")
    live = Session(base, cfg)                      # 지금 프로세스가 쓰는 세션(잠금 파일 있음)
    dead = base / "20260101_000000_dead00"
    (dead / "uploads").mkdir(parents=True)
    (dead / "uploads" / "a.csv").write_text("x", encoding="utf-8")
    (dead / ".lock").write_text("999999", encoding="utf-8")   # 없는 PID
    nolock = base / "20260101_000001_old000"
    (nolock / "out").mkdir(parents=True)
    n = sweep_stale(base)
    assert n == 2 and live.dir.exists() and not dead.exists() and not nolock.exists()
    assert (live.dir / ".lock").read_text(encoding="utf-8").strip() == str(os.getpid())


def test_app_start_sweeps_when_auto_delete(tmp_path):
    from app.server import create_app
    base = tmp_path / "sessions"
    old = base / "20260101_000000_old000" / "uploads"
    old.mkdir(parents=True)
    (old / "a.csv").write_text("x", encoding="utf-8")
    create_app(load_config(tmp_path / "n.ini"), base)
    assert not old.parent.exists()
