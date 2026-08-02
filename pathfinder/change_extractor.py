"""Turn a raw SQL diff into structured, typed changes.

Given the *before* and *after* text of a model, we work out which output
columns were renamed / dropped / added, whether a column's producing expression
changed, and whether the row-set filter (WHERE/QUALIFY) changed. Those typed
changes are what the lineage walk and the classifier reason about.

Design choices for robustness (so a weird file never crashes a PR run):
* We lightly de-Jinja dbt syntax (``{{ ref('x') }}`` -> ``x``) before parsing.
* If ``sqlglot`` cannot parse a file, we fall back to a naive alias diff instead
  of raising.
"""

from __future__ import annotations

import re
from typing import Optional

from .models import ChangeType, ColumnChange

try:
    import sqlglot
    from sqlglot import exp
except Exception:  # pragma: no cover
    sqlglot = None  # type: ignore
    exp = None  # type: ignore


# --- dbt / Jinja light rendering ------------------------------------------
_REF_RE = re.compile(r"{{\s*ref\(\s*['\"]([^'\"]+)['\"]\s*\)\s*}}")
_SOURCE_RE = re.compile(r"{{\s*source\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*}}")
_CONFIG_RE = re.compile(r"{{\s*config\([^}]*\)\s*}}", re.DOTALL)
_ANY_JINJA_RE = re.compile(r"{{.*?}}|{%.*?%}", re.DOTALL)


def light_render(sql: str) -> str:
    """Replace the common dbt macros with plain identifiers so SQL parses."""
    sql = _CONFIG_RE.sub("", sql)
    sql = _REF_RE.sub(lambda m: m.group(1), sql)
    sql = _SOURCE_RE.sub(lambda m: f"{m.group(1)}.{m.group(2)}", sql)
    # Anything else Jinja becomes a harmless literal so the statement still parses.
    sql = _ANY_JINJA_RE.sub("NULL", sql)
    return sql


class ModelShape:
    """The parts of a model we compare across versions."""

    def __init__(self, columns: dict[str, str], where_sql: Optional[str], parsed: bool):
        # ordered map: output column name -> normalized producing expression SQL
        self.columns = columns
        self.where_sql = where_sql
        self.parsed = parsed  # False => produced by the naive fallback


def _normalize(expression) -> str:
    try:
        return expression.sql(normalize=True, comments=False).lower()
    except Exception:
        return str(expression).lower()


def _underlying(proj):
    """The value-producing expression with its output alias stripped.

    We compare *how a column is computed*, not what it is named — otherwise a
    pure rename (same expression, new alias) would look like a drop + add.
    """
    if exp is not None and isinstance(proj, exp.Alias):
        return proj.this
    return proj


def parse_shape(sql: str, dialect: Optional[str] = None) -> ModelShape:
    """Extract output columns + filter from one model's SQL."""
    rendered = light_render(sql)
    if sqlglot is not None:
        try:
            tree = sqlglot.parse_one(rendered, read=dialect)
            select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
            if select is not None:
                columns: dict[str, str] = {}
                for proj in select.selects:
                    name = proj.alias_or_name
                    if not name or name == "*":
                        # star-projection: record it so we can flag "cannot analyze".
                        columns.setdefault("*", "*")
                        continue
                    columns[name] = _normalize(_underlying(proj))
                where = select.args.get("where")
                qualify = select.args.get("qualify")
                where_sql = None
                parts = [p for p in (where, qualify) if p is not None]
                if parts:
                    where_sql = " and ".join(_normalize(p) for p in parts)
                return ModelShape(columns, where_sql, parsed=True)
        except Exception:
            pass
    return _naive_shape(rendered)


def _naive_shape(sql: str) -> ModelShape:
    """Fallback: pull ``expr AS name`` aliases with a regex; no filter analysis."""
    columns: dict[str, str] = {}
    for m in re.finditer(r"(?i)\bas\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", sql):
        columns[m.group(1).lower()] = m.group(0).lower()
    return ModelShape(columns, where_sql=None, parsed=False)


def _cast_type(expr_sql: str) -> Optional[str]:
    m = re.search(r"cast\([^)]*as\s+([a-zA-Z0-9_]+)", expr_sql)
    return m.group(1) if m else None


def diff_model(dataset: str, before_sql: str, after_sql: str,
               dialect: Optional[str] = None) -> list[ColumnChange]:
    """Compare two versions of a model and return typed column/model changes."""
    before = parse_shape(before_sql, dialect)
    after = parse_shape(after_sql, dialect)

    before_cols = {k.lower(): v for k, v in before.columns.items() if k != "*"}
    after_cols = {k.lower(): v for k, v in after.columns.items() if k != "*"}

    dropped = [c for c in before_cols if c not in after_cols]
    added = [c for c in after_cols if c not in before_cols]
    changes: list[ColumnChange] = []

    # --- rename detection: a dropped column whose expression reappears under a
    # new name is a rename, not a drop+add. Match on identical producing SQL. ---
    used_added: set[str] = set()
    still_dropped: list[str] = []
    for d in dropped:
        match = next(
            (a for a in added if a not in used_added and before_cols[d] and before_cols[d] == after_cols.get(a)),
            None,
        )
        if match:
            used_added.add(match)
            changes.append(ColumnChange(
                dataset=dataset, column=d, change_type=ChangeType.RENAME,
                detail=f"renamed `{d}` -> `{match}`", before=d, after=match,
            ))
        else:
            still_dropped.append(d)

    for d in still_dropped:
        changes.append(ColumnChange(
            dataset=dataset, column=d, change_type=ChangeType.DROP_COLUMN,
            detail=f"dropped column `{d}`", before=d, after=None,
        ))

    for a in added:
        if a in used_added:
            continue
        changes.append(ColumnChange(
            dataset=dataset, column=a, change_type=ChangeType.ADD_COLUMN,
            detail=f"added column `{a}`", before=None, after=a,
        ))

    # --- expression / type changes for columns present in both versions ---
    for c in before_cols:
        if c in after_cols and before_cols[c] != after_cols[c]:
            bt, at = _cast_type(before_cols[c]), _cast_type(after_cols[c])
            if bt and at and bt != at:
                changes.append(ColumnChange(
                    dataset=dataset, column=c, change_type=ChangeType.TYPE_CHANGE,
                    detail=f"type of `{c}` changed {bt} -> {at}", before=bt, after=at,
                ))
            else:
                changes.append(ColumnChange(
                    dataset=dataset, column=c, change_type=ChangeType.LOGIC_CHANGE,
                    detail=f"logic producing `{c}` changed", before=before_cols[c], after=after_cols[c],
                ))

    # --- filter / row-set change (model-level) ---
    if before.parsed and after.parsed and (before.where_sql or after.where_sql):
        if (before.where_sql or "") != (after.where_sql or ""):
            changes.append(ColumnChange(
                dataset=dataset, column=None, change_type=ChangeType.FILTER_CHANGE,
                detail="row filter (WHERE/QUALIFY) changed — output rows may differ",
                before=before.where_sql, after=after.where_sql,
            ))

    return changes
