"""normalize — divide one table's value by another's on the shared GSS key, writing a rate.

Joins numerator and denominator tables on the GSS code, divides their primary value columns, and
adds a ``rate`` column (optionally scaled by ``per``, e.g. per=10000 for 'per 10,000 residents').
Pure table arithmetic — no geometry. Both inputs' value columns are carried through for context.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ...data.models import TableDataset, describe
from ..base import ToolContext, ToolOutcome


class NormalizeInput(BaseModel):
    numerator: str = Field(..., description="Handle of the numerator table (e.g. counts).")
    denominator: str = Field(..., description="Handle of the denominator table (e.g. population).")
    per: float | None = Field(
        None, description="Optional scale, e.g. 10000 → 'per 10,000'. Omit for a raw ratio."
    )


class Normalize:
    name = "normalize"
    description = (
        "Join two tables on GSS code and divide the numerator's primary value by the "
        "denominator's, writing a 'rate' column (optionally × per, e.g. per=10000 for "
        "'per 10,000'). Boundaries with a zero/absent denominator get a null rate."
    )
    Input = NormalizeInput

    def run(self, ctx: ToolContext, args: NormalizeInput) -> ToolOutcome:
        num = ctx.store.get(args.numerator)
        den = ctx.store.get(args.denominator)
        if not isinstance(num, TableDataset) or not isinstance(den, TableDataset):
            raise ValueError("normalize needs two tables: numerator and denominator")
        if not num.value_columns or not den.value_columns:
            raise ValueError("both tables need at least one value column to normalize")

        num_col = num.value_columns[0]
        den_col = den.value_columns[0]
        den_map = {r[den.key_column]: r for r in den.rows}

        scale = args.per if args.per is not None else 1.0
        per_label = f" per {int(args.per):,}" if args.per is not None else ""
        ctx.sink.emit("status", {"state": f"normalizing {num_col} / {den_col}{per_label}"})

        rows = []
        for r in num.rows:
            code = r[num.key_column]
            d = den_map.get(code)
            den_val = d[den_col] if d else None
            num_val = r[num_col]
            rate = (num_val / den_val * scale) if den_val else None
            rows.append(
                {
                    "code": code,
                    "name": r.get("name") or (d.get("name") if d else None),
                    num_col: num_val,
                    den_col: den_val,
                    "rate": rate,
                }
            )

        value_columns = [num_col, den_col, "rate"]
        dataset = TableDataset(rows=rows, key_column="code", value_columns=value_columns)
        handle = ctx.store.put(dataset)
        return ToolOutcome(descriptor=describe(handle, dataset))
