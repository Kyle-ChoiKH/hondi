"""설치.bat이 부르는 자가 진단 출력."""
from .selfcheck import run
from .session import APP_DIR, DEFAULT_BASE, load_config

MARK = {"ok": "[정상]", "warn": "[확인]", "fail": "[문제]"}

if __name__ == "__main__":
    for c in run(load_config(APP_DIR / "config.ini"), DEFAULT_BASE):
        print(f"  {MARK[c.level]} {c.name}: {c.detail}")
        if c.fix:
            print(f"         → {c.fix}")
