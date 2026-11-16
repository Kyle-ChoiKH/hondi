"""센터에서 내려받은 CSV를 인식·적재·병합한다(DuckDB in-memory, 디스크에 사본을 만들지 않음)."""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from .catalog import Catalog

TYPE_SQL = {"count": "BIGINT", "amount": "BIGINT", "measure": "DOUBLE"}


@dataclass
class FileInfo:
    path: str
    dataset_id: str | None
    month: str
    rows: int
    status: str
    message: str = ""
    candidates: list = field(default_factory=list)


@dataclass
class DatasetInfo:
    id: str
    name: str
    months: list
    missing: list
    rows: int
    files: list = field(default_factory=list)


def _months_between(a: str, b: str) -> list:
    y, m = int(a[:4]), int(a[5:])
    out = []
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def read_header(path: Path) -> list:
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if any(x.strip() for x in row):
                return [x.strip() for x in row]
    return []


class Workspace:
    def __init__(self, catalog: Catalog):
        self.cat = catalog
        self.con = duckdb.connect(":memory:")
        self._hashes = {}
        self._files = {}

    def table(self, did: str) -> str:
        return "ds_" + did.replace("-", "_")

    def loaded(self) -> list:
        return sorted(self._files)

    def _ensure_table(self, did: str):
        cols = ", ".join(f'"{c["name"]}" {TYPE_SQL.get(c["role"], "VARCHAR")}' for c in self.cat.columns(did))
        self.con.execute(f"create table if not exists {self.table(did)} ({cols}, _file varchar)")

    def add_files(self, paths: list, dataset: str = None) -> list:
        """dataset을 주면 그 데이터로 불러온다(컬럼 구성이 같은 데이터 중 사용자가 고른 경우)."""
        out = []
        for p in paths:
            p = Path(p)
            try:
                out.append(self._add(p, dataset))
            except Exception as e:  # noqa: BLE001 - 파일 하나의 오류가 전체를 막지 않게
                out.append(FileInfo(str(p), None, "", 0, "error", f"읽을 수 없는 파일입니다: {e}"))
        return out

    def _add(self, p: Path, dataset: str = None) -> FileInfo:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest in self._hashes:
            return FileInfo(str(p), self._hashes[digest], "", 0, "duplicate",
                            "같은 파일이 이미 들어와 있어 한 번만 반영했습니다.")
        header = read_header(p)
        cands = self.cat.candidates(header)
        if dataset:
            if dataset not in self.cat.ids():
                raise ValueError(f"없는 데이터입니다: {dataset}")
            cands = [dataset]
        if len(cands) > 1:
            return FileInfo(str(p), None, "", 0, "ambiguous",
                            "컬럼 구성이 같은 데이터가 여러 개입니다: " + ", ".join(self.cat.name(c) for c in cands) +
                            " — 어느 데이터인지 골라 주세요.", cands)
        did = cands[0] if cands else None
        if not did:
            return FileInfo(str(p), None, "", 0, "unknown",
                            "어떤 센터 데이터인지 알 수 없는 파일입니다. 센터 조회 결과 CSV인지 확인해 주세요.")
        known = {c["name"] for c in self.cat.columns(did, include_partition=True)}
        extra = [h for h in header if h not in known]
        self._ensure_table(did)
        cols = self.cat.columns(did)
        sel = []
        for c in cols:
            if c["name"] in header:
                typ = TYPE_SQL.get(c["role"])
                expr = f'"{c["name"]}"'
                if typ == "BIGINT":
                    expr = f"try_cast(try_cast(replace({expr}, ',', '') as double) as bigint)"
                elif typ == "DOUBLE":
                    expr = f"try_cast(replace({expr}, ',', '') as double)"
                else:  # 정류소명 등 뒤에 공백이 붙어 오는 값이 있어 앞뒤 공백을 지운다
                    expr = f"nullif(trim({expr}), '')"
                sel.append(expr)
            else:
                sel.append("null")
        src = ("read_csv(?, header=true, all_varchar=true, delim=',', quote='\"', escape='\"', "
               "nullstr='NA', skip=0, null_padding=true, strict_mode=false)")
        before = self.con.execute(f"select count(*) from {self.table(did)}").fetchone()[0]
        self.con.execute(f"insert into {self.table(did)} select {', '.join(sel)}, ? from {src}",
                         [str(p), str(p)])
        rows = self.con.execute(f"select count(*) from {self.table(did)}").fetchone()[0] - before
        # 바이트는 달라도(다시 저장·줄바꿈 차이) 내용이 이미 불러온 행과 모두 같으면 두 번 더하지 않는다
        names = ", ".join(f'"{c["name"]}"' for c in cols)
        fresh = self.con.execute(f"select count(*) from (select {names} from {self.table(did)} where _file = ? "
                                 f"except all select {names} from {self.table(did)} where _file <> ?)",
                                 [str(p), str(p)]).fetchone()[0]
        if rows and fresh == 0:
            self.con.execute(f"delete from {self.table(did)} where _file = ?", [str(p)])
            self._hashes[digest] = did
            return FileInfo(str(p), did, "", 0, "duplicate",
                            "이미 불러온 파일과 내용이 같아(같은 달·같은 조건) 한 번만 반영했습니다.")
        overlap = rows - fresh
        t = self.cat.time_col(did)
        month = ""
        if t:
            ms = self.con.execute(f"select distinct substr({t},1,6) from {self.table(did)} where _file = ? "
                                  f"and {t} is not null order by 1", [str(p)]).fetchall()
            month = ",".join(f"{m[0][:4]}-{m[0][4:6]}" for m in ms if m[0])
        self._hashes[digest] = did
        self._files.setdefault(did, []).append(str(p))
        notes = [f"모르는 컬럼 {', '.join(extra)} 무시"] if extra else []
        if overlap:
            notes.append(f"이미 불러온 파일과 같은 행이 {overlap}개 있습니다 — 같은 조건으로 두 번 받았다면 합계가 겹칠 수 있습니다")
        msg = "; ".join(notes)
        return FileInfo(str(p), did, month, rows, "ok", msg)

    def datasets(self) -> list:
        out = []
        for did in self.loaded():
            t = self.cat.time_col(did)
            rows = self.con.execute(f"select count(*) from {self.table(did)}").fetchone()[0]
            months, missing = [], []
            if t:
                ms = self.con.execute(f"select distinct substr({t},1,6) m from {self.table(did)} "
                                      f"where {t} is not null order by m").fetchall()
                months = [f"{m[0][:4]}-{m[0][4:6]}" for m in ms if m[0] and len(m[0]) >= 6]
                if months:
                    missing = [m for m in _months_between(months[0], months[-1]) if m not in months]
            out.append(DatasetInfo(did, self.cat.name(did), months, missing, rows, list(self._files[did])))
        return out

    def distinct(self, did: str, col: str, limit: int = 500) -> list:
        if col not in self.cat.allowed_cols(did):
            raise ValueError(f"알 수 없는 컬럼: {col}")
        expr = self.cat.virtual_sql(did).get(col, f'"{col}"')
        rows = self.con.execute(f"select distinct {expr} v from {self.table(did)} where {expr} is not null "
                                f"order by v limit {int(limit)}").fetchall()
        return [str(r[0]) for r in rows]

    def popular(self, did: str, col: str, n: int = 12) -> list:
        """행이 많은 값부터(값 고르기 칩용). 같은 수면 가나다순."""
        if col not in self.cat.allowed_cols(did):
            raise ValueError(f"알 수 없는 컬럼: {col}")
        expr = self.cat.virtual_sql(did).get(col, f'"{col}"')
        rows = self.con.execute(f"select {expr} v, count(*) c from {self.table(did)} where {expr} is not null "
                                f"group by 1 order by c desc, v limit {int(n)}").fetchall()
        return [str(r[0]) for r in rows]

    def dim_values(self) -> dict:
        out = {}
        for did in self.loaded():
            for c in self.cat.columns(did):
                if c["role"] != "dim":
                    continue
                vals = self.con.execute(f'select distinct "{c["name"]}" from {self.table(did)} '
                                        f'where "{c["name"]}" is not null limit 5000').fetchall()
                out.setdefault(c["name"], set()).update(str(v[0]) for v in vals)
        return out

    def clear(self):
        for did in self.loaded():
            self.con.execute(f"drop table if exists {self.table(did)}")
        self._hashes.clear()
        self._files.clear()
