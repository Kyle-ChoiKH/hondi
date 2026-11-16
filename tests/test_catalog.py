from app.catalog import Catalog

H108 = ["base_year_month", "dstrct_se", "city", "area_type", "bjd", "biz_cd", "biz_nm",
        "user_type", "tour_type", "age", "sex", "user_cnt", "use_cnt", "use_amt"]


def test_has_core_datasets():
    cat = Catalog.load()
    ids = set(cat.ids())
    assert {"1-08", "1-12", "1-14", "1-17", "1-19", "3-04", "4-11", "5-02"} <= ids
    assert len(ids) >= 70


def test_roles():
    cat = Catalog.load()
    cols = {c["name"]: c for c in cat.columns("1-08")}
    assert cols["use_cnt"]["role"] == "count"
    assert cols["user_cnt"]["role"] == "count"
    assert cols["use_amt"]["role"] == "amount"
    assert cols["base_year_month"]["role"] == "time"
    assert cols["bjd"]["role"] == "dim"
    assert "pt_year" not in cols
    assert "pt_year" in {c["name"] for c in cat.columns("1-08", include_partition=True)}


def test_identify_v02_vs_v01():
    cat = Catalog.load()
    assert cat.identify(H108) == "1-08"
    assert cat.identify([h for h in H108 if h != "dstrct_se"]) == "1-07"
    assert cat.identify(["foo", "bar", "baz"]) is None


def test_rollup():
    cat = Catalog.load()
    assert cat.rollup_parent("1-08", "bjd") == "dstrct_se"
    assert cat.rollup_parent("1-08", "dstrct_se") == "city"
    assert cat.rollup_parent("1-08", "base_year_month") == "quarter"
    assert cat.rollup_parent("1-08", "biz_nm") == "biz_group"
    assert cat.rollup_parent("1-08", "age") == "age_band"
    assert cat.rollup_parent("1-08", "user_type") == "user_group"


def test_sensitivity():
    cat = Catalog.load()
    assert cat.is_sensitive("1-08") is True
    assert cat.is_sensitive("3-04") is False
    assert cat.count_col("1-08") == "use_cnt"


def test_virtual_sql_only_when_source_exists():
    cat = Catalog.load()
    v = cat.virtual_sql("1-08")
    assert {"quarter", "year", "biz_group", "age_band", "user_group"} <= set(v)
    assert "biz_group" not in cat.virtual_sql("4-11")


# 대회 데이터 탭 '예시데이터 및 컬럼확인용'(2026-11-15)에서 확인한 실제 머리글 차이
def test_real_header_names_are_recognized():
    from app.catalog import Catalog
    c = Catalog.load()
    assert set(c.candidates(["base_year_month", "province", "theme", "user_type", "amount_per_person",
                             "amount_per_case"])) == {"1-03", "1-06"}
    assert c.column("1-03", "theme") and not c.column("1-03", "market_theme")
    assert c.column("1-04", "eupmyeondong") and c.time_col("1-32") == "base_date"
    assert c.column("3-08", "collect_date") and c.column("5-04", "certificate_id")
