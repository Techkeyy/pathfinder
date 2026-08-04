<!-- pathfinder-report -->
## 🧭 Pathfinder — 🔴 BREAKING

This PR affects **6 downstream assets** across your stack.

### `orders` — renamed `customer_id` -> `cust_id`
_renamed `customer_id` -> `cust_id`: touches 6 downstream assets, including 5 in PRODUCTION (customer_value, daily_orders, Exec Revenue). Treat as breaking._

| Sev | Downstream asset | Type | Owner | Why |
|-----|------------------|------|-------|-----|
| 🔴 | 🧬 customer_value **(PROD)** | MLFEATURE | @maria | consumes `customer_id` as a feature/schema input directly; renaming or dropping it breaks the model at serve time |
| 🔴 | 🗂️ daily_orders **(PROD)** | DATASET | @dana | reads `customer_id` directly; the reference will fail to resolve |
| 🔴 | 📊 Exec Revenue **(PROD)** | DASHBOARD | @finance-team | binds to `customer_id` by name 2 hops downstream; the tile will error or go blank |
| 🔴 | 🤖 churn_model **(PROD)** | MLMODEL | @maria | consumes `customer_id` as a feature/schema input 2 hops downstream; renaming or dropping it breaks the model at serve time |
| 🔴 | 🚀 churn_model (serving) **(PROD)** | MLMODEL_DEPLOYMENT | @maria | consumes `customer_id` as a feature/schema input 2 hops downstream; renaming or dropping it breaks the model at serve time |
| 🟠 | 🗂️ ltv_calc **(PROD)** | DATASET | @dana | depends on `customer_id` 2 hops downstream but an intermediate model may shield it — verify |

### 🛠 Suggested fix
**Compatibility alias for orders.customer_id** — Add `cust_id as customer_id` so existing references to `customer_id` keep resolving.

```sql
-- Pathfinder shim for `orders`: keep `customer_id` available while consumers
-- migrate to `cust_id`. Remove after all downstream owners have moved.
select
    *,
    cust_id as customer_id  -- deprecated alias
from {{ ref('orders') }}
```

**Owners to notify:** @dana @finance-team @maria

<sub>Pathfinder walked your DataHub lineage graph. Verdicts are deterministic; rationale may be LLM-assisted.</sub>
