# Sample outputs

Real artifacts produced by Pathfinder (no hand-editing), so judges can evaluate
quality without running anything.

| File | What it shows |
|------|----------------|
| [`orders-rename-pr-comment.md`](orders-rename-pr-comment.md) | The PR comment for renaming `orders.customer_id` → `cust_id`: 6 downstream assets, 5 in production, incl. a prod ML model + its live deployment, with owners and a drafted fix. |
| [`orders-rename-report.json`](orders-rename-report.json) | The machine-readable report for the same change (what CI logs / other agents consume). |
| [`orders-compat-shim.sql`](orders-compat-shim.sql) | The drafted backward-compatible fix — keeps `customer_id` as an alias so nothing breaks during migration. |

Reproduce them:

```bash
pathfinder run \
  --before demo/changes/orders_before.sql \
  --after  demo/changes/orders_after.sql \
  --dataset orders \
  --lineage-fixture demo/lineage.json \
  --repo acme/warehouse --number 42 \
  --dry-run --out examples/orders-rename-report.json
```

The blast radius here comes from [`demo/lineage.json`](../demo/lineage.json) so the
example runs with no DataHub instance. In real use the same shape comes live from
DataHub's `searchAcrossLineage`.
