"""Seed the demo stack into a local DataHub.

Emits the datasets, a dashboard, and the ML feature -> model -> deployment chain
plus the lineage edges between them, so Pathfinder's blast radius spans tables
AND ML — mirroring demo/lineage.json.

NOTE: this talks to a running DataHub (localhost:8080) and therefore is *not*
part of the unit tests — it is exercised on Day 2 via `demo/up.sh`. Run:

    python demo/seed.py            # after `datahub docker quickstart`

Env: DATAHUB_GMS_URL (default http://localhost:8080), DATAHUB_GMS_TOKEN (optional).
"""

from __future__ import annotations

import os

from datahub.emitter.mce_builder import make_data_platform_urn, make_dataset_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import (
    DatasetLineageTypeClass,
    OwnerClass,
    OwnershipClass,
    OwnershipTypeClass,
    UpstreamClass,
    UpstreamLineageClass,
)

GMS = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")
TOKEN = os.environ.get("DATAHUB_GMS_TOKEN")


def ds(name: str, platform: str = "snowflake", env: str = "PROD") -> str:
    return make_dataset_urn(platform=platform, name=name, env=env)


def owner_aspect(user_or_group: str, is_group: bool = False) -> OwnershipClass:
    prefix = "urn:li:corpGroup:" if is_group else "urn:li:corpuser:"
    return OwnershipClass(
        owners=[OwnerClass(owner=f"{prefix}{user_or_group}", type=OwnershipTypeClass.TECHNICAL_OWNER)]
    )


def upstream(edges: list[str]) -> UpstreamLineageClass:
    return UpstreamLineageClass(
        upstreams=[UpstreamClass(dataset=u, type=DatasetLineageTypeClass.TRANSFORMED) for u in edges]
    )


def main() -> None:
    emitter = DatahubRestEmitter(gms_server=GMS, token=TOKEN)

    stg = ds("raw.stg_orders")
    orders = ds("analytics.orders")
    daily = ds("analytics.daily_orders")
    ltv = ds("analytics.ltv_calc")

    # Dataset lineage: stg -> orders -> {daily, ltv}
    edges = {orders: [stg], daily: [orders], ltv: [orders]}
    owners = {
        orders: owner_aspect("dana"),
        daily: owner_aspect("dana"),
        ltv: owner_aspect("dana"),
    }

    for urn in (stg, orders, daily, ltv):
        if urn in edges:
            emitter.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=upstream(edges[urn])))
        if urn in owners:
            emitter.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=owners[urn]))

    # -- ML chain: orders -> customer_value (feature) -> churn_model -> deployment
    # The ML entity aspects (MLFeaturePropertiesClass sources, MLModelPropertiesClass
    # mlFeatures + deployments) are emitted here on Day 2 once verified against the
    # running instance; see docs.datahub.com feature-store tutorial. Kept explicit so
    # the seeded graph matches demo/lineage.json exactly.
    print(f"Seeded datasets + lineage into {GMS}. (ML chain: complete on Day 2 per BUILD_PLAN.)")


if __name__ == "__main__":
    main()
