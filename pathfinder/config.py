"""Configuration for a Pathfinder run.

Values resolve in this order (later wins):
  1. built-in defaults
  2. a YAML file (``pathfinder.yml`` by default)
  3. environment variables (so CI secrets and ``.env`` work without a file)

Nothing here reaches the network; :func:`Config.load` is pure so it is easy to
unit-test.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

try:  # PyYAML is optional at import time; only needed if a yml file is used.
    import yaml
except Exception:  # pragma: no cover - handled gracefully at load time
    yaml = None  # type: ignore


@dataclass
class Config:
    # --- DataHub -----------------------------------------------------------
    # Base GMS URL, e.g. http://localhost:8080 . GraphQL is served at
    # {datahub_url}/api/graphql .
    datahub_url: str = "http://localhost:8080"
    datahub_token: Optional[str] = None
    # Default coordinates used when resolving a bare model name to a URN.
    default_platform: str = "dbt"
    default_env: str = "PROD"
    max_hops: int = 3  # DataHub lineage search supports up to 3 degrees.

    # --- GitHub ------------------------------------------------------------
    github_token: Optional[str] = None

    # --- LLM ---------------------------------------------------------------
    llm_provider: str = "anthropic"          # "anthropic" | "openai" | "none"
    llm_model: str = "claude-sonnet-5"
    llm_api_key: Optional[str] = None

    # --- dbt (optional, improves change extraction) ------------------------
    dbt_manifest_path: Optional[str] = None  # target/manifest.json

    # --- behaviour ---------------------------------------------------------
    # Map a dataset/dbt node name to a DataHub platform when it cannot be
    # inferred (e.g. {"orders": "snowflake"}).
    platform_overrides: dict[str, str] = field(default_factory=dict)
    # Tags/environments that mean "this is live in production".
    production_markers: list[str] = field(
        default_factory=lambda: ["production", "prod", "PROD", "serving", "live"]
    )
    fail_on_breaking: bool = False  # exit non-zero so CI can block a merge.

    @property
    def graphql_url(self) -> str:
        return self.datahub_url.rstrip("/") + "/api/graphql"

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider != "none" and bool(self.llm_api_key)

    # -- loading ------------------------------------------------------------
    @classmethod
    def load(cls, path: str | None = "pathfinder.yml", env: dict[str, str] | None = None) -> "Config":
        env = dict(os.environ if env is None else env)
        data: dict[str, Any] = {}

        if path and os.path.exists(path):
            if yaml is None:
                raise RuntimeError("pathfinder.yml found but PyYAML is not installed")
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}

        cfg = cls(**{k: v for k, v in data.items() if k in cls._field_names()})

        # Environment overrides (CI-friendly).
        cfg.datahub_url = env.get("DATAHUB_GMS_URL", env.get("DATAHUB_URL", cfg.datahub_url))
        cfg.datahub_token = env.get("DATAHUB_GMS_TOKEN", env.get("DATAHUB_TOKEN", cfg.datahub_token))
        cfg.github_token = env.get("GITHUB_TOKEN", cfg.github_token)
        cfg.llm_provider = env.get("PATHFINDER_LLM_PROVIDER", cfg.llm_provider)
        cfg.llm_model = env.get("PATHFINDER_LLM_MODEL", cfg.llm_model)
        cfg.llm_api_key = (
            env.get("ANTHROPIC_API_KEY")
            or env.get("OPENAI_API_KEY")
            or env.get("PATHFINDER_LLM_API_KEY")
            or cfg.llm_api_key
        )
        cfg.dbt_manifest_path = env.get("PATHFINDER_DBT_MANIFEST", cfg.dbt_manifest_path)
        if env.get("PATHFINDER_FAIL_ON_BREAKING", "").lower() in {"1", "true", "yes"}:
            cfg.fail_on_breaking = True
        return cfg

    @staticmethod
    def _field_names() -> set[str]:
        from dataclasses import fields

        return {f.name for f in fields(Config)}
