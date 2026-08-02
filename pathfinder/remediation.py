"""Draft backward-compatible fixes for breaking changes.

This is Pathfinder's Challenge-#2 artifact: it doesn't just warn, it generates
code a data team would actually merge. Templates are deterministic (so they
always work); an LLM can optionally rewrite them to match house style.
"""

from __future__ import annotations

from .llm import LLM
from .models import ChangeType, ImpactAssessment, Remediation

_LLM_SYSTEM = (
    "You are a senior analytics engineer. Rewrite the given backward-compatible "
    "SQL shim to be idiomatic dbt, preserving its behavior exactly. Return only SQL."
)


def draft(assessment: ImpactAssessment, llm: LLM | None = None) -> Remediation | None:
    """Return a shim that keeps consumers working while they migrate, or None."""
    change = assessment.change
    if assessment.overall.value == "safe" or change.change_type is ChangeType.ADD_COLUMN:
        return None

    ct = change.change_type
    ds = change.dataset

    if ct is ChangeType.RENAME and change.before and change.after:
        old, new = change.before, change.after
        body = (
            f"-- Pathfinder shim for `{ds}`: keep `{old}` available while consumers\n"
            f"-- migrate to `{new}`. Remove after all downstream owners have moved.\n"
            f"select\n    *,\n    {new} as {old}  -- deprecated alias\nfrom {{{{ ref('{ds}') }}}}"
        )
        expl = f"Add `{new} as {old}` so existing references to `{old}` keep resolving."
        return _maybe_polish(Remediation(f"Compatibility alias for {ds}.{old}", "sql", body, expl), llm)

    if ct is ChangeType.DROP_COLUMN and change.before:
        col = change.before
        body = (
            f"-- Pathfinder shim for `{ds}`: `{col}` was dropped but consumers still\n"
            f"-- read it. Re-expose it (or a NULL placeholder) until they are updated.\n"
            f"select\n    *,\n    cast(null as string) as {col}  -- TODO: restore real source or remove consumers\nfrom {{{{ ref('{ds}') }}}}"
        )
        expl = f"Re-expose `{col}` (here as a typed NULL) so downstream references do not error."
        return _maybe_polish(Remediation(f"Compatibility placeholder for {ds}.{col}", "sql", body, expl), llm)

    if ct is ChangeType.TYPE_CHANGE and change.column:
        col, bt, at = change.column, change.before, change.after
        body = (
            f"-- Pathfinder note for `{ds}`: `{col}` type changed {bt} -> {at}.\n"
            f"-- If consumers depend on the old type, expose both:\n"
            f"select\n    *,\n    cast({col} as {bt}) as {col}_{bt}  -- legacy-typed copy\nfrom {{{{ ref('{ds}') }}}}"
        )
        expl = f"Offer a legacy-typed `{col}_{bt}` copy so type-sensitive consumers keep working."
        return _maybe_polish(Remediation(f"Type-compat copy for {ds}.{col}", "sql", body, expl), llm)

    if ct in {ChangeType.FILTER_CHANGE, ChangeType.LOGIC_CHANGE}:
        # No structural shim possible; the fix is a coordinated, communicated change.
        return Remediation(
            title=f"Review checklist for {ds}",
            language="diff",
            body=(
                f"# `{ds}` output values may change (no schema break).\n"
                f"# Before merging:\n"
                f"#  1. Snapshot a before/after data diff on the affected columns.\n"
                f"#  2. Confirm downstream metrics/thresholds still hold.\n"
                f"#  3. Notify the owners tagged in this PR."
            ),
            explanation="Value-level change: verify with a data diff rather than a schema shim.",
        )
    return None


def _maybe_polish(rem: Remediation, llm: LLM | None) -> Remediation:
    if rem.language == "sql" and llm and llm.available:
        polished = llm.complete(_LLM_SYSTEM, rem.body, max_tokens=400)
        if polished and "select" in polished.lower():
            rem.body = polished.strip()
    return rem
