from app.josa import j


def test_particles_follow_last_syllable():
    assert j("추이", "을") == "추이를" and j("구성비", "을") == "구성비를" and j("순위", "을") == "순위를"
    assert j("이용금액", "이") == "이용금액이" and j("이용건수", "이") == "이용건수가"
    assert j("노형동", "은") == "노형동은" and j("애월읍", "와") == "애월읍과" and j("한림", "로") == "한림으로"
    assert j("법정동", "로") == "법정동으로" and j("행정시", "로") == "행정시로" and j("서울", "로") == "서울로"


def test_non_hangul_falls_back_to_both_forms():
    assert j("use_amt", "을") == "use_amt을(를)"
    assert j("'카드'", "은") == "'카드'는"  # 따옴표는 건너뛰고 안의 낱말로 판단


def test_narrative_and_plan_text_have_no_paired_particles(small_ws, cat):
    from app.model import Step
    from app.narrate import narrate
    from app.tools import run_step
    r = run_step(small_ws, cat, Step("trend", "1-08", "use_amt", ["base_year_month"], {}, {}))
    text = " ".join(narrate(r, cat))
    assert "(가)" not in text and "(를)" not in text


def test_ieyo_and_digits_and_quoted_words():
    assert j("애월읍", "예요") == "애월읍이에요" and j("제주도민", "예요") == "제주도민이에요" and j("노형동", "예요") == "노형동이에요"
    assert j("한식", "예요") == "한식이에요" and j("2위", "예요") == "2위예요" and j("요일", "예요") == "요일이에요"
    assert j("18", "예요") == "18이에요" and j("2", "예요") == "2예요"   # 숫자는 읽는 소리(십팔·이)로
    assert j("'애월읍'", "예요") == "'애월읍'이에요" and j("'내국인'", "와") == "'내국인'과"  # 따옴표 안 낱말 기준
