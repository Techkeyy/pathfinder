"""Decide how dangerous each change is, deterministically.

Rules decide severity; the LLM (optional, see :mod:`pathfinder.llm`) only writes
prose. Keeping the *decision* deterministic means Pathfinder gives the same
verdict every run, works with no API key, and is trivial to unit-test, exactly
what a data team needs from a merge gate.

Severity model
--------------
* ``ADD_COLUMN`` .................... 🟢 safe (additive)
* structural (rename/drop/type):
    - a dashboard / chart / ML feature / ML model / deployment that consumes it
      within 2 hops ............... 🔴 breaking (they bind to column names/schema)
    - a direct (1-hop) dataset/job .. 🔴 breaking
    - a deeper dataset/job ......... 🟠 partial (an intermediate model may absorb it)
* filter / logic change ............ 🟠 partial (row-set or values shift silently)

A production asset never *lowers* severity; it raises the asset's priority in
the report so the on-call owner sees it first.
"""

from __future__ import annotations

from .models import (
    AssetVerdict,
    ChangeType,
    ColumnChange,
    DownstreamAsset,
    EntityType,
    ImpactAssessment,
    Severity,
)

_SCHEMA_BOUND = {
    EntityType.DASHBOARD,
    EntityType.CHART,
    EntityType.ML_FEATURE,
    EntityType.ML_FEATURE_TABLE,
    EntityType.ML_MODEL,
    EntityType.ML_MODEL_DEPLOYMENT,
}


def classify_asset(change: ColumnChange, asset: DownstreamAsset) -> Severity:
    ct = change.change_type
    if ct is ChangeType.ADD_COLUMN:
        return Severity.SAFE
    if ct.is_structural:
        if asset.entity_type in _SCHEMA_BOUND:
            return Severity.BREAKING if asset.degree <= 2 else Severity.PARTIAL
        return Severity.BREAKING if asset.degree == 1 else Severity.PARTIAL
    # FILTER_CHANGE / LOGIC_CHANGE / UNKNOWN: values move, but names still resolve.
    return Severity.PARTIAL


def _reason(change: ColumnChange, asset: DownstreamAsset, sev: Severity) -> str:
    col = f"`{change.column}`" if change.column else "the row filter"
    hop = "directly" if asset.degree == 1 else f"{asset.degree} hops downstream"
    if sev is Severity.BREAKING:
        if asset.entity_type.is_ml:
            return f"consumes {col} as a feature/schema input {hop}; renaming or dropping it breaks the model at serve time"
        if asset.entity_type in {EntityType.DASHBOARD, EntityType.CHART}:
            return f"binds to {col} by name {hop}; the tile will error or go blank"
        return f"reads {col} {hop}; the reference will fail to resolve"
    if sev is Severity.PARTIAL:
        if change.change_type in {ChangeType.FILTER_CHANGE, ChangeType.LOGIC_CHANGE}:
            return f"depends on this model {hop}; values may change silently even though nothing errors"
        return f"depends on {col} {hop} but an intermediate model may shield it, verify"
    return f"unaffected by an additive change to {col}"


def build_assessment(change: ColumnChange, downstream: list[DownstreamAsset]) -> ImpactAssessment:
    verdicts: list[AssetVerdict] = []
    for asset in downstream:
        sev = classify_asset(change, asset)
        verdicts.append(AssetVerdict(asset=asset, severity=sev, reason=_reason(change, asset, sev)))

    # Most dangerous first; within a severity, production before non-production,
    # then closest hop.
    verdicts.sort(key=lambda v: (-v.severity.rank, not v.asset.is_production, v.asset.degree, v.asset.name))

    assessment = ImpactAssessment(change=change, verdicts=verdicts)
    assessment.recompute_overall()
    assessment.rationale = _summary(change, assessment)
    return assessment


def _summary(change: ColumnChange, assessment: ImpactAssessment) -> str:
    n = assessment.blast_count
    if n == 0:
        return f"{change.detail}: nothing downstream depends on this, safe to merge."
    breaking = assessment.breaking_assets
    prod_breaking = [v for v in breaking if v.asset.is_production]
    head = f"{change.detail}: touches {n} downstream asset{'s' if n != 1 else ''}"
    if prod_breaking:
        names = ", ".join(v.asset.name for v in prod_breaking[:3])
        return f"{head}, including {len(prod_breaking)} in PRODUCTION ({names}). Treat as breaking."
    if breaking:
        return f"{head}; {len(breaking)} would break. Coordinate before merging."
    return f"{head}; no hard breaks, but review the ones flagged partial."
