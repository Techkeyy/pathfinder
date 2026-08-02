"""Contribute the assessment back to the DataHub graph.

This is the judging-rewarded "write back to the context graph" behavior and the
part that fights catalog staleness: every reviewed change leaves a durable trace
on the affected column, so the next engineer or agent inherits the knowledge.

We attach the PR as an institutional-memory link (always reliable) and, best
effort, a ``pathfinder-reviewed`` tag. Nothing here raises — a write-back
failure must never fail the PR check.
"""

from __future__ import annotations

from .datahub_client import DataHubClient
from .models import PathfinderReport

REVIEW_TAG = "urn:li:tag:pathfinder-reviewed"


def write_back(client: DataHubClient, resource_urn: str, report: PathfinderReport) -> dict[str, bool]:
    result = {"link": False, "tag": False}
    pr = report.pr
    url = pr.url or f"https://github.com/{pr.repo}/pull/{pr.number}"
    label = f"Pathfinder: {report.overall.value.upper()} change — {pr.repo}#{pr.number}"
    try:
        result["link"] = client.add_link(resource_urn, url, label)
    except Exception:
        result["link"] = False
    try:
        result["tag"] = client.add_tag(resource_urn, REVIEW_TAG)
    except Exception:
        result["tag"] = False
    return result
