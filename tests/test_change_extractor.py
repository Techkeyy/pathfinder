"""Unit tests for the SQL change extractor — runnable without DataHub."""

from pathfinder.change_extractor import diff_model, light_render, parse_shape
from pathfinder.models import ChangeType


def _types(changes):
    return sorted(c.change_type for c in changes)


def test_detects_rename():
    before = "select id, customer_id as customer_id, amount from orders"
    after = "select id, customer_id as cust_id, amount from orders"
    changes = diff_model("orders", before, after)
    rn = [c for c in changes if c.change_type is ChangeType.RENAME]
    assert len(rn) == 1
    assert rn[0].before == "customer_id" and rn[0].after == "cust_id"


def test_detects_drop():
    before = "select id, email, amount from orders"
    after = "select id, amount from orders"
    changes = diff_model("orders", before, after)
    assert ChangeType.DROP_COLUMN in _types(changes)
    dropped = [c for c in changes if c.change_type is ChangeType.DROP_COLUMN]
    assert dropped[0].column == "email"


def test_detects_add_is_not_breaking_type():
    before = "select id, amount from orders"
    after = "select id, amount, discount from orders"
    changes = diff_model("orders", before, after)
    assert _types(changes) == [ChangeType.ADD_COLUMN]


def test_detects_filter_change():
    before = "select id, amount from orders where status = 'paid'"
    after = "select id, amount from orders where status = 'paid' and region = 'US'"
    changes = diff_model("orders", before, after)
    assert ChangeType.FILTER_CHANGE in _types(changes)


def test_detects_type_change():
    before = "select id, cast(amount as int) as amount from orders"
    after = "select id, cast(amount as float) as amount from orders"
    changes = diff_model("orders", before, after)
    assert ChangeType.TYPE_CHANGE in _types(changes)


def test_light_render_strips_dbt_jinja():
    sql = "select id from {{ ref('stg_orders') }} where x = {{ var('y') }}"
    rendered = light_render(sql)
    assert "{{" not in rendered and "stg_orders" in rendered


def test_dbt_model_parses_via_light_render():
    before = "{{ config(materialized='table') }}\nselect id, customer_id as customer_id from {{ ref('stg_orders') }}"
    after = "{{ config(materialized='table') }}\nselect id, customer_id as cust_id from {{ ref('stg_orders') }}"
    changes = diff_model("orders", before, after)
    assert ChangeType.RENAME in _types(changes)


def test_no_false_positive_on_identical():
    sql = "select id, customer_id as cust_id, amount from orders where status = 'paid'"
    assert diff_model("orders", sql, sql) == []


def test_star_projection_is_recorded():
    shape = parse_shape("select * from orders")
    assert "*" in shape.columns
