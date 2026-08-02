# Pathfinder — MVP definition

## The single demo that must work (the video)
Open a PR that renames `orders.customer_id` → `cust_id`. Pathfinder comments on
the PR:

> 🔴 **BREAKING** — 6 downstream assets, 5 in PRODUCTION, including 🤖 `churn_model`
> (prod ML model, @maria) and its 🚀 live serving deployment. Suggested fix:
> keep `customer_id` as a deprecated alias. Owners notified. Written back to DataHub.

This already runs today, end-to-end, offline:
```bash
pathfinder run --before demo/changes/orders_before.sql \
               --after  demo/changes/orders_after.sql \
               --dataset orders --lineage-fixture demo/lineage.json --dry-run
```
Real output is checked in at [`examples/orders-rename-pr-comment.md`](examples/orders-rename-pr-comment.md).

## In scope for MVP
- [x] Detect rename / drop / add / type-change / filter-change from SQL+dbt (tested)
- [x] Deterministic severity (breaking/partial/safe), ML + prod aware (tested)
- [x] Cross-stack blast radius incl. ML feature/model/deployment (via GraphQL / fixture)
- [x] PR comment with per-asset table + owners
- [x] Backward-compatible fix generation
- [x] JSON artifact for `examples/`
- [x] Write-back to DataHub (link + tag)
- [x] `--pr` (live) and `--before/--after` (offline) modes
- [ ] Verified against a live seeded DataHub (Day 2–3)
- [ ] GitHub Action packaging verified in CI (Day 4, 7)

## Out of scope (post-hackathon)
- Column-level lineage precision beyond what DataHub exposes
- Multi-warehouse SQL dialect edge cases
- A hosted SaaS / web dashboard
- Auto-applying the fix (we suggest; a human merges — deliberate)

## Definition of done for submission
Public Apache-2.0 repo · <3-min video · README with setup · `examples/` with
sample outputs · `pathfinder doctor` green against the seeded DataHub · live
`--pr` run posting a real comment.
