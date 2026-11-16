"""설정(config.ini)과 이용 세션. 퇴실 시 반출 승인 자료 외 데이터는 지워야 하므로 세션 폴더째 삭제한다."""
from __future__ import annotations

import configparser
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BASE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Hondi" / "sessions"
ACTIVITY_KEYS = {"dataset", "tool", "months", "count", "light", "purpose", "result_id", "fix", "files", "source",
                 "status", "kind"}


@dataclass
class Config:
    ai_provider: str = "none"
    ai_model: str = "gpt-5-nano"
    ai_key: str = field(default="", repr=False)
    ai_effort: str = "low"
    price_in: float = 0.05
    price_out: float = 0.40
    usd_krw: float = 1400.0
    monthly_limit_krw: float = 20000.0
    hub_project_key: str = field(default="", repr=False)
    send_aggregates: bool = False
    auto_delete: bool = True
    keep_results: bool = False
    port: int = 8765
    path: str = ""

    def public(self) -> dict:
        return {"ai_provider": self.ai_provider, "ai_model": self.ai_model, "ai_key_set": bool(self.ai_key),
                "hub_key_set": bool(self.hub_project_key), "send_aggregates": self.send_aggregates,
                "auto_delete": self.auto_delete, "keep_results": self.keep_results,
                "monthly_limit_krw": self.monthly_limit_krw}


def load_config(path: Path) -> Config:
    cfg = Config(path=str(path))
    p = configparser.ConfigParser()
    try:
        p.read(path, encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError):
        return cfg

    def get(sec, key, default, conv=str):
        try:
            v = p.get(sec, key, fallback="").strip()
            return conv(v) if v != "" else default
        except (ValueError, configparser.Error):
            return default

    def b(v: str) -> bool:
        return v.lower() in ("1", "true", "yes", "on", "예")

    cfg.ai_provider = get("ai", "provider", cfg.ai_provider).lower()
    cfg.ai_model = get("ai", "model", cfg.ai_model)
    cfg.ai_key = get("ai", "key", "")
    cfg.ai_effort = get("ai", "reasoning_effort", cfg.ai_effort)
    cfg.price_in = get("ai", "price_in_per_mtok_usd", cfg.price_in, float)
    cfg.price_out = get("ai", "price_out_per_mtok_usd", cfg.price_out, float)
    cfg.usd_krw = get("ai", "usd_krw", cfg.usd_krw, float)
    cfg.monthly_limit_krw = get("ai", "monthly_limit_krw", cfg.monthly_limit_krw, float)
    cfg.hub_project_key = get("hub", "project_key", "")
    cfg.send_aggregates = get("privacy", "send_aggregates", cfg.send_aggregates, b)
    cfg.auto_delete = get("privacy", "auto_delete", cfg.auto_delete, b)
    cfg.keep_results = get("privacy", "keep_results", cfg.keep_results, b)
    cfg.port = get("server", "port", cfg.port, int)
    return cfg


def pid_alive(pid: int) -> bool:
    """프로세스가 살아 있는지(Windows는 OpenProcess로 확인, 종료 신호를 보내지 않는다)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not h:
            return False
        try:
            return k.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT = 아직 실행 중
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def sweep_stale(base: Path) -> int:
    """창을 그냥 닫는 등으로 지워지지 않은 이전 세션 폴더를 지운다. 실행 중인 다른 혼디의 세션은 남긴다."""
    base, n = Path(base), 0
    if not base.is_dir():
        return 0
    for d in base.iterdir():
        if not d.is_dir():
            continue
        lock = d / ".lock"
        try:
            pid = int(lock.read_text(encoding="utf-8").strip()) if lock.exists() else 0
        except (OSError, ValueError):
            pid = 0
        if pid and pid_alive(pid):
            continue
        shutil.rmtree(d, ignore_errors=True)
        n += 0 if d.exists() else 1
    return n


class Session:
    def __init__(self, base: Path, cfg: Config):
        self.cfg = cfg
        self.base = Path(base)
        self.id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
        self.dir = self.base / self.id
        self.uploads = self.dir / "uploads"
        self.outbox = self.dir / "out"
        for d in (self.uploads, self.outbox):
            d.mkdir(parents=True, exist_ok=True)
        (self.dir / ".lock").write_text(str(os.getpid()), encoding="utf-8")
        self.ai_log = self.dir / "ai_log.jsonl"
        self.activity_path = self.dir / "activity.jsonl"
        self.usage_path = self.base.parent / "usage.json"
        self.cache_dir = self.base.parent / "hub_cache"

    def activity(self, event: str, **meta):
        bad = set(meta) - ACTIVITY_KEYS
        if bad:
            raise ValueError(f"이용 기록에는 데이터 값을 남기지 않습니다: {sorted(bad)}")
        rec = {"time": datetime.now().isoformat(timespec="seconds"), "event": event, **meta}
        with open(self.activity_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def end(self) -> dict:
        files = [p for p in self.dir.rglob("*") if p.is_file()] if self.dir.exists() else []
        if not self.cfg.auto_delete:
            return {"deleted": 0, "kept": [str(self.dir)]}
        if self.cfg.keep_results:
            gone = [p for p in files if self.outbox not in p.parents]
            for p in gone:
                p.unlink(missing_ok=True)
            shutil.rmtree(self.uploads, ignore_errors=True)
            return {"deleted": len(gone), "kept": [str(self.outbox)]}
        shutil.rmtree(self.dir, ignore_errors=True)
        return {"deleted": len(files), "kept": []}
