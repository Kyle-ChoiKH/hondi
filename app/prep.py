"""방문 전 준비: 목적·질문에서 받을 데이터와 기간을 추천하고, 센터 화면 순서대로 '다운로드 주문서'를 만든다.

센터 데이터는 한 번에 1개월씩만 조회·다운로드되므로(게시판 답변) 데이터 × 달 수만큼 내려받아야 한다.
"""
from __future__ import annotations

import calendar
import html
from datetime import date

from .catalog import Catalog

KEYWORDS = [
    (("매출", "상권", "가게", "장사", "업종", "창업", "소비", "카드", "국수", "식당", "카페", "편의점"), ["1-08", "1-14", "1-12", "1-17"]),
    (("외식", "메뉴", "음식점", "포스"), ["1-19"]),
    (("인구", "유동", "사람", "방문객"), ["4-11"]),
    (("버스", "정류소", "교통"), ["3-04"]),
    (("날씨", "기온", "비", "강수"), ["5-02"]),
]
DEFAULT = {"사업계획서": ["1-08", "1-14", "1-12"], "현황자료": ["1-08", "4-11"], "논문": ["1-08"], "자유": ["1-08"]}
WHY = {
    "1-08": "법정동·업종별 월 매출과 고객 구성(도민·관광객·외국인, 연령)을 봅니다.",
    "1-14": "손님이 오는 시간대(오전·점심·오후·저녁·밤)를 봅니다.",
    "1-12": "요일별 붐비는 정도를 봅니다.",
    "1-17": "업종별 매장 수로 경쟁 강도를 봅니다.",
    "1-19": "외식업 소분류(국수·커피 등) 매출과 표본 점포 수를 봅니다.",
    "4-11": "읍면동 시간대별 거주·근무·방문 인구를 봅니다.",
    "3-04": "정류소별 시간대 승하차 인원을 봅니다(원본 반출 가능).",
    "5-02": "일별 기온·강수를 봅니다(원본 반출 가능).",
}


def _shift(y: int, m: int, k: int):
    m0 = y * 12 + (m - 1) + k
    return m0 // 12, m0 % 12 + 1


def recommend(purpose: str, question: str, catalog: Catalog = None, today: date = None, months: int = 12) -> list:
    catalog = catalog or Catalog.load()
    today = today or date.today()
    ids = list(DEFAULT.get(purpose, DEFAULT["자유"]))
    for words, dids in KEYWORDS:
        if any(w in (question or "") for w in words):
            for d in dids:
                if d not in ids:
                    ids.append(d)
    ly, lm = _shift(today.year, today.month, -2)  # 카드 v02 등 월 데이터 최신 달 추정: 오늘의 전전달
    span = [f"{y}-{m:02d}" for y, m in (_shift(ly, lm, -k) for k in range(months - 1, -1, -1))]
    return [{"id": d, "name": catalog.name(d), "why": WHY.get(d, catalog.get(d).get("period_text", "")),
             "months": span if d != "4-11" else span[-2:]} for d in ids if d in catalog.ids()]


def order_sheet(recs: list, conditions: dict, catalog: Catalog = None) -> str:
    catalog = catalog or Catalog.load()
    total = sum(len(r["months"]) for r in recs)
    rows, n = [], 0
    for r in recs:
        cols = {c["name"] for c in catalog.columns(r["id"])}
        cond = ", ".join(f"{catalog.label(r['id'], k)} = {v}" for k, v in conditions.items() if k in cols and v) or "조건 없음(전체)"
        for ym in r["months"]:
            n += 1
            y, m = int(ym[:4]), int(ym[5:])
            last = calendar.monthrange(y, m)[1]
            rows.append(f"<tr><td>{n}</td><td>{html.escape(r['name'])}</td><td>{ym}-01 ~ {ym}-{last:02d}</td>"
                        f"<td>{html.escape(cond)}</td><td class='box'>☐</td></tr>")
    return ("<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>다운로드 주문서</title><style>"
            "body{font-family:'Malgun Gothic',sans-serif;font-size:13px;padding:24px}table{border-collapse:collapse;width:100%}"
            "th,td{border:1px solid #bbb;padding:5px 8px;text-align:left}th{background:#eef2f5}.box{text-align:center;font-size:16px}"
            ".note{background:#f4f7f9;border-left:3px solid #1b6f8f;padding:8px 12px;margin:10px 0}</style></head><body>"
            "<h2>제주빅데이터센터 다운로드 주문서</h2>"
            f"<p class='note'>센터 조회 화면은 한 번에 1개월씩 조회·다운로드됩니다. 아래 순서대로 총 {total}번 내려받으세요. "
            "검색 기간에 해당 달만 넣고, 조건 칸의 값은 컬럼별 입력값에 넣은 뒤 Search → Result → CSV 다운로드를 누릅니다. "
            "여러 달이 필요하면 방문 전에 센터 운영자에게 미리 내려받아 달라고 요청할 수도 있습니다(혼디의 '운영자 요청문').</p>"
            "<table><thead><tr><th>순번</th><th>데이터명</th><th>검색 기간</th><th>조건</th><th>완료</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>"
            "<p>내려받은 파일(Results_날짜_시간.csv)은 이름을 바꾸지 말고 그대로 혼디에 끌어다 놓으면 자동으로 인식·병합됩니다.</p>"
            "</body></html>")


def operator_request(recs: list, name: str, visit_date: str) -> str:
    lines = [f"- {r['name']}: {r['months'][0]} ~ {r['months'][-1]} ({len(r['months'])}개월, 월별 파일)" for r in recs]
    return (f"제주빅데이터센터 담당자님께,\n\n{visit_date} 분석실 이용 예정인 {name or '(이름)'}입니다. "
            "분석에 필요한 아래 데이터를 방문 전에 미리 내려받아 주실 수 있을지 요청드립니다.\n\n"
            + "\n".join(lines) +
            "\n\n조건 없이 전체 법정동(읍면동)으로 받아 주시고, 바탕화면 '요청파일' 폴더에 넣어 주시면 됩니다. "
            "반출이 필요한 결과물은 센터 기준에 맞게 가공해 반출 신청하겠습니다.\n\n감사합니다.")
