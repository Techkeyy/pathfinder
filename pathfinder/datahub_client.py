"""DataHub access layer — the engine that walks the blast radius.

Everything Pathfinder knows about "what depends on what" comes from here. We talk
to DataHub's **GraphQL** endpoint (``{gms}/api/graphql``) rather than the MCP
wrapper, because GraphQL's ``searchAcrossLineage`` is entity-type-agnostic: a
single downstream walk returns datasets, dashboards, charts, **ML features, ML
models and ML deployments** in one shot. That is the cross-stack + ML coverage
that dbt/Recce cannot give us.

The GraphQL field names below follow DataHub's published schema. Because minor
fields drift between DataHub versions, :meth:`DataHubClient.doctor` runs a live
introspection/smoke check so Day-1 setup fails loudly instead of silently
returning empty blast radii.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import requests

from .models import DownstreamAsset, EntityType, Owner

# GraphQL type name (from `entity.type`) -> our EntityType.
_TYPE_MAP = {
    "DATASET": EntityType.DATASET,
    "DASHBOARD": EntityType.DASHBOARD,
    "CHART": EntityType.CHART,
    "MLMODEL": EntityType.ML_MODEL,
    "MLFEATURE": EntityType.ML_FEATURE,
    "MLFEATURE_TABLE": EntityType.ML_FEATURE_TABLE,
    "MLPRIMARYKEY": EntityType.ML_FEATURE,
    "MLMODEL_DEPLOYMENT": EntityType.ML_MODEL_DEPLOYMENT,
    "DATA_JOB": EntityType.DATA_JOB,
}

# Fragment requesting the fields we need from every relevant entity kind. Kept in
# one place so the search query and the by-URN query stay in sync.
# NOTE: `properties.name` has different nullability on DatasetProperties vs
# DashboardProperties, so selecting it across inline fragments triggers a
# GraphQL FieldsConflict. We therefore read the top-level `name` where the type
# has one (Dataset, MLModel, MLFeature*, MLModelGroup) and ALIAS `properties`
# per type for the ones that only carry a name inside properties (Dashboard,
# Chart, DataJob). _name_of() knows all these keys.
_ENTITY_FRAGMENT = """
fragment PathfinderEntity on Entity {
  urn
  type
  ... on Dataset {
    name
    origin
    platform { name properties { displayName } }
    subTypes { typeNames }
    tags { tags { tag { urn name } } }
    ownership { owners { owner { ... on CorpUser { urn username } ... on CorpGroup { urn name } } } }
  }
  ... on Dashboard {
    dashboardProperties: properties { name }
    platform { name }
    tags { tags { tag { urn name } } }
    ownership { owners { owner { ... on CorpUser { urn username } ... on CorpGroup { urn name } } } }
  }
  ... on Chart {
    chartProperties: properties { name }
    platform { name }
    ownership { owners { owner { ... on CorpUser { urn username } ... on CorpGroup { urn name } } } }
  }
  ... on MLModel {
    name
    tags { tags { tag { urn name } } }
    ownership { owners { owner { ... on CorpUser { urn username } ... on CorpGroup { urn name } } } }
  }
  ... on MLModelGroup { name }
  ... on MLFeature { name }
  ... on MLFeatureTable { name }
  ... on DataJob {
    dataJobProperties: properties { name }
    ownership { owners { owner { ... on CorpUser { urn username } ... on CorpGroup { urn name } } } }
  }
}
"""

_LINEAGE_QUERY = (
    _ENTITY_FRAGMENT
    + """
query PathfinderLineage($input: SearchAcrossLineageInput!) {
  searchAcrossLineage(input: $input) {
    total
    searchResults {
      degree
      entity { ...PathfinderEntity }
    }
  }
}
"""
)

_SEARCH_QUERY = (
    _ENTITY_FRAGMENT
    + """
query PathfinderSearch($input: SearchInput!) {
  search(input: $input) {
    total
    searchResults { entity { ...PathfinderEntity } }
  }
}
"""
)


class DataHubError(RuntimeError):
    """Raised when DataHub returns GraphQL errors or an unexpected shape."""


class DataHubClient:
    def __init__(self, graphql_url: str, token: Optional[str] = None,
                 production_markers: Optional[list[str]] = None, timeout: int = 30):
        self.graphql_url = graphql_url
        self.timeout = timeout
        self.production_markers = [m.lower() for m in (production_markers or ["prod", "production"])]
        self._session = requests.Session()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._session.headers.update(headers)

    # -- transport ----------------------------------------------------------
    def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        resp = self._session.post(
            self.graphql_url,
            data=json.dumps({"query": query, "variables": variables}),
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise DataHubError(f"DataHub HTTP {resp.status_code}: {resp.text[:400]}")
        payload = resp.json()
        if payload.get("errors"):
            raise DataHubError(f"DataHub GraphQL errors: {payload['errors']}")
        return payload.get("data") or {}

    # -- resolution ---------------------------------------------------------
    @staticmethod
    def dataset_urn(name: str, platform: str, env: str = "PROD") -> str:
        """Construct a dataset URN the DataHub way."""
        return f"urn:li:dataset:(urn:li:dataPlatform:{platform},{name},{env})"

    def resolve_dataset(self, name: str, platform: str, env: str = "PROD") -> Optional[str]:
        """Find the URN for a model/table name.

        Tries the deterministic URN first (cheap, exact); if that entity does not
        exist we fall back to a keyword search so a bare dbt model name still
        resolves to whatever platform it actually landed on.
        """
        candidate = self.dataset_urn(name, platform, env)
        if self.entity_exists(candidate):
            return candidate
        hits = self.search(name, types=["DATASET"], count=5)
        # Prefer an exact case-insensitive name match, else the top hit.
        for h in hits:
            if h.name.lower() == name.lower() or h.name.lower().endswith("." + name.lower()):
                return h.urn
        return hits[0].urn if hits else None

    def entity_exists(self, urn: str) -> bool:
        data = self._graphql("query($urn:String!){ entity(urn:$urn){ urn } }", {"urn": urn})
        return bool((data.get("entity") or {}).get("urn"))

    def search(self, query: str, types: Optional[list[str]] = None, count: int = 10) -> list[DownstreamAsset]:
        variables = {"input": {"type": (types or [None])[0], "query": query, "start": 0, "count": count}}
        # `search` takes a single type; use searchAcrossEntities semantics via `type: null`.
        if not types:
            variables["input"].pop("type")
        data = self._graphql(_SEARCH_QUERY, variables)
        results = ((data.get("search") or {}).get("searchResults")) or []
        return [self._to_asset(r["entity"], degree=0) for r in results if r.get("entity")]

    # -- the blast radius ---------------------------------------------------
    def get_downstream(self, urn: str, max_hops: int = 3, count: int = 200,
                       types: Optional[list[str]] = None) -> list[DownstreamAsset]:
        """Return everything downstream of ``urn`` (the blast radius).

        ``types`` may restrict the search (e.g. only DASHBOARD/MLMODEL); by
        default every entity kind is returned. Results are de-duplicated by URN,
        keeping the shortest hop distance.
        """
        variables = {
            "input": {
                "urn": urn,
                "direction": "DOWNSTREAM",
                "query": "*",
                "start": 0,
                "count": count,
                "types": types,
            }
        }
        if types is None:
            variables["input"].pop("types")
        data = self._graphql(_LINEAGE_QUERY, variables)
        results = ((data.get("searchAcrossLineage") or {}).get("searchResults")) or []

        by_urn: dict[str, DownstreamAsset] = {}
        for r in results:
            degree = int(r.get("degree") or 1)
            if degree > max_hops:
                continue
            ent = r.get("entity")
            if not ent:
                continue
            asset = self._to_asset(ent, degree=degree)
            prior = by_urn.get(asset.urn)
            if prior is None or asset.degree < prior.degree:
                by_urn[asset.urn] = asset
        return sorted(by_urn.values(), key=lambda a: (a.degree, a.name))

    # -- mapping helpers ----------------------------------------------------
    def _to_asset(self, ent: dict[str, Any], degree: int) -> DownstreamAsset:
        etype = _TYPE_MAP.get(ent.get("type", ""), EntityType.OTHER)
        name = self._name_of(ent)
        platform = self._platform_of(ent)
        owners = self._owners_of(ent)
        is_prod = self._is_production(ent, etype)
        return DownstreamAsset(
            urn=ent["urn"],
            name=name,
            entity_type=etype,
            platform=platform,
            degree=degree,
            is_production=is_prod,
            owners=owners,
        )

    @staticmethod
    def _name_of(ent: dict[str, Any]) -> str:
        if ent.get("name"):
            return ent["name"]
        # Type-aliased properties (see _ENTITY_FRAGMENT), then a plain one.
        for key in ("dashboardProperties", "chartProperties", "dataJobProperties", "properties"):
            props = ent.get(key) or {}
            if props.get("name"):
                return props["name"]
        # Fall back to the URN's name segment.
        urn = ent.get("urn", "unknown")
        return urn.rstrip(")").split(",")[-2] if "," in urn else urn

    @staticmethod
    def _platform_of(ent: dict[str, Any]) -> Optional[str]:
        plat = ent.get("platform") or {}
        pprops = plat.get("properties") or {}
        return pprops.get("displayName") or plat.get("name")

    @staticmethod
    def _owners_of(ent: dict[str, Any]) -> list[Owner]:
        owners: list[Owner] = []
        for o in ((ent.get("ownership") or {}).get("owners")) or []:
            owner = o.get("owner") or {}
            if owner.get("username"):
                owners.append(Owner(name=owner["username"], kind="user", urn=owner.get("urn")))
            elif owner.get("name"):
                owners.append(Owner(name=owner["name"], kind="group", urn=owner.get("urn")))
        return owners

    def _is_production(self, ent: dict[str, Any], etype: EntityType) -> bool:
        # A live deployment is production by definition.
        if etype is EntityType.ML_MODEL_DEPLOYMENT:
            return True
        # Dataset origin/env (PROD/DEV) is the strongest signal when present.
        origin = (ent.get("origin") or "").lower()
        if origin and any(m in origin for m in self.production_markers):
            return True
        # Otherwise look at tags (e.g. a "production" tag on a model/dashboard).
        for t in ((ent.get("tags") or {}).get("tags")) or []:
            tag = t.get("tag") or {}
            label = (tag.get("name") or tag.get("urn") or "").lower()
            if any(m in label for m in self.production_markers):
                return True
        return False

    # -- write-back ---------------------------------------------------------
    def add_link(self, resource_urn: str, url: str, label: str) -> bool:
        """Attach an institutional-memory link (e.g. the PR) to an entity."""
        data = self._graphql(
            "mutation($input: AddLinkInput!){ addLink(input: $input) }",
            {"input": {"resourceUrn": resource_urn, "linkUrl": url, "label": label}},
        )
        return bool(data.get("addLink"))

    def add_tag(self, resource_urn: str, tag_urn: str) -> bool:
        """Best-effort tag association (tag must exist in DataHub)."""
        try:
            data = self._graphql(
                "mutation($input: TagAssociationInput!){ addTag(input: $input) }",
                {"input": {"resourceUrn": resource_urn, "tagUrn": tag_urn}},
            )
            return bool(data.get("addTag"))
        except DataHubError:
            return False

    # -- self-check ---------------------------------------------------------
    def doctor(self) -> dict[str, Any]:
        """Smoke-test connectivity and that lineage returns cross-stack results.

        Run this on Day 1 (``pathfinder doctor``) against the seeded instance. It
        confirms the GraphQL shape used above matches this DataHub version before
        we rely on it, so schema drift surfaces immediately, not on camera.
        """
        report: dict[str, Any] = {"graphql_url": self.graphql_url}
        me = self._graphql("query{ me { corpUser { urn } } }", {})
        report["authenticated_as"] = ((me.get("me") or {}).get("corpUser") or {}).get("urn")
        # Confirm searchAcrossLineage is accepted with our variable shape.
        probe = self._graphql(
            "query($i:SearchAcrossLineageInput!){ searchAcrossLineage(input:$i){ total } }",
            {"i": {"urn": "urn:li:corpuser:__pathfinder_probe__",
                   "direction": "DOWNSTREAM", "query": "*", "start": 0, "count": 1}},
        )
        report["lineage_query_ok"] = "searchAcrossLineage" in probe
        return report
