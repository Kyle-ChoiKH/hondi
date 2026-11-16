"""데이터 카탈로그: 명세서에서 만든 catalog.json 조회."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

CATALOG_PATH = Path(__file__).parent / "data" / "catalog.json"

COUNT_PREF = ["use_cnt", "usage_count", "user_cnt", "user_count", "store_cnt", "cnt"]

ROLLUP = [
    ("bjd", "dstrct_se"), ("bjd_nm", "city_nm"), ("emd_nm", "dstrct_se"), ("emd", "city"),
    ("dstrct_se", "city"), ("eupmyeondong", "city"), ("base_year_month", "quarter"), ("quarter", "year"),
    ("biz_nm", "biz_group"), ("biz_cd", "biz_group"), ("biz_small_nm", "biz_mid_nm"),
    ("biz_small_cd", "biz_mid_cd"), ("age", "age_band"), ("user_type", "user_group"),
]

VIRTUAL_LABEL = {"quarter": "분기", "year": "연도", "biz_group": "업종 대분류",
                 "age_band": "연령 구간", "user_group": "이용자 묶음"}


# 대회 데이터 탭 「제주빅데이터센터_예시데이터 및 컬럼확인용」(2026-11-15 추가)으로 확인한 실제 머리글과 명세서의 차이.
# (파일 자체는 배포 금지라 저장소에 넣지 않고, 다른 컬럼 이름만 여기에 적는다)
REAL_HEADER_FIXES = {
    "1-03": {"rename": {"market_theme": "theme"}},
    "1-06": {"rename": {"market_theme": "theme"}},
    "1-04": {"rename": {"emd": "eupmyeondong"}},
    "1-32": {"rename": {"base_ymd": "base_date"}},
    "3-08": {"add": {"collect_date": "수집일"}},
    "5-01": {"add": {"collect_date": "수집일"}},
    "5-04": {"add": {"certificate_id": "인증번호"}},
}


class Catalog:
    def __init__(self, data: dict):
        self._ds = {d["id"]: d for d in data["datasets"]}
        for did, fix in REAL_HEADER_FIXES.items():
            d = self._ds.get(did)
            if not d:
                continue
            for old, new in fix.get("rename", {}).items():
                for c in d["columns"]:
                    if c["name"] == old:
                        c["name"] = new
                if d.get("time_col") == old:
                    d["time_col"] = new
            for new, ko in fix.get("add", {}).items():
                if not any(c["name"] == new for c in d["columns"]):
                    d["columns"].append({"name": new, "ko": ko, "role": "dim", "note": "실제 파일에 있는 컬럼(명세서에 없음)"})

    @staticmethod
    def load(path: Path = CATALOG_PATH) -> "Catalog":
        with open(path, encoding="utf-8") as f:
            return Catalog(json.load(f))

    def ids(self) -> list:
        return list(self._ds)

    def get(self, did: str) -> dict:
        return self._ds[did]

    def name(self, did: str) -> str:
        return self._ds[did]["name"]

    def columns(self, did: str, include_partition: bool = False) -> list:
        return [c for c in self._ds[did]["columns"]
                if include_partition or c["role"] != "partition"]

    def column(self, did: str, col: str) -> Optional[dict]:
        return next((c for c in self.columns(did) if c["name"] == col), None)

    def label(self, did: str, col: str) -> str:
        c = self.column(did, col)
        if c:
            return c["ko"] or col
        return VIRTUAL_LABEL.get(col, col)

    def identify(self, header: list) -> Optional[str]:
        c = self.candidates(header)
        return c[0] if c else None

    def candidates(self, header: list) -> list:
        """헤더와 가장 잘 맞는 데이터 id 목록. 컬럼 구성이 똑같은 데이터(예: 내국인/중국인)는 여러 개가 나온다."""
        h = {x.strip() for x in header if x and x.strip()}
        best, best_key = [], None
        for did, d in self._ds.items():
            allc = {c["name"] for c in d["columns"]}
            nonpart = {c["name"] for c in d["columns"] if c["role"] != "partition"}
            core = h - {"pt_year", "pt_month"}
            overlap = len(core & nonpart)
            if overlap < max(3, int(len(core) * 0.8)):
                continue
            exact = 1 if core == nonpart else 0
            extra = len(core - allc)
            key = (exact, overlap, -extra, -len(nonpart - core))
            if best_key is None or key > best_key:
                best, best_key = [did], key
            elif key == best_key:
                best.append(did)
        return best

    def is_sensitive(self, did: str) -> bool:
        return bool(self._ds[did].get("sensitive"))

    def time_col(self, did: str) -> Optional[str]:
        return self._ds[did].get("time_col")

    def count_col(self, did: str) -> Optional[str]:
        names = [c["name"] for c in self.columns(did) if c["role"] == "count"]
        for p in COUNT_PREF:
            if p in names:
                return p
        return names[0] if names else None

    def measures(self, did: str) -> list:
        return [c["name"] for c in self.columns(did) if c["role"] in ("count", "amount", "measure")]

    def dims(self, did: str) -> list:
        return [c["name"] for c in self.columns(did) if c["role"] in ("dim", "time")]

    def virtual_sql(self, did: str) -> dict:
        names = {c["name"] for c in self.columns(did)}
        notes = {c["name"]: c.get("note", "") for c in self.columns(did)}
        out = {}
        t = self.time_col(did)
        if t in ("base_year_month", "base_date", "base_ymd"):
            out["year"] = f"substr({t},1,4)"
            out["quarter"] = (f"substr({t},1,4)||'-Q'||cast((cast(substr({t},5,2) as integer)+2)//3 as varchar)")
        if "biz_cd" in names:
            out["biz_group"] = ("case substr(biz_cd,1,1) when 'G' then '소매' when 'H' then '운송' "
                                "when 'I' then '숙박·음식' when 'L' then '임대' when 'N' then '여행·행사' "
                                "when 'R' then '오락·스포츠' when 'S' then '개인서비스' else '기타' end")
        if "age" in names and "10, 20" in notes.get("age", ""):
            out["age_band"] = ("case when age in ('10','20','30') then '10~30대' when age in ('40','50') "
                               "then '40~50대' when age in ('60','70') then '60대 이상' else '미상' end")
        if "user_type" in names:
            out["user_group"] = ("case when user_type in ('중국','일본','동남아','기타외국') then '외국인' "
                                 "else '내국인·법인' end")
        return out

    def allowed_cols(self, did: str) -> set:
        return set(self.dims(did)) | set(self.virtual_sql(did))

    def rollup_parent(self, did: str, col: str) -> Optional[str]:
        avail = self.allowed_cols(did)
        for child, parent in ROLLUP:
            if child == col and parent in avail:
                return parent
        return None
