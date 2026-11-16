import pytest

from app.catalog import Catalog
from app.ingest import Workspace

H108 = ["base_year_month", "dstrct_se", "city", "area_type", "bjd", "biz_cd", "biz_nm",
        "user_type", "tour_type", "age", "sex", "user_cnt", "use_cnt", "use_amt"]


def months(a, b):
    y, m = int(a[:4]), int(a[5:])
    out = []
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def small_rows():
    """손계산용 1-08 데이터: 2024-07~2025-08(14개월), 애월읍·노형동, 한식·커피 2업종.

    애월읍 한식 도민: user_cnt 20, use_cnt 30, use_amt = 1000 × 월순번(1..14)
    애월읍 한식 일본: user_cnt 3,  use_cnt 4,  use_amt 100
    애월읍 커피 도민: user_cnt 50, use_cnt 60, use_amt 500
    노형동 한식 도민: user_cnt 40, use_cnt 50, use_amt 2000
    """
    rows = []
    for i, ym in enumerate(months("2024-07", "2025-08"), start=1):
        rows.append([ym, "제주시 서부", "제주시", "읍면", "애월읍", "I56111", "한식 음식점업", "제주도민", "도민",
                     "40", "여성", 20, 30, 1000 * i])
        rows.append([ym, "제주시 서부", "제주시", "읍면", "애월읍", "I56111", "한식 음식점업", "일본", "개별",
                     "30", "남성", 3, 4, 100])
        rows.append([ym, "제주시 서부", "제주시", "읍면", "애월읍", "I56220", "비알콜 음료점업", "제주도민", "도민",
                     "20", "여성", 50, 60, 500])
        rows.append([ym, "제주시 중부(서)", "제주시", "도심", "노형동", "I56111", "한식 음식점업", "제주도민", "도민",
                     "50", "남성", 40, 50, 2000])
    return rows


def write_csv(path, header, rows):
    lines = [",".join(f'"{h}"' for h in header)]
    for r in rows:
        lines.append(",".join(f'"{v}"' for v in r))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def cat():
    return Catalog.load()


@pytest.fixture
def small_ws(tmp_path, cat):
    rows = small_rows()
    files = []
    for ym in sorted({r[0] for r in rows}):
        files.append(write_csv(tmp_path / f"Results_20261109_{ym}.csv", H108, [r for r in rows if r[0] == ym]))
    ws = Workspace(cat)
    ws.add_files(files)
    return ws
