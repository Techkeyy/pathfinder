{{ config(materialized='table') }}

-- Core orders model. `customer_id` is the join key everything downstream uses.
select
    order_id,
    customer_id as customer_id,
    order_total,
    cast(order_ts as date) as order_date,
    status
from {{ ref('stg_orders') }}
where status = 'paid'
