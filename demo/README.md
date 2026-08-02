# Demo

Two ways to see Pathfinder work.

## A) Offline (no DataHub) — works right now

Uses a checked-in blast-radius fixture, so anyone can run it in seconds:

```bash
pip install -e ..
pathfinder run \
  --before changes/orders_before.sql \
  --after  changes/orders_after.sql \
  --dataset orders --lineage-fixture lineage.json --dry-run
```

## B) Live DataHub — the full loop (used for the video)

```bash
./up.sh                 # 1. start DataHub locally (Docker) + seed the demo stack
pathfinder doctor       # 2. confirm GraphQL + lineage schema
                        # 3. open a PR renaming a column, then:
pathfinder run --pr https://github.com/<you>/<demo-repo>/pull/<n>
```

Step 3 posts the comment to the real PR **and** writes the assessment back onto
the changed column in the DataHub UI (Documentation → Links + a
`pathfinder-reviewed` tag).

### The seeded stack

`seed.py` emits a small but complete cross-stack graph so the blast radius spans
tables **and** ML:

```
stg_orders → orders → daily_orders → Exec Revenue (Looker dashboard)
                    → ltv_calc
             orders → customer_value (ML feature) → churn_model (ML model) → churn_model (SageMaker deployment)
```

Ownership: `dana@acme.com` (analytics), `maria@acme.com` (ML), `finance-team` (BI).
This mirrors [`lineage.json`](lineage.json) so offline and live demos tell the
same story.
