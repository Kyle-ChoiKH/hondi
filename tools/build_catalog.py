"""제주빅데이터센터 데이터 명세서(xlsx) → app/data/catalog.json

사용: python tools/build_catalog.py <데이터명세서.xlsx> app/data/catalog.json
명세서는 외부 공개 자료(반출 정책 10쪽)이므로 결과물을 저장소에 포함한다.
"""
import json
import re
import sys

import openpyxl

PARTITION = {"pt_year", "pt_month"}
TIME = {"base_year_month", "base_date", "base_ymd"}
COUNT_EXACT = {"user_cnt", "use_cnt", "store_cnt", "user_count", "usage_count", "cnt",
               "store_sale_cnt", "sale_count", "count"}
AMOUNT_EXACT = {"use_amt", "usage_cost", "usage_amount", "usage_amt", "sale_amt", "amount",
                "store_sale_amt", "fee_amount", "sale_amount", "unit_price"}


def role_of(name: str, dtype: str) -> str:
    n = name.strip().lower()
    t = (dtype or "").upper()
    if n in PARTITION:
        return "partition"
    if n in TIME:
        return "time"
    if n.endswith("_pop_cnt"):
        return "measure"
    if n in COUNT_EXACT or n.endswith("_cnt") or n.endswith("_count"):
        return "count"
    if n in AMOUNT_EXACT or n.endswith("_amt") or n.endswith("_amount") or n.endswith("_price") \
            or n.startswith("amount_per"):
        return "amount"
    if t in ("DOUBLE", "FLOAT", "DECIMAL"):
        return "measure"
    return "dim"


def cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def is_int(s: str) -> bool:
    return bool(re.fullmatch(r"\d+", s))


def parse_list(ws):
    info, cat = {}, None
    for row in ws.iter_rows(values_only=True):
        r = [cell(c) for c in row]
        if len(r) < 5 or not re.fullmatch(r"\d-\d\d|-", r[0] or "x"):
            continue
        if r[1]:
            cat = r[1].split("/")[0].strip()
        if r[0] == "-":
            continue
        info[r[0]] = {"category": cat, "export": r[3], "provider": r[4]}
    return info


def parse_sheet(ws):
    rows = [[cell(c) for c in row] for row in ws.iter_rows(values_only=True)]
    desc, columns, codes = "", [], {}
    hdr = None
    for i, r in enumerate(rows):
        if r and r[0] == "설명":
            desc = next((x for x in r[1:] if x), "")
        if r and r[0] == "No" and len(r) > 2 and ("컬럼" in r[1] or "Column" in r[1]):
            hdr = i
            break
    if hdr is not None:
        for r in rows[hdr + 1:]:
            if not r or not is_int(r[0]) or len(r) < 3 or not r[1]:
                break
            name = r[1].strip()
            dtype = r[3] if len(r) > 3 else ""
            columns.append({"name": name, "ko": r[2].strip() if len(r) > 2 else "",
                            "type": dtype, "example": r[4] if len(r) > 4 else "",
                            "note": next((x for x in r[5:] if x), "") if len(r) > 5 else "",
                            "role": role_of(name, dtype)})
    for i, r in enumerate(rows):
        for c, v in enumerate(r):
            if not v.startswith("[참고"):
                continue
            title = re.sub(r"^\[참고\d*\]\s*", "", v).strip()
            vals = []
            for r2 in rows[i + 2:]:
                if c >= len(r2) or not is_int(r2[c]):
                    break
                parts = [x for x in r2[c + 1:c + 4] if x]
                if parts:
                    vals.append(parts if len(parts) > 1 else parts[0])
            if vals:
                codes[title] = vals
    return desc, columns, codes


def main(src, out):
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    info = parse_list(wb[wb.sheetnames[0]])
    datasets = []
    for ws in wb.worksheets[1:]:
        m = re.match(r"(\d-\d\d)\s+(.*)$", ws.title.strip())
        if not m:
            continue
        did, name = m.group(1), m.group(2).strip()
        desc, columns, codes = parse_sheet(ws)
        if not columns:
            continue
        meta = info.get(did, {})
        period = re.search(r"기간:\s*([^/]+)", desc)
        time_col = next((c["name"] for c in columns if c["role"] == "time"), None)
        grain = {"base_year_month": "month", "base_date": "day", "base_ymd": "day"}.get(time_col, "snapshot")
        datasets.append({
            "id": did, "name": name, "category": meta.get("category", ""),
            "provider": meta.get("provider", ""), "export": meta.get("export", ""),
            "sensitive": meta.get("export", "") == "불가능",
            "period_text": period.group(1).strip() if period else "",
            "description": desc, "time_col": time_col, "grain": grain,
            "columns": columns, "codes": codes,
        })
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source": "제주빅데이터센터 데이터 명세서", "datasets": datasets}, f,
                  ensure_ascii=False, indent=1)
    print("datasets", len(datasets))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
