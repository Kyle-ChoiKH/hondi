import csv
import io

import pytest

from app.catalog import Catalog
from app.ingest import Workspace
from app.synth import generate


@pytest.fixture(scope="module")
def cat():
    return Catalog.load()


def _sum(ws, did, col):
    return ws.con.execute(f"select sum({col}) from {ws.table(did)}").fetchone()[0]


def test_load_and_identify(tmp_path, cat):
    files = generate("1-08", ["2025-07", "2025-08", "2025-09"], tmp_path)
    ws = Workspace(cat)
    infos = ws.add_files(files)
    assert all(i.status == "ok" for i in infos)
    ds = ws.datasets()
    assert len(ds) == 1 and ds[0].id == "1-08"
    assert ds[0].months == ["2025-07", "2025-08", "2025-09"]
    assert ds[0].rows == sum(i.rows for i in infos)


def test_both_quote_modes_and_bom(tmp_path, cat):
    a = generate("1-08", ["2025-07"], tmp_path / "a")[0]
    b = generate("1-08", ["2025-07"], tmp_path / "b", quote_mode="first_unquoted")[0]
    c = tmp_path / "c.csv"
    c.write_bytes(b"\xef\xbb\xbf" + a.read_bytes())
    sums = []
    for p in (a, b, c):
        ws = Workspace(cat)
        ws.add_files([p])
        sums.append(_sum(ws, "1-08", "use_amt"))
    assert sums[0] == sums[1] == sums[2] and sums[0] > 0


def test_missing_month(tmp_path, cat):
    files = generate("1-08", ["2025-07", "2025-08", "2025-10"], tmp_path)
    ws = Workspace(cat)
    ws.add_files(files)
    assert ws.datasets()[0].missing == ["2025-09"]


def test_reorders_and_extra_columns(tmp_path, cat):
    src = generate("1-08", ["2025-07"], tmp_path / "s")[0]
    rows = list(csv.reader(io.StringIO(src.read_text(encoding="utf-8"))))
    header = rows[0]
    order = list(reversed(range(len(header))))
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow([header[i] for i in order] + ["extra_col"])
    for r in rows[1:]:
        w.writerow([r[i] for i in order] + ["x"])
        w.writerow([])
    p = tmp_path / "Results_20261109_120000.csv"
    p.write_text(buf.getvalue(), encoding="utf-8")
    ws = Workspace(cat)
    info = ws.add_files([p])[0]
    assert info.status == "ok" and info.dataset_id == "1-08"
    assert "extra_col" in info.message
    ref = Workspace(cat)
    ref.add_files([src])
    assert _sum(ws, "1-08", "use_amt") == _sum(ref, "1-08", "use_amt")


def test_duplicate_and_mixed_files(tmp_path, cat):
    a = generate("1-08", ["2025-07"], tmp_path / "a")[0]
    b = generate("1-14", ["2025-07"], tmp_path / "b")[0]
    ws = Workspace(cat)
    infos = ws.add_files([a, a, b])
    assert [i.status for i in infos] == ["ok", "duplicate", "ok"]
    assert sorted(d.id for d in ws.datasets()) == ["1-08", "1-14"]


def test_unknown_file(tmp_path, cat):
    p = tmp_path / "x.csv"
    p.write_text('"foo","bar"\n"1","2"\n', encoding="utf-8")
    info = Workspace(cat).add_files([p])[0]
    assert info.status == "unknown"


def test_numbers_cast(tmp_path, cat):
    p = generate("1-08", ["2025-07"], tmp_path)[0]
    ws = Workspace(cat)
    ws.add_files([p])
    types = dict(ws.con.execute(f"select column_name, data_type from information_schema.columns "
                                f"where table_name = '{ws.table('1-08')}'").fetchall())
    assert types["use_amt"] in ("BIGINT", "HUGEINT", "DOUBLE")
    nulls = ws.con.execute(f"select count(*) from {ws.table('1-08')} where age is null").fetchone()[0]
    assert nulls > 0
    assert "애월읍" in ws.distinct("1-08", "bjd")
    assert "애월읍" in ws.dim_values()["bjd"]


def test_popular_orders_by_row_count(tmp_path, cat):
    from conftest import H108, write_csv
    base = ["202601", "제주시 서부", "제주시", "읍면", "", "I56111", "한식 음식점업", "제주도민", "도민", "40", "여성", 20, 30, 1000]
    rows = [base[:4] + [b] + base[5:] for b in ["애월읍"] * 3 + ["노형동"] + ["가가동"] * 2]
    ws = Workspace(cat)
    ws.add_files([write_csv(tmp_path / "Results_20260101_000000.csv", H108, rows)])
    assert ws.popular("1-08", "bjd", 2) == ["애월읍", "가가동"]


def test_needs_include_popular_top(small_ws, cat):
    from app.model import Plan, Step
    from app.planner import needs
    plan = Plan("자유", [Step("trend", "1-08", "use_amt", ["base_year_month"], {"bjd": "?"}, {})])
    n = needs(plan, small_ws, cat)[0]
    assert n["top"] and set(n["top"]) <= set(n["options"])


def test_same_content_different_bytes_is_duplicate(tmp_path, cat):
    from conftest import H108, small_rows, write_csv
    rows = [r for r in small_rows() if r[0] == "202407"]
    a = write_csv(tmp_path / "Results_20261109_000001.csv", H108, rows)
    b = tmp_path / "Results_20261109_000002.csv"
    b.write_bytes(a.read_bytes().replace(b"\n", b"\r\n"))       # 같은 내용, 줄바꿈만 다름
    c = write_csv(tmp_path / "Results_20261109_000003.csv", H108,
                  [r[:4] + ["한림읍"] + r[5:] for r in rows])      # 같은 달, 다른 조건(지역)
    ws = Workspace(cat)
    out = ws.add_files([a, b, c])
    assert [o.status for o in out] == ["ok", "duplicate", "ok"]
    n = ws.con.execute(f"select count(*) from {ws.table('1-08')}").fetchone()[0]
    assert n == 2 * len(rows)


def test_crlf_file_loads_with_exact_values(tmp_path, cat):
    from conftest import H108, small_rows, write_csv
    rows = [r for r in small_rows() if r[0] == "202407"]
    a = write_csv(tmp_path / "x.csv", H108, rows)
    b = tmp_path / "Results_20261109_000009.csv"
    b.write_bytes(a.read_bytes().replace(b"\n", b"\r\n"))       # 윈도우 줄바꿈(CRLF) 파일
    ws = Workspace(cat)
    out = ws.add_files([b])
    assert out[0].status == "ok" and out[0].rows == len(rows)
    tot = ws.con.execute(f"select sum(use_amt), max(length(sex)) from {ws.table('1-08')}").fetchone()
    assert tot[0] == sum(r[13] for r in rows) and tot[1] == 2


def test_same_columns_ask_which_dataset(tmp_path, cat):
    from conftest import write_csv
    h = [c["name"] for c in cat.columns("1-02")]
    p = write_csv(tmp_path / "Results_20261109_000010.csv", h, [["202501", "제주", "면세점", "개인", "1000", "500"]])
    ws = Workspace(cat)
    out = ws.add_files([p])
    assert out[0].status == "ambiguous" and set(out[0].candidates) == {"1-02", "1-05"}
    assert ws.loaded() == []
    out = ws.add_files([p], dataset="1-05")
    assert out[0].status == "ok" and ws.loaded() == ["1-05"]


def test_text_values_are_trimmed(tmp_path, cat):
    from conftest import H108, small_rows, write_csv
    rows = [r[:4] + [r[4] + "      "] + r[5:] for r in small_rows() if r[0] == "202407"]
    ws = Workspace(cat)
    ws.add_files([write_csv(tmp_path / "Results_20261109_000020.csv", H108, rows)])
    assert "애월읍" in ws.distinct("1-08", "bjd") and not any(v.endswith(" ") for v in ws.distinct("1-08", "bjd"))
