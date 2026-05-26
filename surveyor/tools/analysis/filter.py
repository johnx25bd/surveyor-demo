"""filter — refine a dataset against a constrained expression over its own columns.

Not free SQL and never sent upstream (architecture §7): a sequence of ``col OP value`` comparisons
over the dataset's own columns, joined by a single ``and``/``or``. Columns are validated against
the dataset; values are numbers or quoted strings. Keeps matching rows (table) or features (geo).
"""

from __future__ import annotations

import operator
import re
from typing import Any, Callable

from pydantic import BaseModel, Field

from ...data.models import GeoDataset, TableDataset, describe
from ..base import ToolContext, ToolOutcome

_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "<=": operator.le,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "=": operator.eq,
}
_CLAUSE = re.compile(r"^\s*([A-Za-z_]\w*)\s*(<=|>=|==|!=|<|>|=)\s*(.+?)\s*$")


def _literal(raw: str) -> Any:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] in "'\"" and raw[-1] == raw[0]:
        return raw[1:-1]
    for cast in (int, float):
        try:
            return cast(raw)
        except ValueError:
            continue
    return raw


def _parse(where: str) -> tuple[str, list[tuple[str, Callable[[Any, Any], bool], Any]]]:
    connective = "or" if (" or " in where and " and " not in where) else "and"
    clauses = []
    for part in re.split(rf"\s+{connective}\s+", where):
        m = _CLAUSE.match(part)
        if not m:
            raise ValueError(f"cannot parse filter clause {part!r}; use 'col <op> value'")
        clauses.append((m.group(1), _OPS[m.group(2)], _literal(m.group(3))))
    return connective, clauses


def _matches(props: dict, connective: str, clauses: list) -> bool:
    outcomes = []
    for col, fn, val in clauses:
        actual = props.get(col)
        try:
            outcomes.append(actual is not None and fn(actual, val))
        except TypeError:
            outcomes.append(False)
    return all(outcomes) if connective == "and" else any(outcomes)


class FilterInput(BaseModel):
    dataset: str = Field(..., description="Handle of the dataset to filter.")
    where: str = Field(
        ..., description="e.g. 'IMDDec0 <= 3' or \"description = 'Health Centre'\"."
    )


class Filter:
    name = "filter"
    description = (
        "Refine a dataset by a constrained expression over its own columns — `col OP value` "
        "comparisons joined by a single 'and'/'or' (OP in <, <=, >, >=, ==, !=). Keeps matching "
        "rows (table) or features (geo). Not SQL; validated against the dataset's columns."
    )
    Input = FilterInput

    def run(self, ctx: ToolContext, args: FilterInput) -> ToolOutcome:
        ds = ctx.store.get(args.dataset)
        connective, clauses = _parse(args.where)

        if isinstance(ds, TableDataset):
            known = set(ds.rows[0]) if ds.rows else set()
            self._check_columns(clauses, known)
            kept = [r for r in ds.rows if _matches(r, connective, clauses)]
            out: TableDataset | GeoDataset = TableDataset(
                rows=kept, key_column=ds.key_column, value_columns=ds.value_columns
            )
        elif isinstance(ds, GeoDataset):
            feats = ds.features.get("features", [])
            known = set(feats[0].get("properties", {})) if feats else set()
            self._check_columns(clauses, known)
            kept = [f for f in feats if _matches(f.get("properties", {}), connective, clauses)]
            out = GeoDataset(
                features={"type": "FeatureCollection", "features": kept},
                crs=ds.crs,
                geometry_type=ds.geometry_type,
                key_property=ds.key_property,
                name_property=ds.name_property,
            )
        else:
            raise ValueError("filter needs a table or geo dataset")

        handle = ctx.store.put(out)
        ctx.sink.emit(
            "status", {"state": f"filtered '{args.where}': {out.count} of {ds.count} kept"}
        )
        return ToolOutcome(descriptor=describe(handle, out))

    @staticmethod
    def _check_columns(clauses: list, known: set) -> None:
        for col, _, _ in clauses:
            if known and col not in known:
                raise ValueError(f"unknown column {col!r}; available: {sorted(known)}")
