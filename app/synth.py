"""명세서 구조를 따른 가상 센터 CSV 생성기(개발·시연·심사용).

실제 센터 데이터가 아니며 값은 모두 무작위로 만든 것이다. 파일 형식은 센터 조회 결과와 같다:
UTF-8(BOM 없음), 쉼표, 모든 값 큰따옴표, 결측 NA, 파티션 컬럼 없음, Results_YYYYMMDD_HHMMSS.csv.
법정동→권역 배정은 시연용 가정이다(실제 파일에는 권역 컬럼이 들어 있다).
"""
from __future__ import annotations

import calendar
import csv
import io
import math
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .catalog import Catalog

JEJU_EAST = ["구좌읍", "조천읍", "우도면", "봉개동", "회천동", "도련일동", "도련이동", "삼양일동",
             "삼양이동", "삼양삼동", "화북일동", "화북이동"]
JEJU_MID_E = ["일도일동", "일도이동", "이도일동", "이도이동", "건입동", "아라일동", "아라이동", "오등동",
              "영평동", "월평동", "용강동", "삼도일동", "삼도이동"]
JEJU_MID_W = ["노형동", "연동", "해안동", "도평동", "외도일동", "외도이동", "이호일동", "이호이동",
              "도두일동", "도두이동", "내도동", "오라일동", "오라이동", "오라삼동", "용담일동", "용담이동",
              "용담삼동", "도남동"]
JEJU_WEST = ["애월읍", "한림읍", "한경면", "추자면"]
SGP_EAST = ["성산읍", "표선면", "남원읍", "토평동", "신효동", "하효동", "보목동", "상효동"]
SGP_MID = ["서귀동", "동홍동", "서홍동", "호근동", "서호동", "법환동", "강정동", "도순동", "영남동",
           "월평동", "하원동", "대포동"]
SGP_WEST = ["대정읍", "안덕면", "중문동", "색달동", "상예동", "하예동", "회수동"]
DISTRICTS = [("제주시 동부", "제주시", JEJU_EAST), ("제주시 중부(동)", "제주시", JEJU_MID_E),
             ("제주시 중부(서)", "제주시", JEJU_MID_W), ("제주시 서부", "제주시", JEJU_WEST),
             ("서귀포시 동부", "서귀포시", SGP_EAST), ("서귀포시 중부", "서귀포시", SGP_MID),
             ("서귀포시 서부", "서귀포시", SGP_WEST)]
HOT = {"애월읍": 3.0, "성산읍": 2.6, "중문동": 2.6, "노형동": 3.2, "연동": 3.4, "일도이동": 2.2,
       "이도이동": 2.4, "한림읍": 1.8, "조천읍": 1.6, "구좌읍": 1.6, "서귀동": 2.0, "표선면": 1.5,
       "안덕면": 1.5, "색달동": 1.6, "용담이동": 1.5}
TOUR_BIZ = {"I56111": 3.0, "I56220": 2.6, "G47122": 2.8, "I56112": 1.4, "I56113": 1.3, "I56114": 1.6,
            "I55111": 1.8, "L69110": 1.5, "G47121": 2.2, "G47842": 1.2, "I56219": 1.6, "G47711": 1.8}
TICKET = {"I": 18000, "G": 22000, "H": 9000, "L": 90000, "N": 120000, "R": 60000, "S": 40000}
USERS = [("제주도민", "도민", 3.0), ("내국인", "개별", 2.4), ("내국인", "단체", 0.5), ("법인", "NA", 0.5),
         ("중국", "개별", 0.35), ("일본", "개별", 0.2), ("동남아", "개별", 0.15), ("기타외국", "개별", 0.15),
         ("중국", "단체", 0.2)]
AGES = [("10", 0.3), ("20", 1.1), ("30", 1.4), ("40", 1.4), ("50", 1.1), ("60", 0.7), ("70", 0.35)]
WEEK = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일", "공휴일"]
TIMES = [("오전", 0.8), ("점심", 1.5), ("오후", 1.0), ("저녁", 1.6), ("밤", 0.4)]
POS = [("Q04", "별식/퓨전요리", "Q04008", "퓨전음식전문"), ("Q06", "분식", "Q06002", "떡볶이전문"),
       ("Q06", "분식", "Q06004", "국수전문"), ("Q07", "양식", "Q07002", "돈가스전문점"),
       ("Q10", "일식/수산물", "Q10011", "생선회전문"), ("Q13", "커피/음료", "Q13006", "커피전문점"),
       ("Q01", "한식", "Q01003", "흑돼지구이전문"), ("Q03", "닭/오리요리", "Q03001", "치킨전문")]
STATIONS = [("4001", "제주국제공항"), ("4002", "제주시외버스터미널"), ("4003", "동문로터리"),
            ("4004", "노형오거리"), ("4005", "서귀포버스터미널"), ("4006", "중문관광단지"),
            ("4007", "성산일출봉입구"), ("4008", "애월하나로마트")]
OBS = ["184", "185", "188", "189", "328"]
SKT_AGES = ["2024", "3539", "5054", "7000"]


def season(month: int) -> float:
    return 1.0 + 0.35 * math.sin((month - 4) / 12 * 2 * math.pi) + (0.25 if month in (7, 8) else 0)


def _bjd_list():
    out = []
    for dst, city, names in DISTRICTS:
        for n in names:
            out.append((dst, city, "읍면" if n[-1] in "읍면" else "도심", n))
    return out


def _biz(cat: Catalog):
    rows = cat.get("1-08")["codes"]["업종코드 및 업종명"]
    return [(r[0], r[1]) for r in rows if isinstance(r, list)]


def _q(row, mode):
    out = []
    for i, v in enumerate(row):
        s = str(v)
        out.append(s if (mode == "first_unquoted" and i == 0) else '"' + s.replace('"', '""') + '"')
    return ",".join(out)


def _card_rows(cat, rng, ym, extra):
    y, m = int(ym[:4]), int(ym[5:])
    biz = _biz(cat)
    rows = []
    for dst, city, area, bjd in _bjd_list():
        hot = HOT.get(bjd, 1.0)
        weights = [TOUR_BIZ.get(b[0], 0.6) for b in biz]
        k = 8 if extra is None else 5
        stable = random.Random(f"biz-{bjd}")  # 법정동마다 업종 구성은 달마다 같게
        chosen = {i for i, b in enumerate(biz) if b[0] in ("I56111", "I56220", "G47122")}
        while len(chosen) < k:
            chosen.add(stable.choices(range(len(biz)), weights)[0])
        for bi in sorted(chosen):
            cd, nm = biz[bi]
            for ut, tt, uw in USERS:
                if rng.random() > (0.85 if uw > 1 else 0.45):
                    continue
                ages = [("NA", 1.0)] if ut == "법인" else rng.sample(AGES, 3 if extra is None else 1)
                for age, aw in ages:
                    sexes = ["알수없음"] if ut == "법인" else (["남성", "여성"] if extra is None else [rng.choice(["남성", "여성"])])
                    for sex in sexes:
                        if ut != "법인" and rng.random() < 0.05:
                            age_v, tour_v = "NA", tt
                        else:
                            age_v, tour_v = age, tt
                        for ex, ew in (extra or [(None, 1.0)]):
                            base = 30 * hot * TOUR_BIZ.get(cd, 0.6) * uw * aw * ew * season(m)
                            users = max(1, int(base * rng.lognormvariate(0, 0.7)))
                            cnt = max(users, int(users * rng.uniform(1.0, 1.8)))
                            amt = int(cnt * TICKET.get(cd[0], 20000) * rng.uniform(0.6, 1.5) / 10) * 10
                            row = [f"{y}{m:02d}", dst]
                            if extra is None:
                                row += [city, area]
                            row += [bjd, cd, nm, ut, tour_v]
                            if ex is not None:
                                row.append(ex)
                            row += [age_v, sex, users, cnt, amt]
                            rows.append(row)
    return rows


def _rows(cat, did, ym, rng):
    y, m = int(ym[:4]), int(ym[5:])
    ndays = calendar.monthrange(y, m)[1]
    if did == "1-08":
        return _card_rows(cat, rng, ym, None)
    if did == "1-12":
        return _card_rows(cat, rng, ym, [(w, 1.3 if w in ("금요일", "토요일") else 0.5 if w == "공휴일" else 1.0)
                                          for w in WEEK])
    if did == "1-14":
        return _card_rows(cat, rng, ym, TIMES)
    if did == "1-17":
        rows = []
        for city in ("제주시", "서귀포시"):
            for og in ("내국인 개인", "제주도민 개인", "법인", "외국인", "NA"):
                for cd, nm in _biz(cat):
                    rows.append([f"{y}{m:02d}", city, og, cd, nm,
                                 max(0, int(TOUR_BIZ.get(cd, 0.5) * 40 * rng.lognormvariate(0, 0.8)))])
        return rows
    if did == "1-19":
        rows = []
        for dst, city, area, bjd in _bjd_list():
            ccd = "5011" if city == "제주시" else "5013"
            for i, (mcd, mnm, scd, snm) in enumerate(POS):
                if rng.random() < 0.4:
                    continue
                stores = max(1, int(HOT.get(bjd, 1.0) * 6 * rng.lognormvariate(0, 0.7)))
                use = int(stores * rng.uniform(300, 900))
                rows.append([f"{y}{m:02d}", ccd, city, f"{ccd}{len(rows) % 900 + 100:03d}0", bjd,
                             mcd, mnm, scd, snm, int(use * rng.uniform(12000, 30000)), stores, use])
        return rows
    if did == "3-04":
        rows = []
        for d in range(1, ndays + 1):
            day = datetime(y, m, d)
            dow = "월화수목금토일"[day.weekday()]
            for h in range(6, 24):
                for sid, sname in STATIONS[:5]:
                    for gt in ("승차", "하차"):
                        for uc, w in (("일반", 1.0), ("청소년", 0.25), ("경로", 0.3)):
                            rows.append([day.strftime("%Y%m%d"), dow, f"{h:02d}", sid, sname, gt, uc, "카드",
                                         max(0, int(30 * w * rng.lognormvariate(0, 0.6)))])
        return rows
    if did == "4-11":
        emds = cat.get("4-11")["codes"]["행정동코드 및 행정동명"]
        rows = []
        for d in range(1, ndays + 1):
            day = datetime(y, m, d).strftime("%Y%m%d")
            for t in range(1, 25, 6):
                for code, name in [(e[0], e[1]) for e in emds]:
                    short = name.split()[-1]
                    dst = next((x[0] for x in DISTRICTS if short[:2] in "".join(x[2])), "제주시 중부(서)")
                    for sex in ("남성", "여성"):
                        for age in SKT_AGES[:2]:
                            for resd in ("제주", "그외"):
                                base = 400 * (0.3 if resd == "그외" else 1.0) * HOT.get(short, 1.0)
                                rows.append([day, f"{t:02d}", dst, code, name, sex, age,
                                             f"{base * rng.uniform(0.6, 1.4):.4f}",
                                             f"{base * 0.2 * rng.uniform(0.5, 1.5):.4f}",
                                             f"{base * 0.4 * rng.uniform(0.5, 1.5):.4f}", resd])
        return rows
    if did == "5-02":
        rows = []
        for d in range(1, ndays + 1):
            for ob in OBS:
                t = 15 + 10 * math.sin((m - 4) / 12 * 2 * math.pi) + rng.uniform(-3, 3)
                rows.append([datetime(y, m, d).strftime("%Y%m%d"), ob, round(t, 1), round(t - 4, 1), "0520",
                             round(t + 4, 1), "1430", round(max(0.0, rng.gauss(0, 12)), 1),
                             round(rng.uniform(3, 15), 1), "1310", round(rng.uniform(1, 6), 1),
                             round(rng.uniform(0, 360), 1)])
        return rows
    raise ValueError(f"가상 데이터 미지원: {did}")


def generate(dataset_id: str, months: list, out_dir: Path, seed: int = 7,
             quote_mode: str = "all", index_offset: int = 0) -> list:
    cat = Catalog.load()
    header = [c["name"] for c in cat.columns(dataset_id)]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    order = cat.ids().index(dataset_id)
    files = []
    for i, ym in enumerate(months):
        rng = random.Random(f"{seed}-{dataset_id}-{ym}")
        rows = _rows(cat, dataset_id, ym, rng)
        assert all(len(r) == len(header) for r in rows), dataset_id
        stamp = datetime(2026, 11, 9, 9, 0, 0) + timedelta(seconds=order * 100 + index_offset + i)
        p = out_dir / f"Results_{stamp:%Y%m%d_%H%M%S}.csv"
        buf = io.StringIO()
        buf.write(",".join(f'"{h}"' for h in header) + "\n")
        for r in rows:
            buf.write(_q(r, quote_mode) + "\n")
        p.write_bytes(buf.getvalue().encode("utf-8"))
        files.append(p)
    return files


def month_range(start: str, end: str) -> list:
    y, m = int(start[:4]), int(start[5:])
    out = []
    while f"{y}-{m:02d}" <= end:
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def build_demo(out_dir: Path) -> list:
    """시연 묶음: 1-08·1-14·1-12 12개월(2025-11 1-08 일부러 뺌), 4-11 2개월, 5-02 12개월."""
    out_dir = Path(out_dir)
    year = month_range("2025-07", "2026-06")
    files = []
    m108 = [m for m in year if m != "2025-11"]
    files += generate("1-08", m108[:-1], out_dir)
    files += generate("1-08", m108[-1:], out_dir, quote_mode="first_unquoted", index_offset=len(m108) - 1)
    files += generate("1-14", year, out_dir)
    files += generate("1-12", year, out_dir)
    files += generate("4-11", ["2026-05", "2026-06"], out_dir)
    files += generate("5-02", year, out_dir)
    return files


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        target = Path(__file__).resolve().parent.parent / "demo"
        for old in target.glob("Results_*.csv"):
            old.unlink()
        fs = build_demo(target)
        print(len(fs), "files")
