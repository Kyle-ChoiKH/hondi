"""대회 데이터 탭의 헤더 예시 엑셀(시트마다 데이터 1종)을 혼디 카탈로그가 모두 알아보는지 확인한다.

사용: python tools/check_headers.py "<예시데이터 및 컬럼확인용.xlsx 경로>"   (openpyxl 필요: requirements-dev.txt)
예시 파일은 배포 제한 자료라 저장소·제출 ZIP에 넣지 않았다. 파일을 가진 사람이 직접 경로를 넘겨 확인한다.
"""
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.catalog import Catalog  # noqa: E402


def header(ws):
    for row in ws.iter_rows(values_only=True):
        vals = [str(v).strip() for v in row if v is not None and str(v).strip()]
        if len(vals) >= 2 and all(v.replace("_", "").isascii() for v in vals):
            return vals
    return None


def main(path: str) -> int:
    cat = Catalog.load()
    wb = openpyxl.load_workbook(path, read_only=True)
    miss = []
    for ws in wb.worksheets:
        h = header(ws)
        if not h or not cat.candidates(h):
            miss.append(ws.title)
    n = len(wb.worksheets)
    print(f"시트 {n}개 중 {n - len(miss)}개 인식" + (f", 못 알아본 시트: {', '.join(miss)}" if miss else ""))
    return 1 if miss else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    raise SystemExit(main(sys.argv[1]))
