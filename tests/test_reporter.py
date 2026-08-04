"""Reporter tests — especially the honest handling of uncatalogued datasets."""

from pathfinder.classifier import build_assessment
from pathfinder.models import (
    ChangeType,
    ColumnChange,
    DownstreamAsset,
    EntityType,
    PathfinderReport,
    PullRequestRef,
)
from pathfinder.reporter import render_markdown


def _pr() -> PullRequestRef:
    return PullRequestRef(repo="acme/warehouse", number=1)


def _report_with_blast() -> PathfinderReport:
    change = ColumnChange(dataset="orders", column="x", change_type=ChangeType.RENAME, detail="renamed")
    asset = DownstreamAsset(urn="urn:li:x", name="d", entity_type=EntityType.DATASET, degree=1)
    return PathfinderReport(pr=_pr(), assessments=[build_assessment(change, [asset])])


def test_unresolved_reports_cannot_assess_not_safe():
    # A changed dataset that DataHub doesn't know about must NOT read as "safe".
    report = PathfinderReport(pr=_pr(), unresolved=["mystery_model"])
    md = render_markdown(report)
    assert "CANNOT FULLY ASSESS" in md
    assert "mystery_model" in md
    assert "Safe to merge" not in md


def test_empty_and_resolved_is_safe():
    report = PathfinderReport(pr=_pr())  # nothing downstream, nothing unresolved
    md = render_markdown(report)
    assert "Safe to merge" in md
    assert "CANNOT FULLY ASSESS" not in md


def test_writeback_footer_only_when_written():
    report = _report_with_blast()  # footer only renders when there's a blast radius
    assert "written back to the catalog" in render_markdown(report, wrote_back=True)
    assert "written back to the catalog" not in render_markdown(report, wrote_back=False)
