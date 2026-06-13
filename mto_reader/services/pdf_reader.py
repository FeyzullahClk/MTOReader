from __future__ import annotations

from typing import Callable

import pandas as pd
import pdfplumber

from mto_reader.models import ExtractedTable


def _normalize_text(value: object) -> object:
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return cleaned if cleaned else None
    return value


def _make_unique_headers(headers: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    unique_headers: list[str] = []

    for raw in headers:
        base = raw or "Column"
        count = counts.get(base, 0)
        if count == 0:
            unique = base
        else:
            unique = f"{base}_{count + 1}"
        counts[base] = count + 1
        unique_headers.append(unique)

    return unique_headers


def _table_to_dataframe(raw_table: list[list[object]]) -> pd.DataFrame | None:
    if not raw_table:
        return None

    frame = pd.DataFrame(raw_table)
    frame = frame.map(_normalize_text)

    # Remove rows and columns that contain no useful values.
    frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if frame.empty:
        return None

    header_values = [str(value) if value is not None else "" for value in frame.iloc[0].tolist()]
    headers = _make_unique_headers(header_values)

    data = frame.iloc[1:].reset_index(drop=True)
    data.columns = headers

    data = data.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if data.empty:
        return None

    return data


def parse_page_selection(page_selection: str, total_pages: int) -> list[int]:
    text = (page_selection or "").strip()
    if not text:
        return list(range(total_pages))

    pages: set[int] = set()
    parts = [part.strip() for part in text.split(",") if part.strip()]

    for part in parts:
        if "-" in part:
            start_text, end_text = part.split("-", maxsplit=1)
            start = int(start_text)
            end = int(end_text)
            if start > end:
                start, end = end, start
            for page in range(start, end + 1):
                if page < 1 or page > total_pages:
                    raise ValueError(f"Page {page} is outside 1-{total_pages}.")
                pages.add(page - 1)
        else:
            page = int(part)
            if page < 1 or page > total_pages:
                raise ValueError(f"Page {page} is outside 1-{total_pages}.")
            pages.add(page - 1)

    if not pages:
        raise ValueError("No valid pages selected.")

    return sorted(pages)


class PDFTableExtractor:
    def extract_tables(
        self,
        pdf_path: str,
        page_selection: str = "",
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[ExtractedTable]:
        extracted: list[ExtractedTable] = []

        with pdfplumber.open(pdf_path) as pdf:
            selected_page_indexes = parse_page_selection(page_selection, len(pdf.pages))

            for page_index in selected_page_indexes:
                page_number = page_index + 1
                page = pdf.pages[page_index]
                raw_tables = page.extract_tables() or []

                if progress_callback:
                    progress_callback(f"Scanning page {page_number}: found {len(raw_tables)} raw tables.")

                for raw_table in raw_tables:
                    frame = _table_to_dataframe(raw_table)
                    if frame is None:
                        continue
                    extracted.append(ExtractedTable(page_number=page_number, dataframe=frame))

        return extracted
