"""Render the PR comment and the JSON artifact.

The comment is the whole product from the engineer's seat, so it has to read
like something a thoughtful reviewer wrote: a one-line verdict, a table of what
breaks and who owns it, the drafted fix, and the owners to notify.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from .models import PathfinderReport, Remediation, Severity

MARKER = "<!-- pathfinder-report -->"  # marker so we can update the comment in place
_HEADER = MARKER


def render_markdown(report: PathfinderReport, wrote_back: bool = False) -> str:
    unresolved = report.unresolved
    lines: list[str] = [_HEADER]

    # When nothing resolved, don't claim "safe", that would be a false negative.
    if report.total_blast == 0 and unresolved:
        lines.append("## 🧭 Pathfinder, ⚠️ CANNOT FULLY ASSESS")
    else:
        lines.append(f"## 🧭 Pathfinder, {report.overall.emoji} {report.overall.value.upper()}")

    if unresolved:
        names = ", ".join(f"`{d}`" for d in unresolved)
        lines.append(
            f"\n⚠️ **Not found in DataHub:** {names}. Pathfinder can't see any downstream "
            f"for these, so a lack of findings is **not** a clean bill of health, catalog "
            f"them to get a real assessment."
        )

    if report.total_blast == 0:
        if not unresolved:
            lines.append("\nNo downstream assets depend on the changed columns. **Safe to merge.** ✅")
        return "\n".join(lines)

    n = report.total_blast
    owners = report.affected_owners
    lines.append(
        f"\nThis PR affects **{n} downstream asset{'s' if n != 1 else ''}** across your stack."
    )

    for assessment in report.assessments:
        if not assessment.verdicts:
            continue
        c = assessment.change
        lines.append(f"\n### `{c.dataset}`, {c.detail}")
        lines.append(f"_{assessment.rationale}_\n")
        lines.append("| Sev | Downstream asset | Type | Owner | Why |")
        lines.append("|-----|------------------|------|-------|-----|")
        for v in assessment.verdicts:
            a = v.asset
            owner = ", ".join(o.mention() for o in a.owners) or "—"
            prod = " **(PROD)**" if a.is_production else ""
            lines.append(
                f"| {v.severity.emoji} | {a.entity_type.emoji} {a.name}{prod} "
                f"| {a.entity_type.value} | {owner} | {v.reason} |"
            )

    # Drafted fixes
    if report.remediations:
        lines.append("\n### 🛠 Suggested fix")
        for rem in report.remediations:
            lines.append(_render_remediation(rem))

    # Owner notifications
    if owners:
        mentions = " ".join(sorted({o.mention() for o in owners}))
        lines.append(f"\n**Owners to notify:** {mentions}")

    writeback_note = (
        " This assessment has been written back to the catalog." if wrote_back else ""
    )
    lines.append(
        "\n<sub>Pathfinder walked your DataHub lineage graph. "
        "Verdicts and rationale are deterministic; the drafted fix may be LLM-polished."
        + writeback_note + "</sub>"
    )
    return "\n".join(lines)


def _render_remediation(rem: Remediation) -> str:
    fence = rem.language if rem.language in {"sql", "yaml", "diff"} else ""
    return f"**{rem.title}**, {rem.explanation}\n\n```{fence}\n{rem.body}\n```"


def to_json(report: PathfinderReport) -> str:
    """Serialize the full report (used for the `examples/` artifact and CI logs)."""
    payload = {
        "pr": asdict(report.pr),
        "overall": report.overall.value,
        "total_blast": report.total_blast,
        "assessments": [
            {
                "change": asdict(a.change),
                "overall": a.overall.value,
                "rationale": a.rationale,
                "verdicts": [
                    {
                        "severity": v.severity.value,
                        "reason": v.reason,
                        "asset": {
                            "urn": v.asset.urn,
                            "name": v.asset.name,
                            "type": v.asset.entity_type.value,
                            "platform": v.asset.platform,
                            "degree": v.asset.degree,
                            "is_production": v.asset.is_production,
                            "owners": [o.name for o in v.asset.owners],
                        },
                    }
                    for v in a.verdicts
                ],
            }
            for a in report.assessments
        ],
        "remediations": [asdict(r) for r in report.remediations],
    }
    return json.dumps(payload, indent=2)
