# Pathfinder — Build Plan

**Hackathon:** Build with DataHub: The Agent Hackathon · **Deadline:** 2026-08-10 22:00 GMT+1
**Entering under:** Challenge #3 (Production ML Agents) — naturally spans #1 (agent doing real work + write-back) and #2 (metadata-aware code generation).

## The one-line pitch
A pull-request agent that walks DataHub's cross-stack lineage graph to catch breaking data changes — including breakage to **production ML models** — before they merge, drafts the fix, and writes the assessment back to the catalog.

## Why it can win
- **Proven PMF:** Atlan (`atlanhq/atlan-action`) and Datafold sell the dbt-only version for money.
- **Proven winning shape:** GitLab AI Hackathon 2026 grand prizes (Gitdefender, GraphDev) were "impact-analysis + fix inside the PR." Judges rewarded: inside-the-workflow, generates-the-fix, human-in-the-loop.
- **Whitespace:** those winners mapped *code* deps. Nobody pointed it at a *data lineage graph with ML models*. DataHub uniquely enables cross-stack column lineage (dbt + BI + ML) — the exact gap dbt/Recce have.
- **Originality guard:** the differentiation is the ML + cross-stack + write-back depth, NOT the PR-comment mechanic.

## Architecture (all implemented in `pathfinder/`)
```
change_extractor  SQL/dbt diff → typed column & filter changes      [DONE, tested]
datahub_client    GraphQL searchAcrossLineage → cross-stack + ML blast radius
classifier        deterministic severity + rationale                [DONE, tested]
remediation       backward-compatible fix generation (Challenge #2) [DONE]
reporter          PR comment markdown + JSON artifact               [DONE]
writeback         addLink/addTag back to DataHub (Challenge #1)     [DONE]
vcs               GitHub: read PR SQL, post/patch comment           [DONE]
pipeline + cli    doctor / run (--pr | --before/--after) + fixtures [DONE]
```
Rules **decide**; the LLM only **narrates** → deterministic, works with no API key, easy to test.

## 9-day plan
| Day | Milestone | State |
|-----|-----------|-------|
| 1 | Repo scaffold, Apache-2.0, core models/config, **change extractor + classifier proven by tests**, end-to-end offline run producing real `examples/` output | ✅ done |
| 2 | DataHub quickstart (Docker) + seed the demo stack (dbt models + 2 dashboards + feature→model→deployment). `pathfinder doctor` green against live GraphQL. | next |
| 3 | Wire `datahub_client.get_downstream` against the live graph; confirm ML entities appear in the blast radius. Replace fixture with live lineage in the demo. | |
| 4 | Live `--pr` path end-to-end on a real test PR (GitHub → analyze → comment). | |
| 5 | Write-back verified in the DataHub UI (link + tag on the changed column). | |
| 6 | Remediation polish + owner notifications; LLM narration wired (Claude). | |
| 7 | GitHub Action packaging; `examples/` expanded (drop, type-change, filter cases). | |
| 8 | README/docs polish, one-command demo, record the 3-min video. | |
| 9 | Buffer + video edit + Devpost submission (repo URL, description, feedback survey). | |

## Bonus (rewarded): open-source contribution
Contribute a **Pathfinder "impact-analysis" Skill** to DataHub's open Skills Registry (and/or a docs PR for the GraphQL lineage-in-CI pattern).

## Demo filming plan (de-risked)
Film the **CLI path**, not the cloud Action (GitHub runners can't reach a laptop DataHub):
local DataHub (Docker, seeded) → open a real PR on a public demo repo → `pathfinder run --pr <url>` → the comment posts to the real PR + the write-back shows in the DataHub UI. No tunneling.

## Open risks
- `searchAcrossLineage` field shapes vary slightly by DataHub version → `pathfinder doctor` catches drift on Day 2 before we rely on it.
- Column-level lineage granularity in the seed → if column-level is unavailable, table-level still produces a correct (slightly broader) blast radius.
