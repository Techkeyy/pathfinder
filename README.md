# 🧭 Pathfinder

**Walk the path from a data change to everything it touches — before you break it.**

Pathfinder is a pull-request agent for data teams. When someone opens a PR that
changes a data model, Pathfinder reads [DataHub's](https://datahub.com) cross-stack
lineage graph — tables → dashboards → **ML features → ML models** —
and answers the question every data engineer dreads at 3am:

> *"If I change this column, what silently breaks, and who do I need to tell?"*

It posts the answer **as a comment on the PR**, drafts a backward-compatible fix,
notifies the downstream owners, and **writes the assessment back into DataHub** so
the next person (or agent) inherits the knowledge instead of relearning it the
hard way.

> Built for [**Build with DataHub: The Agent Hackathon**](https://datahub.devpost.com/)
> — Challenge #3, Production ML Agents (spans #1 and #2).

---

## Why this exists

Tools like dbt docs and Recce show impact analysis **inside the dbt project** — they
stop at the edge. They can't see the Looker dashboard or the production ML model
that reads the column you're about to rename. Atlan and Datafold sell the
cross-tool version, closed and commercial.

DataHub already holds the one thing that makes this solvable in the open: a
**column-level lineage graph that spans the whole stack, including ML**. Pathfinder
turns that graph into a guardrail that lives where engineers already work.

```
            YOUR CHANGE                    dbt / Recce see this
        orders.customer_id  ──►  daily_orders ──►  ltv_calc
                    │                                  │
                    │            ── only DataHub sees this ──
                    ▼                                  ▼
           📊 Exec Revenue Dashboard        🧬 ml_feature: customer_value
                                                       │
                                                       ▼
                                              🤖 churn_model  (serving in production)
```

## What it does

1. **Detects the change** — diffs the SQL/dbt in the PR to find renamed, dropped,
   retyped columns and changed row filters (via `sqlglot`).
2. **Walks the blast radius** — one DataHub GraphQL `searchAcrossLineage` call
   returns every downstream dataset, dashboard, ML feature, and ML model, plus
   each one's owner.
3. **Judges severity** — deterministic rules classify each downstream asset as
   🔴 breaking / 🟠 partial / 🟢 safe (a production ML model outranks an internal
   table). The rationale is deterministic too; an optional LLM only polishes the
   drafted fix, so Pathfinder runs fully without an API key.
4. **Drafts the fix** — generates a backward-compatible shim (e.g. keep the old
   column name as an alias) so nothing breaks while you migrate.
5. **Reports + notifies** — posts a PR comment and @-mentions affected owners.
6. **Writes back** — annotates the changed dataset in DataHub with the verdict and
   a link to the PR.

## Quickstart

```bash
pip install -e .

# 1. Point Pathfinder at your DataHub + GitHub
export DATAHUB_GMS_URL=http://localhost:8080
export DATAHUB_GMS_TOKEN=...      # DataHub personal access token
export GITHUB_TOKEN=...           # to post the PR comment
export ANTHROPIC_API_KEY=...      # optional: nicer prose + drafted fix

# 2. Confirm the lineage graph is reachable and the schema matches
pathfinder doctor

# 3. Analyze a pull request (CLI mode — great for demos)
pathfinder run --pr https://github.com/acme/warehouse/pull/42
```

Or run it as CI on every PR — see [`action.yml`](action/action.yml).

## Try the demo — one click, reproducible (GitHub Codespaces)

DataHub needs Linux + Docker and ~8 GB RAM, so the demo runs in a Codespace with
everything pre-wired (a committed [`.devcontainer`](.devcontainer/devcontainer.json)).

1. **Code ▸ Codespaces ▸ Create codespace on `main`** (pick the 4-core / 16 GB machine).
   The devcontainer installs Pathfinder + the DataHub CLI automatically.
2. Boot DataHub and seed the demo graph (tables → dashboard → ML feature → ML model):
   ```bash
   bash demo/up.sh          # first run pulls images, ~5-10 min
   ```
3. Confirm the live lineage schema, then run Pathfinder against the seeded change:
   ```bash
   pathfinder doctor
   pathfinder run --before demo/changes/orders_before.sql \
                  --after  demo/changes/orders_after.sql --dataset orders
   ```
   DataHub's UI is on forwarded port **9002** (login `datahub` / `datahub`); you'll
   see Pathfinder's write-back appear on the `analytics.orders` column.

**No Codespace?** The full pipeline also runs offline against a lineage fixture —
no DataHub needed — which is how the sample below was generated:

```bash
pip install -e .
pathfinder run --before demo/changes/orders_before.sql \
               --after  demo/changes/orders_after.sql \
               --dataset orders --lineage-fixture demo/lineage.json --dry-run
```

Sample outputs judges can read without running anything are in
[`examples/`](examples/).

## Architecture

| Module | Job |
|---|---|
| `change_extractor.py` | SQL/dbt diff → typed column & filter changes |
| `datahub_client.py` | GraphQL lineage walk → the cross-stack + ML blast radius |
| `classifier.py` | Deterministic severity + rationale (no LLM) |
| `remediation.py` | Backward-compatible fix generation |
| `reporter.py` | PR comment + owner notifications |
| `writeback.py` | Annotate the change back into DataHub |
| `cli.py` | `doctor`, `run`, demo entry points |

## License

[Apache 2.0](LICENSE).
