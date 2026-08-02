"""Unit tests for the deterministic severity classifier."""

from pathfinder.classifier import build_assessment, classify_asset
from pathfinder.models import (
    ChangeType,
    ColumnChange,
    DownstreamAsset,
    EntityType,
    Severity,
)


def _change(ct=ChangeType.RENAME, col="customer_id"):
    return ColumnChange(dataset="orders", column=col, change_type=ct, detail="renamed")


def _asset(etype, degree=1, prod=False, name="x"):
    return DownstreamAsset(urn=f"urn:{name}", name=name, entity_type=etype, degree=degree, is_production=prod)


def test_rename_breaks_direct_dataset():
    assert classify_asset(_change(), _asset(EntityType.DATASET, degree=1)) is Severity.BREAKING


def test_rename_partial_for_deep_dataset():
    assert classify_asset(_change(), _asset(EntityType.DATASET, degree=3)) is Severity.PARTIAL


def test_rename_breaks_ml_model_within_two_hops():
    assert classify_asset(_change(), _asset(EntityType.ML_MODEL, degree=2)) is Severity.BREAKING


def test_add_column_is_safe():
    assert classify_asset(_change(ChangeType.ADD_COLUMN), _asset(EntityType.DASHBOARD)) is Severity.SAFE


def test_filter_change_is_partial_even_for_dashboard():
    assert classify_asset(_change(ChangeType.FILTER_CHANGE, col=None), _asset(EntityType.DASHBOARD)) is Severity.PARTIAL


def test_assessment_overall_is_worst_and_prod_first():
    downstream = [
        _asset(EntityType.DATASET, degree=3, name="cold_table"),          # partial
        _asset(EntityType.ML_MODEL, degree=1, prod=True, name="churn"),   # breaking, prod
        _asset(EntityType.DASHBOARD, degree=1, name="exec"),              # breaking
    ]
    a = build_assessment(_change(), downstream)
    assert a.overall is Severity.BREAKING
    assert a.blast_count == 3
    # production breaking asset should be ranked first.
    assert a.verdicts[0].asset.name == "churn"
    assert a.verdicts[0].asset.is_production is True


def test_empty_blast_is_safe():
    a = build_assessment(_change(), [])
    assert a.overall is Severity.SAFE
    assert "safe to merge" in a.rationale
