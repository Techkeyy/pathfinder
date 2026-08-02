"""The end-to-end pipeline, independent of where inputs come from.

``analyze`` takes changed models plus a way to look up lineage and returns a full
:class:`PathfinderReport`. The CLI wires real sources (GitHub + DataHub) or a
fixture into it; tests can pass plain callables.
"""

from __future__ import annotations

from typing import Callable

from .change_extractor import diff_model
from .classifier import build_assessment
from .llm import LLM
from .models import DownstreamAsset, PathfinderReport, PullRequestRef
from .remediation import draft

# dataset name -> its downstream blast radius
LineageProvider = Callable[[str], list[DownstreamAsset]]


def analyze(
    pairs: list[tuple[str, str, str]],
    lineage: LineageProvider,
    pr: PullRequestRef,
    llm: LLM | None = None,
    dialect: str | None = None,
) -> PathfinderReport:
    """pairs = [(dataset, before_sql, after_sql), ...]."""
    report = PathfinderReport(pr=pr)
    for dataset, before_sql, after_sql in pairs:
        changes = diff_model(dataset, before_sql, after_sql, dialect=dialect)
        if not changes:
            continue
        downstream = lineage(dataset) or []
        for change in changes:
            assessment = build_assessment(change, downstream)
            report.assessments.append(assessment)
            rem = draft(assessment, llm)
            if rem is not None:
                report.remediations.append(rem)
    return report
