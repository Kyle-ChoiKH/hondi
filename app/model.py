"""혼디 공용 데이터 구조."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Step:
    tool: str
    dataset: str
    metric: str
    by: list = field(default_factory=list)
    filters: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"tool": self.tool, "dataset": self.dataset, "metric": self.metric,
                "by": list(self.by), "filters": dict(self.filters), "options": dict(self.options)}

    @staticmethod
    def from_dict(d: dict) -> "Step":
        return Step(tool=str(d.get("tool", "")), dataset=str(d.get("dataset", "")),
                    metric=str(d.get("metric", "")), by=list(d.get("by") or []),
                    filters=dict(d.get("filters") or {}), options=dict(d.get("options") or {}))


@dataclass
class Plan:
    purpose: str
    steps: list
    ask: Optional[str] = None
    source: str = "card"

    def to_dict(self) -> dict:
        return {"purpose": self.purpose, "steps": [s.to_dict() for s in self.steps],
                "ask": self.ask, "source": self.source}

    @staticmethod
    def from_dict(d: dict) -> "Plan":
        return Plan(purpose=str(d.get("purpose", "자유")),
                    steps=[Step.from_dict(s) for s in (d.get("steps") or [])],
                    ask=d.get("ask"), source=str(d.get("source", "ai")))


@dataclass
class Result:
    id: str
    title: str
    step: Step
    dims: list
    measures: list
    rows: list
    agg_kind: str
    period: tuple
    masked: set = field(default_factory=set)
    notes: list = field(default_factory=list)


@dataclass
class Fix:
    id: str
    label: str
    op: str
    params: dict = field(default_factory=dict)


@dataclass
class Assessment:
    light: str
    reasons: list
    fixes: list
    kind_label: str
