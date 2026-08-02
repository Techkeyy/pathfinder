{{ config(materialized='table') }}

-- Core orders model. Renamed `customer_id` -> `cust_id` for naming consistency.
select
    order_id,
    customer_id as cust_id,
    order_total,
    cast(order_ts as date) as order_date,
    status
from {{ ref('stg_orders') }}
where status = 'paid'
