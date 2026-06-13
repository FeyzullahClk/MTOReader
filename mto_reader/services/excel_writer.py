from __future__ import annotations

from pathlib import Path

import pandas as pd

from mto_reader.models import ExtractedTable


def export_tables_to_excel(
    tables: list[ExtractedTable],
    output_path: str,
    sheet_name: str = "MTO",
) -> None:
    if not tables:
        raise ValueError("No tables were extracted from the PDF.")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    merged_frames: list[pd.DataFrame] = []
    for index, table in enumerate(tables, start=1):
        frame = table.dataframe.copy()
        frame.insert(0, "SourcePage", table.page_number)
        frame.insert(1, "SourceTable", index)
        merged_frames.append(frame)

    merged = pd.concat(merged_frames, ignore_index=True)
    safe_sheet_name = (sheet_name or "MTO")[:31]

    page_numbers = sorted({table.page_number for table in tables})
    summary = pd.DataFrame(
        {
            "Metric": ["TotalTables", "TotalRows", "Pages"],
            "Value": [len(tables), len(merged), ", ".join(map(str, page_numbers))],
        }
    )

    with pd.ExcelWriter(destination, engine="openpyxl") as writer:
        merged.to_excel(writer, sheet_name=safe_sheet_name, index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)
