"""rank — sort a table by a column, optionally keeping the top N. Drives the ranked chart."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ...data.models import TableDataset, describe
from ..base import ToolContext, ToolOutcome


class RankInput(BaseModel):
    table: str = Field(..., description="Handle of the table to rank.")
    by: str = Field(..., description="Column to sort by, e.g. 'rate'.")
    order: str = Field("desc", description="'desc' (default) or 'asc'.")
    top_n: int | None = Field(None, ge=1, description="Optionally keep only the top N rows.")


class Rank:
    name = "rank"
    description = (
        "Sort a table by a column (order 'desc' or 'asc') and optionally keep the top N rows. "
        "Rows with a missing sort value sort last."
    )
    Input = RankInput

    def run(self, ctx: ToolContext, args: RankInput) -> ToolOutcome:
        table = ctx.store.get(args.table)
        if not isinstance(table, TableDataset):
            raise ValueError("rank needs a table")
        if table.rows and args.by not in table.rows[0]:
            raise ValueError(f"unknown column {args.by!r}; available: {sorted(table.rows[0])}")
        if args.order not in {"asc", "desc"}:
            raise ValueError(f"order must be 'asc' or 'desc', got {args.order!r}")

        reverse = args.order == "desc"
        valued = [r for r in table.rows if r.get(args.by) is not None]
        missing = [r for r in table.rows if r.get(args.by) is None]
        valued.sort(key=lambda r: r[args.by], reverse=reverse)
        ranked = valued + missing
        if args.top_n is not None:
            ranked = ranked[: args.top_n]

        dataset = TableDataset(
            rows=ranked, key_column=table.key_column, value_columns=table.value_columns
        )
        handle = ctx.store.put(dataset)
        limit = f", top {args.top_n}" if args.top_n is not None else ""
        ctx.sink.emit(
            "status", {"state": f"ranked {len(table.rows)} rows by {args.by} ({args.order}){limit}"}
        )
        return ToolOutcome(descriptor=describe(handle, dataset))
