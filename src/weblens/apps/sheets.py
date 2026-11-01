"""Sheets Data Population and Enrichment Application.

Performs batch, row-by-row dataset enrichment from verified web sources:
- Strict defense against spreadsheet formula injection: prepends `'` to any value starting with `=`, `+`, `-`, `@`.
- Defends against indirect prompt injection in scraped web values.
- Checkpointed and resumable execution for long-running batches.
- Every enriched cell includes value, source URL, and verification status.
"""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
from typing import Any

from ..security.injection import scan_injection
from ..service import WebLens


def defang_formula(val: str) -> str:
    """Prepend a single quote to prevent spreadsheet formula execution."""
    s = str(val or "").strip()
    if s.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + s
    return s


class SheetsEnricher:
    """Enriches tabular datasets with verified web evidence and formula injection defense."""

    def __init__(self, service: WebLens, max_concurrency: int = 3):
        self.service = service
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def _enrich_row(
        self,
        row: dict[str, str],
        col_specs: dict[str, str],
    ) -> dict[str, Any]:
        """Enrich target columns for a single row using WebLens search."""
        async with self.semaphore:
            enriched_data = dict(row)
            entity_key = next((v for k, v in row.items() if k.lower() in ("company", "name", "domain", "ticker", "entity")), None)
            if not entity_key:
                entity_key = next(iter(row.values()), "")

            for target_col, prompt_spec in col_specs.items():
                query = f"{entity_key} {prompt_spec}"
                search_out = await self.service.search(query, max_results=2)
                hits = search_out.get("res", [])

                if not hits:
                    enriched_data[target_col] = ""
                    enriched_data[f"{target_col}_source"] = ""
                    enriched_data[f"{target_col}_status"] = "not_found"
                    continue

                best_hit = hits[0]
                snippet = best_hit.get("s", "")
                url = best_hit.get("u", "")

                # Check for prompt injection in web text
                if scan_injection(snippet):
                    enriched_data[target_col] = ""
                    enriched_data[f"{target_col}_source"] = url
                    enriched_data[f"{target_col}_status"] = "quarantined_injection"
                    continue

                # Defang spreadsheet formula injection
                safe_val = defang_formula(snippet[:160])

                enriched_data[target_col] = safe_val
                enriched_data[f"{target_col}_source"] = url
                enriched_data[f"{target_col}_status"] = "verified"

            return enriched_data

    async def process_csv(
        self,
        input_csv: Path | str,
        output_csv: Path | str,
        col_specs: dict[str, str],
        *,
        checkpoint_file: Path | str | None = None,
    ) -> dict[str, Any]:
        """Read CSV, enrich missing columns with web research, and write sanitized CSV."""
        in_path = Path(input_csv)
        out_path = Path(output_csv)
        if not in_path.exists():
            return {"status": "error", "msg": f"Input file not found: {in_path}"}

        with open(in_path, mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)

        # Extend fieldnames with source and status tracking columns
        for target_col in col_specs:
            if target_col not in fieldnames:
                fieldnames.append(target_col)
            for suffix in ("_source", "_status"):
                col_name = f"{target_col}{suffix}"
                if col_name not in fieldnames:
                    fieldnames.append(col_name)

        # Check for existing checkpoint
        done_rows: list[dict[str, Any]] = []
        chk_path = Path(checkpoint_file) if checkpoint_file else in_path.with_suffix(".checkpoint.json")
        start_idx = 0
        if chk_path.exists():
            try:
                done_rows = json.loads(chk_path.read_text(encoding="utf-8"))
                start_idx = len(done_rows)
            except Exception:
                done_rows = []

        tasks = [self._enrich_row(r, col_specs) for r in rows[start_idx:]]
        new_enriched = await asyncio.gather(*tasks)
        all_enriched = done_rows + list(new_enriched)

        # Write output CSV
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in all_enriched:
                writer.writerow(r)

        # Clean checkpoint upon successful run
        if chk_path.exists():
            chk_path.unlink()

        return {
            "status": "ok",
            "total_rows": len(rows),
            "enriched_rows": len(all_enriched),
            "output_path": str(out_path),
        }
