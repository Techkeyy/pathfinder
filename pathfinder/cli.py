"""Command line entry point: ``pathfinder doctor`` and ``pathfinder run``.

``run`` supports two input modes that share one pipeline:
* ``--pr <github-url>``  — production/CI path (reads the PR, posts a comment).
* ``--before/--after/--dataset`` — local path, ideal for demos and filming.

Lineage comes from DataHub, or from a ``--lineage-fixture`` JSON so the whole
thing runs (and the demo films) without a live catalog.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from .config import Config
from .llm import LLM
from .models import DownstreamAsset, EntityType, Owner, PullRequestRef
from .pipeline import analyze
from .reporter import MARKER, render_markdown, to_json


# --------------------------------------------------------------------------
# lineage sources
# --------------------------------------------------------------------------
def load_fixture(path: str) -> dict[str, list[DownstreamAsset]]:
    """A JSON map: dataset -> [ {urn,name,type,platform,degree,is_production,owners[]} ]."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    out: dict[str, list[DownstreamAsset]] = {}
    for dataset, assets in raw.items():
        out[dataset] = [
            DownstreamAsset(
                urn=a["urn"],
                name=a["name"],
                entity_type=EntityType(a.get("type", "OTHER")),
                platform=a.get("platform"),
                degree=int(a.get("degree", 1)),
                is_production=bool(a.get("is_production", False)),
                owners=[Owner(name=o) for o in a.get("owners", [])],
            )
            for a in assets
        ]
    return out


def _make_llm(cfg: Config) -> LLM:
    return LLM(provider=cfg.llm_provider, model=cfg.llm_model, api_key=cfg.llm_api_key)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def cmd_doctor(args) -> int:
    cfg = Config.load(args.config)
    from .datahub_client import DataHubClient

    client = DataHubClient(cfg.graphql_url, cfg.datahub_token, cfg.production_markers)
    try:
        report = client.doctor()
    except Exception as exc:  # noqa: BLE001 - doctor reports, never crashes hard
        print(f"❌ DataHub check failed: {exc}")
        return 1
    print("🧭 Pathfinder doctor")
    print(f"  GraphQL URL      : {report.get('graphql_url')}")
    print(f"  Authenticated as : {report.get('authenticated_as') or '(anonymous / token missing)'}")
    print(f"  Lineage query OK : {report.get('lineage_query_ok')}")
    ok = bool(report.get("lineage_query_ok"))
    print("✅ DataHub reachable and lineage schema matches." if ok else "⚠️  Lineage query shape mismatch — see above.")
    return 0 if ok else 1


def cmd_run(args) -> int:
    cfg = Config.load(args.config)
    llm = _make_llm(cfg)

    # 1) Gather changed (dataset, before, after) triples + PR context.
    if args.pr:
        pairs, pr = _collect_from_pr(cfg, args)
    elif args.before and args.after and args.dataset:
        with open(args.before, encoding="utf-8") as f:
            before = f.read()
        with open(args.after, encoding="utf-8") as f:
            after = f.read()
        pairs = [(args.dataset, before, after)]
        pr = PullRequestRef(repo=args.repo or "local/demo", number=args.number or 0,
                            title="local run", url=args.repo_url or "")
    else:
        print("run needs either --pr <url> or (--before --after --dataset)", file=sys.stderr)
        return 2

    # 2) Lineage source: fixture (offline) or live DataHub.
    if args.lineage_fixture:
        fixture = load_fixture(args.lineage_fixture)
        lineage = lambda ds: fixture.get(ds, [])  # noqa: E731
        resolve_urn = lambda ds: (fixture.get(ds) or [None])  # unused offline
    else:
        from .datahub_client import DataHubClient

        client = DataHubClient(cfg.graphql_url, cfg.datahub_token, cfg.production_markers)
        _urn_cache: dict[str, Optional[str]] = {}

        def _urn(ds: str) -> Optional[str]:
            if ds not in _urn_cache:
                _urn_cache[ds] = client.resolve_dataset(ds, cfg.default_platform, cfg.default_env)
            return _urn_cache[ds]

        def lineage(ds: str) -> list[DownstreamAsset]:
            urn = _urn(ds)
            return client.get_downstream(urn, cfg.max_hops) if urn else []

    # 3) Analyze.
    report = analyze(pairs, lineage, pr, llm=llm, dialect=args.dialect)
    # Flag changed datasets that aren't in DataHub, so the report says "cannot
    # assess" instead of a false "safe to merge" when lineage simply isn't there.
    if args.lineage_fixture:
        report.unresolved = [ds for ds, _, _ in pairs if ds not in fixture]
    else:
        report.unresolved = [ds for ds, _, _ in pairs if _urn(ds) is None]
    # The comment only claims a write-back when this invocation will actually do one.
    will_write_back = not args.dry_run and not args.lineage_fixture and not args.no_write_back
    md = render_markdown(report, wrote_back=will_write_back)
    print(md)

    # 4) Artifact.
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(to_json(report))
        print(f"\n[wrote JSON artifact -> {args.out}]", file=sys.stderr)

    # 5) Side effects (skipped on --dry-run).
    if not args.dry_run:
        if args.pr and not args.no_post:
            from .vcs import GitHub

            gh = GitHub(cfg.github_token)
            url = gh.upsert_comment(pr.repo, pr.number, md, MARKER)
            print(f"[posted PR comment -> {url}]", file=sys.stderr)
        if not args.lineage_fixture and not args.no_write_back:
            from .datahub_client import DataHubClient
            from .writeback import write_back

            client = DataHubClient(cfg.graphql_url, cfg.datahub_token, cfg.production_markers)
            for ds, _, _ in pairs:
                urn = client.resolve_dataset(ds, cfg.default_platform, cfg.default_env)
                if urn:
                    res = write_back(client, urn, report)
                    print(f"[wrote back to DataHub {ds}: {res}]", file=sys.stderr)

    # 6) Exit code so CI can block a merge.
    if cfg.fail_on_breaking and report.overall.value == "breaking":
        return 1
    return 0


def _collect_from_pr(cfg: Config, args) -> tuple[list[tuple[str, str, str]], PullRequestRef]:
    from .vcs import GitHub, parse_pr_url

    repo, number = parse_pr_url(args.pr)
    gh = GitHub(cfg.github_token)
    pr_json = gh.get_pr(repo, number)
    pr = gh.pr_ref(repo, number, pr_json)
    base_sha = (pr_json.get("base") or {}).get("sha")
    head_sha = (pr_json.get("head") or {}).get("sha")

    pairs: list[tuple[str, str, str]] = []
    for f in gh.changed_files(repo, number):
        path = f.get("filename", "")
        if not path.endswith(".sql"):
            continue
        before = gh.file_at(repo, path, base_sha) if f.get("status") != "added" else ""
        after = gh.file_at(repo, path, head_sha) if f.get("status") != "removed" else ""
        dataset = os.path.splitext(os.path.basename(path))[0]
        pairs.append((dataset, before, after))
    return pairs, pr


# --------------------------------------------------------------------------
# arg parsing
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pathfinder", description="Walk the path from a data change to everything it touches.")
    p.add_argument("--config", default="pathfinder.yml", help="path to pathfinder.yml (optional)")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="check DataHub connectivity + lineage schema")
    d.set_defaults(func=cmd_doctor)

    r = sub.add_parser("run", help="analyze a pull request or a local before/after pair")
    r.add_argument("--pr", help="GitHub PR url")
    r.add_argument("--before", help="local: path to the model before the change")
    r.add_argument("--after", help="local: path to the model after the change")
    r.add_argument("--dataset", help="local: model/table name (defaults from filename)")
    r.add_argument("--repo", help="local: owner/name for the report header")
    r.add_argument("--repo-url", dest="repo_url", help="local: repo url for write-back link")
    r.add_argument("--number", type=int, help="local: PR number for the report header")
    r.add_argument("--lineage-fixture", help="JSON blast-radius fixture (offline mode)")
    r.add_argument("--dialect", help="SQL dialect for parsing (e.g. snowflake, bigquery)")
    r.add_argument("--out", help="write the JSON report artifact to this path")
    r.add_argument("--dry-run", action="store_true", help="analyze + print only; no PR comment, no write-back")
    r.add_argument("--no-post", action="store_true", help="do not post the PR comment")
    r.add_argument("--no-write-back", action="store_true", help="do not write back to DataHub")
    r.set_defaults(func=cmd_run)
    return p


def _force_utf8() -> None:
    # Pathfinder prints emoji; Windows consoles default to cp1252 and would crash.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def main(argv: Optional[list[str]] = None) -> int:
    _force_utf8()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
