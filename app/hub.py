"""제주데이터허브 Open API(공개 데이터) 클라이언트. 센터 데이터는 여기로 보내지 않는다.

요청: GET https://open.jejudatahub.net/api/proxy/{데이터키}/{프로젝트키}?{params}  (일일 쿼터 1000)
응답 래퍼 형식은 공개 문서(hwp)로 확인하지 못해, JSON 안의 첫 번째 '객체 배열'을 행으로 읽는 관대한 파서를 쓴다.
키가 없거나 접속이 안 되면 캐시 → 예시(가상) 데이터 순으로 대신한다.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

BASE = "https://open.jejudatahub.net/api/proxy"
HUB = {
    "population": {"key": "Daaa1t3at3tt8a8DD3t55538t35Dab1t", "name": "읍면동 단위 내국인 유동인구",
                   "url": "https://www.jejudatahub.net/data/view/data/583"},
    "bus_station": {"key": "1b1ta1a1ba6t6a1ttt3bD6b1tb1t1D3t", "name": "일일 정류소별 버스 이용자 정보",
                    "url": "https://www.jejudatahub.net/data/view/data/613"},
    "weather": {"key": "1aD5taat1attaa51Db1511b51ab9Da19", "name": "일별 기상 정보",
                "url": "https://www.jejudatahub.net/data/view/data/579"},
}
EMDS = ["한림읍", "애월읍", "구좌읍", "조천읍", "한경면", "추자면", "우도면", "일도1동", "일도2동", "이도1동", "이도2동",
        "삼도1동", "삼도2동", "용담1동", "용담2동", "건입동", "화북동", "삼양동", "봉개동", "아라동", "오라동", "연동",
        "노형동", "외도동", "이호동", "도두동", "대정읍", "남원읍", "성산읍", "안덕면", "표선면", "송산동", "정방동",
        "중앙동", "천지동", "효돈동", "영천동", "동홍동", "서홍동", "대륜동", "대천동", "중문동", "예래동"]
OBS = ["중문", "산천단", "대흘", "강정", "추자도", "우도", "마라도", "유수암", "선흘", "서광", "어리목", "한림", "구좌",
       "성판악", "표선"]


@dataclass
class HubResult:
    rows: list
    source: str
    note: str = ""


def _first_list(obj):
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            found = _first_list(v)
            if found is not None:
                return found
    return None


def _cache_path(cache_dir: Path, kind: str, params: dict) -> Path:
    h = hashlib.sha256(json.dumps([kind, sorted(params.items())], ensure_ascii=False).encode()).hexdigest()[:16]
    return Path(cache_dir) / f"hub_{kind}_{h}.json"


def fetch(kind: str, params: dict, project_key, cache_dir: Path) -> HubResult:
    info = HUB[kind]
    params = {k: v for k, v in params.items() if v not in (None, "")}
    cp = _cache_path(cache_dir, kind, params)
    if project_key:
        try:
            rows, url, pages = [], f"{BASE}/{info['key']}/{urllib.parse.quote(project_key)}?" + \
                urllib.parse.urlencode(params), 0
            while url and pages < 20:
                with urllib.request.urlopen(url, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                rows += _first_list(data) or []
                nxt = data.get("next") or data.get("nextPage") if isinstance(data, dict) else None
                url = nxt if (isinstance(data, dict) and data.get("hasMore") and isinstance(nxt, str)
                              and nxt.startswith("http")) else None
                pages += 1
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            return HubResult(rows, "live", f"제주데이터허브 「{info['name']}」 실시간 조회")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            if cp.exists():
                return HubResult(json.loads(cp.read_text(encoding="utf-8")), "cache",
                                 "허브에 접속하지 못해 이전에 받은 결과를 보여 줍니다.")
    elif cp.exists():
        return HubResult(json.loads(cp.read_text(encoding="utf-8")), "cache", "이전에 받은 결과")
    return HubResult(sample(kind, params), "sample",
                     "예시(가상) 데이터입니다. config.ini에 허브 프로젝트 키를 넣으면 실제 공개 데이터를 불러옵니다.")


def _days(params: dict):
    a = params.get("startDate") or params.get("searchDate") or "20251001"
    b = params.get("endDate") or a
    d0, d1 = datetime.strptime(a, "%Y%m%d"), datetime.strptime(b, "%Y%m%d")
    out = []
    while d0 <= d1 and len(out) < 62:
        out.append(d0)
        d0 += timedelta(days=1)
    return out


def sample(kind: str, params: dict) -> list:
    rng = random.Random(f"hub-{kind}-{sorted(params.items())}")
    rows = []
    for d in _days(params):
        wk = 1.15 if d.weekday() >= 5 else 1.0
        if kind == "population":
            for emd in [params["emd"]] if params.get("emd") else EMDS:
                city = "서귀포시" if emd in EMDS and EMDS.index(emd) >= 26 else "제주시"
                for g in ("남", "여"):
                    for age in ("20대", "40대", "60대"):
                        base = rng.uniform(6000, 22000)
                        rows.append({"baseDate": d.strftime("%Y%m%d"), "city": city, "emd": emd, "gender": g,
                                     "ageGroup": age, "resdPop": int(base), "workPop": int(base * 0.15 * wk),
                                     "visitPop": int(base * 0.6 * wk)})
        elif kind == "bus_station":
            for sid, name in (("4001", "제주국제공항"), ("4002", "제주시외버스터미널"), ("4005", "서귀포버스터미널")):
                for mt in ("승차", "환승"):
                    rows.append({"baseDate": d.strftime("%Y%m%d"), "stationId": sid, "stationName": name,
                                 "moveType": mt, "priceType": "일반", "payType": "카드",
                                 "userCount": int(rng.uniform(300, 2500) * wk)})
        elif kind == "weather":
            for ob in [params["observatoryName"]] if params.get("observatoryName") else OBS:
                t = 15 + 10 * math.sin((d.month - 4) / 12 * 2 * math.pi) + rng.uniform(-3, 3)
                rows.append({"observatoryName": ob, "baseDate": d.strftime("%Y%m%d"),
                             "averageTemperature": round(t, 1), "lowestTemperature": round(t - 4, 1),
                             "highestTemperature": round(t + 4, 1), "dailyRainfall": round(max(0, rng.gauss(0, 10)), 1),
                             "averageWindSpeed": round(rng.uniform(1, 6), 1)})
    return rows
