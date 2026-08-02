"""Core data structures shared across Pathfinder.

These are deliberately plain dataclasses with no I/O so they are trivial to
construct in tests and to serialize into the PR comment, the JSON artifact, and
the DataHub write-back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ChangeType(str, Enum):
    """The kind of change Pathfinder detected on a column or model."""

    RENAME = "rename"            # column renamed (breaking for consumers by name)
    DROP_COLUMN = "drop_column"  # column removed
    TYPE_CHANGE = "type_change"  # column data type changed
    FILTER_CHANGE = "filter_change"  # WHERE/qualify predicate changed (row set changes)
    LOGIC_CHANGE = "logic_change"    # the expression producing a column changed
    ADD_COLUMN = "add_column"    # new column added (generally safe)
    UNKNOWN = "unknown"

    @property
    def is_structural(self) -> bool:
        """Structural changes are the ones that break consumers referencing a name."""
        return self in {ChangeType.RENAME, ChangeType.DROP_COLUMN, ChangeType.TYPE_CHANGE}


class Severity(str, Enum):
    """How dangerous a change is for a given downstream asset (or overall)."""

    BREAKING = "breaking"  # will break the consumer
    PARTIAL = "partial"    # may break / silently change values; needs review
    SAFE = "safe"          # additive or non-impacting

    @property
    def rank(self) -> int:
        return {"breaking": 3, "partial": 2, "safe": 1}[self.value]

    @property
    def emoji(self) -> str:
        return {"breaking": "🔴", "partial": "🟠", "safe": "🟢"}[self.value]


class EntityType(str, Enum):
    """DataHub entity kinds Pathfinder cares about in a blast radius."""

    DATASET = "DATASET"
    DASHBOARD = "DASHBOARD"
    CHART = "CHART"
    ML_MODEL = "MLMODEL"
    ML_FEATURE = "MLFEATURE"
    ML_FEATURE_TABLE = "MLFEATURE_TABLE"
    ML_MODEL_DEPLOYMENT = "MLMODEL_DEPLOYMENT"
    DATA_JOB = "DATA_JOB"
    OTHER = "OTHER"

    @property
    def emoji(self) -> str:
        return {
            "DATASET": "🗂️",
            "DASHBOARD": "📊",
            "CHART": "📈",
            "MLMODEL": "🤖",
            "MLFEATURE": "🧬",
            "MLFEATURE_TABLE": "🧬",
            "MLMODEL_DEPLOYMENT": "🚀",
            "DATA_JOB": "⚙️",
            "OTHER": "🔗",
        }.get(self.value, "🔗")

    @property
    def is_ml(self) -> bool:
        return self in {
            EntityType.ML_MODEL,
            EntityType.ML_FEATURE,
            EntityType.ML_FEATURE_TABLE,
            EntityType.ML_MODEL_DEPLOYMENT,
        }


@dataclass
class ColumnChange:
    """A single detected change, scoped to a dataset and (optionally) a column."""

    dataset: str                      # human name of the changed model/table
    change_type: ChangeType
    column: Optional[str] = None      # None => model-level change (e.g. filter)
    detail: str = ""                  # human explanation ("renamed customer_id -> cust_id")
    before: Optional[str] = None
    after: Optional[str] = None

    def key(self) -> str:
        return f"{self.dataset}.{self.column or '*'}:{self.change_type.value}"


@dataclass
class Owner:
    """An owner resolved from DataHub ownership aspects."""

    name: str
    kind: str = "user"   # "user" | "group"
    urn: Optional[str] = None

    def mention(self) -> str:
        # DataHub usernames often are emails; strip the domain for a readable @mention.
        handle = self.name.split("@")[0] if self.name else self.name
        return f"@{handle}"


@dataclass
class DownstreamAsset:
    """One node in the blast radius: something that depends on the changed column."""

    urn: str
    name: str
    entity_type: EntityType
    platform: Optional[str] = None
    degree: int = 1                    # hops from the change (1 = direct)
    is_production: bool = False        # tag/env heuristic; True raises severity
    owners: list[Owner] = field(default_factory=list)
    via_column: Optional[str] = None   # which changed column reaches this asset

    def label(self) -> str:
        prod = " (PROD)" if self.is_production else ""
        plat = f" · {self.platform}" if self.platform else ""
        return f"{self.entity_type.emoji} {self.name}{prod}{plat}"


@dataclass
class AssetVerdict:
    """Per-asset judgement produced by the classifier."""

    asset: DownstreamAsset
    severity: Severity
    reason: str


@dataclass
class ImpactAssessment:
    """Everything Pathfinder concluded about one detected change."""

    change: ColumnChange
    verdicts: list[AssetVerdict] = field(default_factory=list)
    overall: Severity = Severity.SAFE
    rationale: str = ""

    @property
    def blast_count(self) -> int:
        return len(self.verdicts)

    @property
    def breaking_assets(self) -> list[AssetVerdict]:
        return [v for v in self.verdicts if v.severity is Severity.BREAKING]

    def recompute_overall(self) -> Severity:
        """Overall severity = the worst per-asset severity."""
        if not self.verdicts:
            self.overall = Severity.SAFE
        else:
            self.overall = max((v.severity for v in self.verdicts), key=lambda s: s.rank)
        return self.overall


@dataclass
class Remediation:
    """A drafted, backward-compatible fix for a change (Challenge #2 artifact)."""

    title: str
    language: str          # "sql" | "yaml" | "diff"
    body: str              # the actual code/patch
    explanation: str = ""


@dataclass
class PullRequestRef:
    """Minimal PR context Pathfinder needs to comment and label."""

    repo: str              # "owner/name"
    number: int
    title: str = ""
    author: str = ""
    url: str = ""


@dataclass
class PathfinderReport:
    """The full result of a run: everything the reporter and write-back consume."""

    pr: PullRequestRef
    assessments: list[ImpactAssessment] = field(default_factory=list)
    remediations: list[Remediation] = field(default_factory=list)

    @property
    def overall(self) -> Severity:
        if not self.assessments:
            return Severity.SAFE
        return max((a.overall for a in self.assessments), key=lambda s: s.rank)

    @property
    def total_blast(self) -> int:
        # Count each affected asset once, even if reached by several changes.
        return len({v.asset.urn for a in self.assessments for v in a.verdicts})

    @property
    def affected_owners(self) -> list[Owner]:
        seen: dict[str, Owner] = {}
        for a in self.assessments:
            for v in a.verdicts:
                for o in v.asset.owners:
                    seen.setdefault(o.name, o)
        return list(seen.values())
