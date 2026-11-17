"""결과 그림(PNG). 반출 정책상 그림파일 형태가 권장되므로 모든 그림에 출처를 넣는다."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .catalog import Catalog  # noqa: E402
from .model import Result  # noqa: E402
from .narrate import _ym, caveats, fmt_value, source_line  # noqa: E402

_FONTS = Path(__file__).parent / "data" / "fonts"  # 화면과 같은 Pretendard(SIL OFL)를 함께 넣는다
for _f in sorted(_FONTS.glob("*.otf")):
    try:
        font_manager.fontManager.addfont(str(_f))
    except Exception:  # 글꼴 파일이 깨져도 그림은 기본 글꼴로 그린다
        pass
_FONT = next((n for n in ("Pretendard", "Malgun Gothic", "NanumGothic", "AppleGothic")
              if any(f.name == n for f in font_manager.fontManager.ttflist)), None)
if _FONT:
    plt.rcParams["font.family"] = _FONT
plt.rcParams["axes.unicode_minus"] = False

INK, SUB, GRID = "#191f28", "#6b7684", "#eef0f3"
C1, C2, HATCH = "#3182f6", "#ff8a3d", "#c9cfd6"
TIME_DIMS = {"base_year_month", "base_date", "quarter", "year", "time", "week", "base_hour"}


def _label(r: dict, dims: list) -> str:
    vals = [r.get(d) for d in dims]
    if len(vals) == 1 and dims[0] == "base_year_month":
        return _ym(vals[0])
    return " ".join(str(v) for v in vals)


def month_slots(rows: list, dim: str) -> list:
    """시간 축 칸 목록. 기준년월이면 빠진 달도 칸으로 넣어(행 번호 None) 선이 끊기게 한다."""
    keys = [str(r.get(dim)) for r in rows]
    if dim != "base_year_month" or not keys or not all(len(k) == 6 and k.isdigit() for k in keys):
        return [(k, i) for i, k in enumerate(keys)]
    pos = {k: i for i, k in enumerate(keys)}
    y, m = int(keys[0][:4]), int(keys[0][4:])
    last, out = keys[-1], []
    while True:
        k = f"{y}{m:02d}"
        out.append((k, pos.get(k)))
        if k >= last or len(out) > 600:
            return out
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _pick_measure(result: Result) -> str:
    for m in result.measures:
        if m != "rank":
            return m
    return result.measures[0]


def render(result: Result, cat: Catalog, path: Path, numbers: bool = True, demo: bool = False) -> Path:
    path = Path(path)
    _m = lambda x: result.step.metric if x == "change_diff" else x  # 증감값의 단위는 원래 지표(금액이면 원, 건수면 건)
    path.parent.mkdir(parents=True, exist_ok=True)
    numbers = numbers and "no_numbers" not in result.notes
    did = result.step.dataset
    fig, ax = plt.subplots(figsize=(10.67, 6), dpi=150)
    fig.patch.set_facecolor("white")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=SUB, length=0, pad=6)
    ax.grid(axis="y" if result.dims and result.dims[0] in TIME_DIMS else "x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)

    t = result.step.tool
    rows = result.rows
    if not rows:
        ax.text(0.5, 0.5, "조건에 맞는 데이터가 없습니다", ha="center", va="center", fontsize=16, color=SUB,
                transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
    elif t == "profile":
        ax.axis("off")
        cells = [[r["지표"], "10 미만(가림)" if (i, "값") in result.masked else
                  (f"{r['값']:.1f}%" if r.get("_applied") else fmt_value(r["값"], result.step.metric, cat, did))]
                 for i, r in enumerate(rows)]
        tb = ax.table(cellText=cells, colLabels=["지표", "값"], loc="center", cellLoc="left", colWidths=[0.6, 0.3])
        tb.auto_set_font_size(False)
        tb.set_fontsize(12)
        tb.scale(1, 1.8)
    elif t == "compare":
        ma, mb = result.measures[0], result.measures[1]
        labels = [_label(r, result.dims) for r in rows]
        x = range(len(rows))
        w = 0.4
        fa = ", ".join(str(v) for v in result.step.filters.values()) or "가"
        fb = ", ".join(str(v) for v in (result.step.options.get("filters_b") or {}).values()) or "나"
        for k, (m, color, name, off) in enumerate(((ma, C1, fa, -w / 2), (mb, C2, fb, w / 2))):
            vals = [0 if (i, m) in result.masked else (r.get(m) or 0) for i, r in enumerate(rows)]
            bars = ax.bar([i + off for i in x], vals, w, color=color, label=name)
            for i, b in enumerate(bars):
                if (i, m) in result.masked:
                    ax.text(b.get_x() + w / 2, 0, "가림", ha="center", va="bottom", fontsize=8, color=SUB)
                elif numbers:
                    ax.text(b.get_x() + w / 2, b.get_height(), fmt_value(vals[i], _m(m), cat, did), ha="center",
                            va="bottom", fontsize=7, color=INK)
        ax.set_xticks(list(x), labels, rotation=30 if len(rows) > 6 else 0, ha="right" if len(rows) > 6 else "center")
        ax.legend(frameon=False)
    else:
        m = _pick_measure(result)
        is_time = result.dims and result.dims[0] in TIME_DIMS and t in ("trend", "yoy", "describe")
        if t == "describe":
            m = "mean"
        if is_time:
            slots = month_slots(rows, result.dims[0])
            labels = [_label(rows[i], result.dims) if i is not None else _label({result.dims[0]: k}, result.dims[:1])
                      for k, i in slots]
            vals = [None if i is None or (i, m) in result.masked else rows[i].get(m) for k, i in slots]
            xs = list(range(len(slots)))
            ax.plot(xs, [float("nan") if v is None else v for v in vals],
                    color=C1, linewidth=2.2, marker="o", markersize=5)
            for x, v, (k, i) in zip(xs, vals, slots):
                if i is None:
                    ax.axvspan(x - 0.3, x + 0.3, color=HATCH, alpha=0.25)
                    ax.text(x, ax.get_ylim()[0], "자료 없음", ha="center", va="bottom", fontsize=8, color=SUB)
                elif v is None:
                    ax.axvspan(x - 0.3, x + 0.3, color=HATCH, alpha=0.4)
                    ax.text(x, ax.get_ylim()[0], "가림", ha="center", va="bottom", fontsize=8, color=SUB)
                elif numbers:
                    ax.annotate(fmt_value(v, _m(m), cat, did), (x, v), textcoords="offset points", xytext=(0, 7),
                                ha="center", fontsize=7, color=INK)
            ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: fmt_value(y, _m(m), cat, did)))
            step = max(1, len(xs) // 12)
            ax.set_xticks(xs[::step], labels[::step], rotation=30 if len(xs) > 8 else 0)
            if m.endswith("_pct"):
                ax.axhline(0, color=SUB, linewidth=0.8)
        else:
            order = list(range(len(rows)))
            if t != "rank" and not (result.dims and result.dims[0] in TIME_DIMS):
                order.sort(key=lambda i: (rows[i].get(m) or 0))
            elif t != "rank":
                order.reverse()
            else:
                order.reverse()
            order = order[-20:]
            labels = [_label(rows[i], result.dims) for i in order]
            vals = [0 if (i, m) in result.masked else (rows[i].get(m) or 0) for i in order]
            colors = [C2 if (m == "change_diff" and v < 0) else C1 for v in vals]
            bars = ax.barh(range(len(order)), vals, color=colors, height=0.6)
            span = max([abs(v) for v in vals] + [1])
            for k, (i, b) in enumerate(zip(order, bars)):
                if (i, m) in result.masked:
                    ax.barh(k, span * 0.04, color="none", edgecolor=HATCH, hatch="///", height=0.6)
                    ax.text(span * 0.05, k, "10 미만(가림)", va="center", fontsize=9, color=SUB)
                elif numbers:
                    ax.text(b.get_width() + span * 0.01, k, fmt_value(vals[k], _m(m), cat, did), va="center",
                            fontsize=9, color=INK)
            ax.set_yticks(range(len(order)), labels)
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt_value(v, _m(m), cat, did)))
            if not numbers:
                ax.set_xticks([])
            ax.set_xlim(min(0, min(vals) * 1.15), span * 1.18)
        if not numbers:
            ax.set_yticks([]) if is_time else None
    ax.set_title(result.title, loc="left", fontsize=15, color=INK, pad=16, fontweight="bold")
    foot = source_line(result, cat)
    cv = caveats(result, cat, demo)
    if cv:
        foot += "  ·  " + cv[0]
    fig.text(0.01, 0.01, foot, fontsize=8, color=SUB)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path
