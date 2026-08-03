"""Seed the demo stack into a local DataHub.

Builds the exact graph Pathfinder's blast radius walks — tables AND ML — so the
live demo matches demo/lineage.json:

    raw.stg_orders
        └─ analytics.orders            (the model the demo PR changes)
             ├─ analytics.daily_orders ──► 📊 Exec Revenue (dashboard)
             │        └─ analytics.ltv_calc
             └─ 🧬 customer_value (ML feature)
                      └─ 🤖 churn_model (ML model) ──► 🚀 churn_model_prod (deployment)

Run inside the Codespace (or any host with a running DataHub):

    $HOME/.dh/bin/python demo/seed.py      # emitter lives in the isolated venv

Env: DATAHUB_GMS_URL (default http://localhost:8080), DATAHUB_GMS_TOKEN (optional).

Each non-core section is wrapped so a single SDK field-name drift reports itself
(printed as SKIPPED with the reason) instead of aborting the whole seed — the
dataset lineage always lands.
"""

from __future__ import annotations

import os

from datahub.emitter.mce_builder import make_dataset_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import (
    AuditStampClass,
    ChangeAuditStampsClass,
    DashboardInfoClass,
    DatasetLineageTypeClass,
    MLFeaturePropertiesClass,
    MLFeatureTablePropertiesClass,
    MLModelDeploymentPropertiesClass,
    MLModelPropertiesClass,
    OwnerClass,
    OwnershipClass,
    OwnershipTypeClass,
    UpstreamClass,
    UpstreamLineageClass,
)

GMS = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")
TOKEN = os.environ.get("DATAHUB_GMS_TOKEN")

# --- URNs (string form is stable across DataHub versions) -----------------
STG = make_dataset_urn("snowflake", "raw.stg_orders", "PROD")
ORDERS = make_dataset_urn("snowflake", "analytics.orders", "PROD")
DAILY = make_dataset_urn("snowflake", "analytics.daily_orders", "PROD")
LTV = make_dataset_urn("snowflake", "analytics.ltv_calc", "PROD")
DASHBOARD = "urn:li:dashboard:(looker,exec_revenue)"
FEATURE_TABLE = "urn:li:mlFeatureTable:(urn:li:dataPlatform:feast,customer_features)"
FEATURE = "urn:li:mlFeature:(customer_features,customer_value)"
MODEL = "urn:li:mlModel:(urn:li:dataPlatform:mlflow,churn_model,PROD)"
DEPLOYMENT = "urn:li:mlModelDeployment:(urn:li:dataPlatform:sagemaker,churn_model_prod,PROD)"

_T0 = AuditStampClass(time=0, actor="urn:li:corpuser:datahub")


def _owner(who: str, is_group: bool = False) -> OwnershipClass:
    prefix = "urn:li:corpGroup:" if is_group else "urn:li:corpuser:"
    return OwnershipClass(
        owners=[OwnerClass(owner=f"{prefix}{who}", type=OwnershipTypeClass.TECHNICAL_OWNER)]
    )


def _upstreams(urns: list[str]) -> UpstreamLineageClass:
    return UpstreamLineageClass(
        upstreams=[UpstreamClass(dataset=u, type=DatasetLineageTypeClass.TRANSFORMED) for u in urns]
    )


def _emit(emitter: DatahubRestEmitter, urn: str, aspect) -> None:
    emitter.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))


def _section(name: str, fn) -> None:
    try:
        fn()
        print(f"  ✓ {name}")
    except Exception as exc:  # noqa: BLE001 - report + continue; fix live in Codespace
        print(f"  ⚠ SKIPPED {name}: {type(exc).__name__}: {exc}")


def main() -> None:
    emitter = DatahubRestEmitter(gms_server=GMS, token=TOKEN)
    print(f"Seeding {GMS} ...")

    # --- core: dataset lineage + owners (must always land) ---
    def core():
        _emit(emitter, ORDERS, _upstreams([STG]))
        _emit(emitter, DAILY, _upstreams([ORDERS]))
        _emit(emitter, LTV, _upstreams([DAILY]))
        for urn in (ORDERS, DAILY, LTV):
            _emit(emitter, urn, _owner("dana"))
    _section("datasets + lineage (stg→orders→daily→ltv)", core)

    # --- dashboard consuming daily_orders ---
    def dashboard():
        info = DashboardInfoClass(
            title="Exec Revenue",
            description="Executive revenue dashboard (depends on analytics.daily_orders).",
            lastModified=ChangeAuditStampsClass(created=_T0, lastModified=_T0),
            datasets=[DAILY],
        )
        _emit(emitter, DASHBOARD, info)
        _emit(emitter, DASHBOARD, _owner("finance-team", is_group=True))
    _section("dashboard Exec Revenue → daily_orders", dashboard)

    # --- ML feature sourced from orders ---
    def feature():
        _emit(emitter, FEATURE, MLFeaturePropertiesClass(
            description="Rolling customer value; sourced from analytics.orders.",
            sources=[ORDERS],
        ))
        _emit(emitter, FEATURE_TABLE, MLFeatureTablePropertiesClass(
            description="Customer feature table.",
            mlFeatures=[FEATURE],
        ))
    _section("ML feature customer_value ← orders", feature)

    # --- ML model consuming the feature, with a live deployment ---
    def model():
        _emit(emitter, MODEL, MLModelPropertiesClass(
            description="Churn prediction model (PROD).",
            mlFeatures=[FEATURE],
            deployments=[DEPLOYMENT],
        ))
        _emit(emitter, MODEL, _owner("maria"))
        _emit(emitter, DEPLOYMENT, MLModelDeploymentPropertiesClass(
            description="Live churn_model serving endpoint.",
        ))
        _emit(emitter, DEPLOYMENT, _owner("maria"))
    _section("ML model churn_model ← feature, → deployment", model)

    print(
        f"\nDone. Blast radius from analytics.orders should include daily_orders, ltv_calc,\n"
        f"Exec Revenue, customer_value, churn_model, churn_model_prod.\n"
        f"UI: forwarded port 9002  |  GraphQL: {GMS}/api/graphql"
    )


if __name__ == "__main__":
    main()
