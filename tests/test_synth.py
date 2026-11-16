import csv
import re

from app.catalog import Catalog
from app.synth import generate

H108 = ["base_year_month", "dstrct_se", "city", "area_type", "bjd", "biz_cd", "biz_nm",
        "user_type", "tour_type", "age", "sex", "user_cnt", "use_cnt", "use_amt"]


def _read(p):
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def test_file_format(tmp_path):
    files = generate("1-08", ["2025-07", "2025-08"], tmp_path)
    assert len(files) == 2
    for p in files:
        assert re.fullmatch(r"Results_\d{8}_\d{6}\.csv", p.name)
        raw = p.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        first = raw.decode("utf-8").splitlines()
        assert first[0] == ",".join(f'"{h}"' for h in H108)
        assert first[1].startswith('"') and first[1].endswith('"')
        assert "pt_year" not in first[0]
    assert _read(files[0])[1][0] == "202507"


def test_has_small_cells_and_na(tmp_path):
    rows = _read(generate("1-08", ["2025-07"], tmp_path)[0])[1:]
    assert any(int(r[11]) < 10 for r in rows)
    assert any(r[8] == "NA" for r in rows)
    assert any(r[9] == "NA" for r in rows)
    assert len(rows) <= 20000


def test_deterministic(tmp_path):
    a = generate("1-08", ["2025-07"], tmp_path / "a", seed=3)[0].read_bytes()
    b = generate("1-08", ["2025-07"], tmp_path / "b", seed=3)[0].read_bytes()
    assert a == b


def test_first_unquoted_mode(tmp_path):
    line = generate("1-08", ["2025-07"], tmp_path, quote_mode="first_unquoted")[0] \
        .read_text(encoding="utf-8").splitlines()[1]
    assert line.startswith("202507,\"")


def test_other_datasets(tmp_path):
    cat = Catalog.load()
    for did in ["1-12", "1-14", "1-17", "1-19", "3-04", "4-11", "5-02"]:
        p = generate(did, ["2025-07"], tmp_path / did)[0]
        header = _read(p)[0]
        assert header == [c["name"] for c in cat.columns(did)], did
        assert len(_read(p)) > 10, did
