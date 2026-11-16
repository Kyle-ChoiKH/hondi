"""매뉴얼·기획서용 화면 캡처. 실행 중인 혼디(127.0.0.1:포트)를 Edge 헤드리스로 열어 #tour=장면을 찍는다.

사용: python tools/shots.py [포트] [장면 ...]   → docs/img/화면_<장면>.png
주의: 장면마다 세션을 새로 시작하므로(이전 세션 삭제) 실제 사용 중인 혼디에는 쓰지 마세요.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.report import find_browser  # noqa: E402

SCENES = ["start", "home", "easy", "prep", "ask", "results", "guard", "fixed", "export", "outbound", "dataset", "rerun"]


def shoot(port: int, scene: str, out_dir: Path, size: str = "1600,1000") -> Path:
    out = out_dir / f"화면_{scene}.png"
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([find_browser(), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={prof}",
                        f"--window-size={size}", "--virtual-time-budget=90000", f"--screenshot={out}",
                        f"http://127.0.0.1:{port}/#tour={scene}"], timeout=180, capture_output=True)
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    port = int(args[0]) if args and args[0].isdigit() else 8765
    size = next((a.split("=", 1)[1] for a in args if a.startswith("--size=")), "1600,1000")
    out = next((a.split("=", 1)[1] for a in args if a.startswith("--out=")), "")
    scenes = [a for a in args if not a.isdigit() and not a.startswith("--")] or SCENES
    d = Path(out) if out else ROOT / "docs" / "img"
    d.mkdir(parents=True, exist_ok=True)
    for s in scenes:
        p = shoot(port, s, d, size)
        print(s, p.exists() and p.stat().st_size)
