"""혼디 로컬 서버: 127.0.0.1에서만 열리는 화면과 JSON API.

실행: python -m app.server   (실행.bat)
"""
from __future__ import annotations

import copy
import json
import mimetypes
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import hub, prep
from .josa import j
from .catalog import Catalog
from .export_form import check_memo, draft, draft_text
from .firewall import Masker, Outbound, Usage
from .guard import LIGHT_TEXT, apply_fix, assess
from .ingest import Workspace
from .llm import make_provider
from .model import Plan
from .narrate import HOWTO, caveats, fmt_value, headline, narrate, narrate_ai, source_line
from .charts import render
from .planner import CARD_LIST, PURPOSES, PlanCache, card_plan, cards_for, fill, needs, plan_from_question, plan_text, validate, _protected
from .report import _mlabel, build_report
from .selfcheck import run as selfcheck
from .session import APP_DIR, DEFAULT_BASE, Config, Session, load_config, sweep_stale
from .synth import build_demo
from .tools import run_step

WEB = APP_DIR / "web"
MAX_BODY = 50 * 1024 * 1024
MAX_UPLOAD = 300 * 1024 * 1024


def out_url(rel: str) -> str:
    return "/out/" + urllib.parse.quote(rel)


class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


class App:
    def __init__(self, cfg: Config, base: Path):
        self.cfg = cfg
        self.base = Path(base)
        self.cat = Catalog.load()
        self.lock = threading.RLock()
        if cfg.auto_delete:
            sweep_stale(self.base)  # 지난번에 창을 닫아 남은 세션 정리
        self.provider = make_provider(cfg.ai_provider, cfg.ai_model, cfg.ai_key)
        if hasattr(self.provider, "effort"):
            self.provider.effort = cfg.ai_effort
        self._new_session()

    def _new_session(self):
        self.session = Session(self.base, self.cfg)
        self.usage = Usage(self.session.usage_path, self.cfg.price_in, self.cfg.price_out, self.cfg.usd_krw,
                           self.cfg.monthly_limit_krw)
        self.outbound = Outbound(self.session.ai_log, self.provider, self.usage)
        self.ws = Workspace(self.cat)
        self.cache = PlanCache()
        self.purpose = "사업계획서"
        self.results = {}
        self.order = []
        self.demo = False
        self._masker = None
        self.file_infos = []
        self.pending = {}

    # ---------- 공통 ----------
    def masker(self):
        if self._masker is None:
            self._masker = Masker(self.ws.dim_values(), protected=_protected(self.ws, self.cat))
        return self._masker

    def datasets(self):
        return [{"id": d.id, "name": d.name, "months": d.months, "missing": d.missing, "rows": d.rows,
                 "files": len(d.files), "sensitive": self.cat.is_sensitive(d.id), **self._explore(d.id)}
                for d in self.ws.datasets()]

    def _explore(self, did):
        """비전문가용 데이터 소개: 명세서 설명을 쉬운 말로, 볼 수 있는 수치·나눠 볼 기준, 바로 누를 질문 카드."""
        cols = self.cat.columns(did)
        measures = [self.cat.label(did, c["name"]) for c in cols if c["role"] in ("count", "amount", "measure")]
        by = [self.cat.label(did, c["name"]) for c in cols if c["role"] in ("dim", "time")
              and not c["name"].endswith(("_cd", "_code"))]
        return {"about": _plain_about(self.cat.get(did).get("description") or "", by, measures),
                "measures": measures, "by": by, "cards": [c.id for c in CARD_LIST if did in c.datasets]}

    def focus_options(self, q=None, b=None):
        """'관심 조건' 고르기 목록: 불러온 데이터의 지역(법정동·읍면동)·업종 값, 자주 나오는 순."""
        def gather(cols):
            out = []
            for did in self.ws.loaded():
                allowed = self.cat.allowed_cols(did)
                for col in cols:
                    if col in allowed:
                        out += [v for v in self.ws.popular(did, col, 500) if v not in out]
            return out
        return {"areas": gather(("bjd", "emd_nm")), "businesses": gather(("biz_nm",))}

    def result_json(self, rid):
        r, a = self.results[rid]["result"], self.results[rid]["assess"]
        did = r.step.dataset
        cols = [{"key": c, "label": self.cat.label(did, c)} for c in r.dims] + \
               [{"key": m, "label": _mlabel(m, self.cat, did)} for m in r.measures]
        rows = []
        for i, row in enumerate(r.rows[:50]):
            cells = [str(row.get(d)) for d in r.dims]
            for m in r.measures:
                if (i, m) in r.masked:
                    cells.append("10 미만(가림)")
                elif m == "값" and row.get("_applied"):
                    cells.append(f"{row.get(m):.1f}%")
                else:
                    cells.append(fmt_value(row.get(m), m if m not in ("값", "change_diff") else r.step.metric, self.cat, did))
            rows.append(cells)
        info = self.results[rid]
        return {"id": rid, "title": r.title, "dataset": self.cat.name(did), "png": out_url(info['png'].name),
                "table": {"columns": cols, "rows": rows, "total": len(r.rows)}, "masked": len(r.masked),
                "light": a.light, "light_text": LIGHT_TEXT[a.light], "kind": a.kind_label, "reasons": a.reasons,
                "fixes": [{"id": f.id, "label": f.label} for f in a.fixes], "narrative": info["narrative"],
                "headline": headline(r, self.cat), "howto": HOWTO.get(r.step.tool, ""),
                "ai_narrative": info.get("ai"), "caveats": caveats(r, self.cat, self.demo),
                "source": source_line(r, self.cat), "step": r.step.to_dict(), "notes": r.notes,
                "edit": self._edit(r)}

    def _edit(self, r):
        """결과 카드에서 조건·기간·지표를 바꿔 다시 실행할 때 고를 수 있는 값."""
        did = r.step.dataset
        flt = [{"key": k, "label": self.cat.label(did, k), "value": v, "options": self.ws.distinct(did, k),
                "top": self.ws.popular(did, k, 8)}
               for k, v in r.step.filters.items() if not isinstance(v, list) and k in self.cat.allowed_cols(did)]
        months = next((d.months for d in self.ws.datasets() if d.id == did), [])
        per = list(r.period) if r.period and r.period[0] else ([months[0], months[-1]] if months else [])
        return {"filters": flt, "period": per, "months": months, "metric": r.step.metric, "tool": r.step.tool,
                "metrics": [{"key": m, "label": self.cat.label(did, m)} for m in self.cat.measures(did)]}

    def _store(self, r):
        a = assess(r, self.cat)
        png = render(r, self.cat, self.session.outbox / f"result_{r.id}.png", demo=self.demo)
        ai = narrate_ai(r, a, self.cat, self.outbound, self.masker(), self.cfg.send_aggregates) \
            if self.cfg.send_aggregates else None
        self.results[r.id] = {"result": r, "assess": a, "png": png, "narrative": narrate(r, self.cat), "ai": ai}
        self.order.append(r.id)
        self.session.activity("result", dataset=r.step.dataset, tool=r.step.tool, light=a.light, result_id=r.id)
        return r.id

    # ---------- API ----------
    def state(self, q=None, b=None):
        return {"purpose": self.purpose, "purposes": PURPOSES, "datasets": self.datasets(),
                "files": self.file_infos[-200:],
                "results": [{"id": i, "title": self.results[i]["result"].title, "light": self.results[i]["assess"].light,
                             "png": out_url(self.results[i]['png'].name)} for i in self.order],
                "settings": self.cfg.public(), "outbound_count": len(self.outbound.records()),
                "usage": self.usage.month(), "demo": self.demo, "session": self.session.id,
                "ai_ready": self.cfg.ai_provider == "openai" and bool(self.cfg.ai_key),
                "external_files": self.external_files()}

    def external_files(self):
        """'폴더에서 찾기'로 제자리에서 읽은 원본 CSV(세션 밖 파일). 퇴실 삭제 대상이 아니므로 알려 준다."""
        folders = {}
        for d in self.ws.datasets():
            for f in d.files:
                p = Path(f)
                demo = self.base.parent / "demo"  # 예시(가상) 데이터는 센터 데이터가 아니므로 안내하지 않는다
                if self.session.dir not in p.parents and demo not in p.parents:
                    folders[str(p.parent)] = folders.get(str(p.parent), 0) + 1
        return [{"folder": k, "count": v} for k, v in sorted(folders.items())]

    def set_purpose(self, q, b):
        p = (b or {}).get("purpose")
        if p not in PURPOSES:
            raise ApiError("목적은 사업계획서·현황자료·논문·자유 중 하나입니다.")
        self.purpose = p
        self.session.activity("purpose", purpose=p)
        return self.state()

    def _add(self, paths, dataset=None):
        infos = self.ws.add_files(paths, dataset)
        self._masker = None
        for i in infos:
            if i.status == "ambiguous":
                self.pending[i.path] = i.candidates
            else:
                self.pending.pop(i.path, None)
        out = [{"name": Path(i.path).name, "dataset": self.cat.name(i.dataset_id) if i.dataset_id else "",
                "month": i.month, "rows": i.rows, "status": i.status, "message": i.message,
                "candidates": [{"id": c, "name": self.cat.name(c)} for c in i.candidates]} for i in infos]
        self.file_infos += out
        self.session.activity("load", files=len(paths), status=",".join(sorted({i.status for i in infos})))
        return {"files": out, "datasets": self.datasets()}

    def files_assign(self, q, b):
        did = (b or {}).get("dataset")
        paths = [p for p, c in self.pending.items() if did in c]
        if not paths:
            raise ApiError("고를 파일이 없습니다.")
        return self._add(paths, did)

    def files_scan(self, q, b):
        folder = (b or {}).get("folder")
        home = Path.home()
        cands = [Path(folder)] if folder else [home / "Downloads", home / "Desktop" / "요청파일",
                                               home / "OneDrive" / "바탕 화면" / "요청파일", home / "Desktop"]
        out = []
        for c in cands:
            if c.is_dir():
                for p in sorted(c.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)[:300]:
                    out.append({"path": str(p), "name": p.name, "folder": str(c), "size": p.stat().st_size,
                                "center": bool(re.fullmatch(r"Results_\d{8}_\d{6}\.csv", p.name))})
        return {"files": out, "folders": [str(c) for c in cands if c.is_dir()]}

    def files_load(self, q, b):
        paths = [Path(p) for p in (b or {}).get("paths", [])]
        if not paths:
            raise ApiError("불러올 파일을 골라 주세요.")
        return self._add(paths)

    def upload(self, name: str, data: bytes):
        safe = re.sub(r"[\\/:*?\"<>|]", "_", Path(name).name) or "upload.csv"
        p = self.session.uploads / f"{int(time.time() * 1000)}_{safe}"
        p.write_bytes(data)
        return self._add([p])

    def demo_load(self, q, b):
        d = self.base.parent / "demo"
        files = sorted(d.glob("Results_*.csv")) if d.exists() else []
        if len(files) < 40:
            for f in files:
                f.unlink()
            files = build_demo(d)
        self.demo = True
        return self._add(files)

    def cards(self, q, b):
        return {"purpose": self.purpose, "cards": cards_for(self.purpose, self.ws, self.cat)}

    def plan(self, q, b):
        b = b or {}
        n0 = len(self.outbound.all_records())
        res = self._plan(b)
        res["trace"] = [{"sent": r.get("user", ""), "input_tokens": r.get("input_tokens", 0),
                         "output_tokens": r.get("output_tokens", 0), "krw": r.get("krw", 0),
                         "error": r.get("error"), "masked": r.get("masked", 0)}
                        for r in self.outbound.all_records()[n0:]]
        return res

    def _plan(self, b):
        if b.get("card"):
            plan, notes = card_plan(b["card"], self.ws, self.cat), []
            missing = validate(plan, self.ws, self.cat)
            if missing:
                raise ApiError("이 카드에 필요한 파일을 먼저 불러와 주세요: " + "; ".join(missing))
        elif (b.get("question") or "").strip():
            try:
                plan, notes = plan_from_question(b["question"].strip(), self.purpose, self.ws, self.cat,
                                                 self.outbound, self.cache)
            except ValueError as e:
                raise ApiError(str(e))
        else:
            raise ApiError("질문을 입력하거나 질문 카드를 골라 주세요.")
        self.session.activity("plan", source=plan.source, count=len(plan.steps))
        return {"plan": plan.to_dict(), "plan_text": plan_text(plan, self.cat), "needs": needs(plan, self.ws, self.cat),
                "notes": notes}

    def run(self, q, b):
        b = b or {}
        plan = fill(Plan.from_dict(b.get("plan") or {}), b.get("values") or {})
        errs = validate(plan, self.ws, self.cat)
        if errs:
            raise ApiError("계획을 실행할 수 없습니다: " + "; ".join(errs))
        left = needs(plan, self.ws, self.cat)
        if left:
            raise ApiError("먼저 고를 값이 있습니다: " + ", ".join(n["label"] for n in left))
        out = []
        for s in plan.steps:
            try:
                r = run_step(self.ws, self.cat, s)
            except ValueError as e:
                raise ApiError(str(e))
            out.append(self.result_json(self._store(r)))
        return {"results": out}

    def fix(self, q, b):
        b = b or {}
        rid = b.get("result_id")
        if rid not in self.results:
            raise ApiError("결과를 찾을 수 없습니다.")
        a = self.results[rid]["assess"]
        f = next((x for x in a.fixes if x.id == b.get("fix_id")), None)
        if not f:
            raise ApiError("고치기 방법을 찾을 수 없습니다.")
        r = apply_fix(self.ws, self.cat, self.results[rid]["result"], f)
        self.session.activity("fix", fix=f.op, result_id=rid)
        return {"results": [self.result_json(self._store(r))], "replaced": rid}

    def rerun(self, q, b):
        b = b or {}
        rid = b.get("result_id")
        if rid not in self.results:
            raise ApiError("결과를 찾을 수 없습니다.")
        step = copy.deepcopy(self.results[rid]["result"].step)
        did = step.dataset
        for k, v in (b.get("filters") or {}).items():
            if k not in self.cat.allowed_cols(did):
                raise ApiError(f"쓸 수 없는 조건입니다: {k}")
            if str(v) not in self.ws.distinct(did, k, limit=5000):
                raise ApiError(f"{j(v, '은')} 불러온 데이터에 없는 값입니다. 목록에서 골라 주세요.")
            step.filters[k] = str(v)
        if "period" in b:
            step.options = dict(step.options or {})
            if b["period"]:
                step.options["period"] = b["period"]
            else:
                step.options.pop("period", None)
        if b.get("metric"):
            if b["metric"] not in self.cat.measures(did):
                raise ApiError("계산할 수 없는 지표입니다.")
            step.metric = b["metric"]
        try:
            r = run_step(self.ws, self.cat, step)
        except ValueError as e:
            raise ApiError(str(e))
        self.session.activity("rerun", result_id=rid, dataset=did, tool=step.tool)
        return {"results": [self.result_json(self._store(r))], "from": rid}

    def bundle(self, q, b):
        """반출 신청 묶음: 보고서·그림·점검 메모·신청서 초안을 ZIP 하나로(센터 반출 신청에 첨부)."""
        b = b or {}
        rs, ass = self._pick(b)
        stamp = time.strftime("%H%M%S")
        out = build_report(self.purpose, rs, ass, self.cat, self.session.outbox / f"bundle_{stamp}",
                           {"title": b.get("title") or ""}, demo=self.demo)
        note = b.get("note") or ""
        d = draft(rs, ass, self.cat, self.purpose, note)
        zp = self.session.outbox / f"반출신청_묶음_{stamp}.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for p in out["pngs"]:
                z.write(p, p.name)
            z.write(out["html"], "보고서.html")
            if out["pdf"]:
                z.write(out["pdf"], "보고서.pdf")
            z.writestr("반출점검메모.html", check_memo(rs, ass, self.cat, self.purpose, note))
            z.writestr("반출신청서_초안.txt", draft_text(d))
            names = z.namelist()
        self.session.activity("bundle", count=len(rs), purpose=self.purpose)
        return {"zip_url": out_url(zp.name), "files": names, "draft": d}

    def dataset_detail(self, q, b):
        did = (q.get("id") or [""])[0]
        if did not in self.ws.loaded():
            raise ApiError("불러오지 않은 데이터입니다.", 404)
        info = next(d for d in self.ws.datasets() if d.id == did)
        con, table, t = self.ws.con, self.ws.table(did), self.cat.time_col(did)
        counts = {}
        if t:
            counts = dict(con.execute(f"select substr({t},1,6), count(*) from {table} group by 1").fetchall())
        months = [{"month": m, "rows": counts.get(m.replace("-", ""), 0), "missing": m in info.missing}
                  for m in sorted(info.months + info.missing)]
        cols = []
        for c in self.cat.columns(did):
            item = {"key": c["name"], "label": self.cat.label(did, c["name"]), "role": c["role"],
                    "note": (c.get("note") or "")[:120]}
            if c["role"] == "dim":
                item["distinct"] = con.execute(f'select count(distinct "{c["name"]}") from {table}').fetchone()[0]
                item["top"] = self.ws.popular(did, c["name"], 5)
            cols.append(item)
        g = self.cat.get(did)
        return {"id": did, "name": info.name, "rows": info.rows, "files": len(info.files),
                "sensitive": self.cat.is_sensitive(did), "provider": g.get("provider", ""),
                "months": months, "columns": cols,
                "cards": [{"id": c.id, "label": c.label, "purpose": c.purpose} for c in CARD_LIST if did in c.datasets]}

    def activity_log(self, q, b):
        p = self.session.activity_path
        ev = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []
        return {"events": ev[-300:]}

    def remove(self, q, b):
        rid = (b or {}).get("result_id")
        if rid in self.results:
            self.order.remove(rid)
            del self.results[rid]
        return self.state()

    def _pick(self, b):
        ids = [i for i in (b or {}).get("result_ids", []) if i in self.results] or list(self.order)
        if not ids:
            raise ApiError("먼저 분석 결과를 만들어 주세요.")
        return [self.results[i]["result"] for i in ids], [self.results[i]["assess"] for i in ids]

    def report(self, q, b):
        rs, ass = self._pick(b)
        folder = self.session.outbox / f"report_{time.strftime('%H%M%S')}"
        out = build_report(self.purpose, rs, ass, self.cat, folder,
                           {"title": (b or {}).get("title") or "", "author": (b or {}).get("author") or ""},
                           demo=self.demo)
        self.session.activity("report", purpose=self.purpose, count=len(rs))
        rel = lambda p: out_url(p.relative_to(self.session.outbox).as_posix())  # noqa: E731
        return {"html_url": rel(out["html"]), "pdf_url": rel(out["pdf"]) if out["pdf"] else None,
                "pngs": [rel(p) for p in out["pngs"]]}

    def export_form(self, q, b):
        rs, ass = self._pick(b)
        d = draft(rs, ass, self.cat, self.purpose, (b or {}).get("note") or "")
        memo = self.session.outbox / f"반출점검메모_{time.strftime('%H%M%S')}.html"
        memo.write_text(check_memo(rs, ass, self.cat, self.purpose, (b or {}).get("note") or ""), encoding="utf-8")
        for f in d["files"]:
            f["url"] = out_url(self.results[f['result_id']]['png'].name)
        return {"draft": d, "memo_url": out_url(memo.name)}

    def outbound_log(self, q, b):
        return {"records": self.outbound.all_records(), "usage": self.usage.month(),
                "limit_krw": self.cfg.monthly_limit_krw, "model": self.cfg.ai_model}

    def settings(self, q, b):
        b = b or {}
        for k in ("send_aggregates", "auto_delete", "keep_results"):
            if k in b:
                setattr(self.cfg, k, bool(b[k]))
        return {"settings": self.cfg.public()}

    def prep(self, q, b):
        b = b or {}
        recs = prep.recommend(b.get("purpose") or self.purpose, b.get("question") or "", self.cat)
        sel = b.get("ids")
        if sel:
            recs = [r for r in recs if r["id"] in sel]
        p = self.session.outbox / f"다운로드주문서_{time.strftime('%H%M%S')}.html"
        p.write_text(prep.order_sheet(recs, b.get("conditions") or {}, self.cat), encoding="utf-8")
        return {"recs": recs, "order_url": out_url(p.name),
                "request_text": prep.operator_request(recs, b.get("name") or "", b.get("visit_date") or "")}

    def hub_preview(self, q, b):
        kind = (q.get("kind") or ["population"])[0]
        if kind not in hub.HUB:
            raise ApiError("알 수 없는 허브 데이터입니다.")
        params = {k: v[0] for k, v in q.items() if k != "kind"}
        r = hub.fetch(kind, params, self.cfg.hub_project_key, self.session.cache_dir)
        key = {"population": "visitPop", "bus_station": "userCount", "weather": "averageTemperature"}[kind]
        series = {}
        for row in r.rows:
            d = str(row.get("baseDate", ""))
            try:
                series.setdefault(d, []).append(float(row.get(key) or 0))
            except (TypeError, ValueError):
                continue
        agg = [{"date": d, "value": round(sum(v) / len(v), 1) if kind == "weather" else round(sum(v))}
               for d, v in sorted(series.items())]
        return {"source": r.source, "note": r.note, "name": hub.HUB[kind]["name"], "url": hub.HUB[kind]["url"],
                "metric": key, "series": agg, "rows": r.rows[:30]}

    def check(self, q, b):
        return {"checks": [c.to_dict() for c in selfcheck(self.cfg, self.base)]}

    def end_session(self, q, b):
        outside = self.external_files()
        summary = self.session.end()
        summary["left_outside"] = outside
        self.session.activity = lambda *a, **k: None
        self._new_session()
        return {"ended": summary, "state": self.state()}


ROUTES = {
    ("GET", "/api/state"): "state", ("POST", "/api/purpose"): "set_purpose",
    ("POST", "/api/files/scan"): "files_scan", ("POST", "/api/files/load"): "files_load",
    ("POST", "/api/files/assign"): "files_assign",
    ("POST", "/api/demo"): "demo_load", ("GET", "/api/cards"): "cards", ("POST", "/api/plan"): "plan",
    ("POST", "/api/run"): "run", ("POST", "/api/fix"): "fix", ("POST", "/api/remove"): "remove",
    ("POST", "/api/rerun"): "rerun", ("POST", "/api/bundle"): "bundle", ("GET", "/api/dataset"): "dataset_detail",
    ("GET", "/api/activity"): "activity_log", ("GET", "/api/focus-options"): "focus_options",
    ("POST", "/api/report"): "report", ("POST", "/api/export-form"): "export_form",
    ("GET", "/api/outbound"): "outbound_log", ("POST", "/api/settings"): "settings", ("POST", "/api/prep"): "prep",
    ("GET", "/api/hub"): "hub_preview", ("GET", "/api/selfcheck"): "check", ("POST", "/api/session/end"): "end_session",
}


def _plain_about(desc: str, by: list, measures: list) -> str:
    """명세서 설명 첫 줄을 '…을 알 수 있어요'로. 설명이 없으면 컬럼으로 만든다."""
    first = next((x.strip(" -	") for x in desc.splitlines() if x.strip(" -	")), "")
    if first.endswith(("제공합니다.", "제공합니다")):
        return first.rsplit("제공합니다", 1)[0].rstrip() + " 알 수 있어요."
    if first:
        return first
    return f"{', '.join(by[:4])}별로 {', '.join(measures[:3])}을(를) 볼 수 있어요." if measures else ""


mimetypes.add_type("font/woff2", ".woff2")  # Windows 레지스트리에 없을 때가 많다


def _safe_file(root: Path, rel: str):
    rel = urllib.parse.unquote(rel)
    if ".." in Path(rel).parts or rel.startswith(("/", "\\")) or ":" in rel:
        return None
    p = (root / rel).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        server_version = "Hondi/1.0"

        def log_message(self, fmt, *args):
            pass

        def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

        def _file(self, p):
            if not p:
                return self._send(404, "찾을 수 없습니다".encode(), "text/plain; charset=utf-8")
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            self._send(200, p.read_bytes(), ctype)

        def _handle(self, method):
            u = urllib.parse.urlsplit(self.path)
            path = u.path
            # 이 PC의 혼디 화면에서 온 요청만 받는다(다른 웹사이트의 위조 요청·DNS 재바인딩 차단)
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if (self.headers.get("Host") or "").lower() not in hosts:
                return self._json(403, {"error": "허용되지 않은 주소입니다."})
            if method == "POST":
                origin = (self.headers.get("Origin") or "").lower()
                if origin and origin not in {f"http://{h}" for h in hosts}:
                    return self._json(403, {"error": "다른 사이트에서 온 요청은 받지 않습니다."})
                ctype = (self.headers.get("Content-Type") or "").lower()
                if path != "/api/files/upload" and not ctype.startswith("application/json"):
                    return self._json(415, {"error": "요청 형식이 올바르지 않습니다."})
            if method == "GET" and not path.startswith("/api/"):
                if path in ("/", "/index.html"):
                    return self._file(WEB / "index.html" if (WEB / "index.html").exists() else None)
                if path.startswith("/web/"):
                    return self._file(_safe_file(WEB, path[5:]))
                if path.startswith("/out/"):
                    return self._file(_safe_file(app.session.outbox, path[5:]))
                return self._file(None)
            name = ROUTES.get((method, path))
            if path == "/api/files/upload" and method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_UPLOAD:
                    return self._json(413, {"error": "파일이 너무 큽니다(300MB 초과)."})
                data = self.rfile.read(n)
                fname = urllib.parse.unquote(self.headers.get("X-Filename") or "upload.csv")
                with app.lock:
                    return self._json(200, app.upload(fname, data))
            if not name:
                return self._json(404, {"error": "없는 주소입니다."})
            body = None
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    return self._json(413, {"error": "요청이 너무 큽니다."})
                raw = self.rfile.read(n) if n else b""
                try:
                    body = json.loads(raw.decode("utf-8")) if raw else {}
                except ValueError:
                    return self._json(400, {"error": "요청 형식이 올바르지 않습니다."})
            q = urllib.parse.parse_qs(u.query)
            with app.lock:
                return self._json(200, getattr(app, name)(q, body))

        def _wrap(self, method):
            try:
                self._handle(method)
            except ApiError as e:
                self._json(e.code, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self._json(500, {"error": f"처리 중 오류가 났습니다: {e}"})

        def do_GET(self):
            self._wrap("GET")

        def do_POST(self):
            self._wrap("POST")

    return H


def create_app(cfg: Config, base: Path) -> App:
    return App(cfg, base)


class _Server(ThreadingHTTPServer):
    # Windows에서 SO_REUSEADDR는 같은 포트 중복 바인딩을 허용한다 → 끄고 독점 사용으로 연다.
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        import socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(app: App, port: int) -> ThreadingHTTPServer:
    return _Server(("127.0.0.1", port), make_handler(app))


_HANDLERS = []


def _on_console_close(fn):
    """Windows 콘솔 창 닫기·로그오프·종료 때 세션을 지운다(최선 노력; 못 지우면 다음 실행 때 정리)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
        def handler(event):
            if event in (2, 5, 6):  # CTRL_CLOSE / LOGOFF / SHUTDOWN
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    pass
            return False
        _HANDLERS.append(handler)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)
    except Exception:  # noqa: BLE001
        pass


def serve(cfg: Config, open_browser: bool = True):
    app = create_app(cfg, DEFAULT_BASE)
    httpd = None
    for port in [cfg.port] + list(range(8766, 8776)):
        try:
            httpd = make_server(app, port)
            break
        except OSError:
            continue
    if httpd is None:
        print("사용할 수 있는 포트가 없습니다(8765~8775).")
        sys.exit(1)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"혼디가 실행 중입니다: {url}\n이 창을 닫으면 혼디가 종료됩니다.")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    _on_console_close(lambda: app.session.end() if cfg.auto_delete else None)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if cfg.auto_delete:
            app.session.end()


if __name__ == "__main__":
    serve(load_config(APP_DIR / "config.ini"), open_browser="--no-browser" not in sys.argv)
