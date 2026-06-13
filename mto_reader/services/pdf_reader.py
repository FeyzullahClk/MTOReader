from __future__ import annotations

from typing import Callable

import pandas as pd
import pdfplumber

from mto_reader.models import ExtractedTable

# pdfplumber table settings optimised for CAD/engineering vector PDFs
# where table borders are actual drawn lines.
_ENGINEERING_TABLE_SETTINGS: dict = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
    "min_words_vertical": 1,
    "min_words_horizontal": 1,
}

# Keywords that must all appear (case-insensitive) in the first row of a table
# for it to be identified as a Rigging Material List.
_RIGGING_KEYWORDS: tuple[str, ...] = ("rigging", "material", "list")


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


def _is_rigging_table(raw_table: list[list[object]]) -> bool:
    """Return True when the first non-empty row contains the Rigging Material List title."""
    for row in raw_table[:3]:  # title is usually in the first few rows
        row_text = " ".join(str(cell).lower() for cell in row if cell is not None)
        if all(kw in row_text for kw in _RIGGING_KEYWORDS):
            return True
    return False


def _is_footer_row(row: pd.Series) -> bool:
    """Return True for summary/footer rows such as 'TOTAL WEIGHT'."""
    row_text = " ".join(str(v).lower() for v in row if pd.notna(v))
    return "total weight" in row_text


def _extract_title_from_raw(raw_table: list[list[object]]) -> str:
    """Return the title text from the spanning first row of a rigging table."""
    for row in raw_table[:3]:
        non_none = [str(c).strip() for c in row if c is not None]
        if not non_none:
            continue
        combined = " ".join(non_none)
        if all(kw in combined.lower() for kw in _RIGGING_KEYWORDS):
            return " ".join(combined.split())
    return "RIGGING MATERIAL LIST (OFFSHORE INSTALLATION)"


def _extract_total_weight_from_raw(raw_table: list[list[object]]) -> str:
    """Return the numeric total weight value string from the footer row."""
    for row in reversed(raw_table):
        row_text = " ".join(str(c).lower() for c in row if c is not None)
        if "total weight" in row_text:
            for cell in reversed(row):
                if cell is not None:
                    s = str(cell).strip()
                    try:
                        float(s.replace(",", ""))
                        return s
                    except ValueError:
                        continue
    return ""


def _table_to_dataframe(raw_table: list[list[object]]) -> pd.DataFrame | None:
    if not raw_table:
        return None

    frame = pd.DataFrame(raw_table)
    frame = frame.map(_normalize_text)

    # Remove rows and columns that contain no useful values.
    frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if frame.empty:
        return None

    # If this is a Rigging Material List the very first row is a spanning title.
    # Skip it and treat the next row as column headers.
    start_row = 0
    first_row_text = " ".join(
        str(v).lower() for v in frame.iloc[0].tolist() if v is not None
    )
    if all(kw in first_row_text for kw in _RIGGING_KEYWORDS):
        start_row = 1  # skip the title row

    header_values = [
        str(value) if value is not None else ""
        for value in frame.iloc[start_row].tolist()
    ]
    headers = _make_unique_headers(header_values)

    data = frame.iloc[start_row + 1 :].reset_index(drop=True)
    data.columns = headers

    data = data.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if data.empty:
        return None

    # Drop footer rows (e.g. "TOTAL WEIGHT : 345.6")
    data = data[~data.apply(_is_footer_row, axis=1)].reset_index(drop=True)
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

                # Use line-based strategy first (works well for CAD/engineering drawings).
                raw_tables = page.extract_tables(table_settings=_ENGINEERING_TABLE_SETTINGS) or []

                # Fall back to pdfplumber defaults if no tables found with line strategy.
                if not raw_tables:
                    raw_tables = page.extract_tables() or []

                if progress_callback:
                    progress_callback(f"Scanning page {page_number}: found {len(raw_tables)} raw table(s).")

                for raw_table in raw_tables:
                    is_rigging = _is_rigging_table(raw_table)
                    if progress_callback and is_rigging:
                        progress_callback(f"  → Rigging Material List detected on page {page_number}.")

                    # Extract metadata BEFORE _table_to_dataframe strips these rows.
                    title = _extract_title_from_raw(raw_table) if is_rigging else ""
                    total_weight = _extract_total_weight_from_raw(raw_table) if is_rigging else ""

                    frame = _table_to_dataframe(raw_table)
                    if frame is None:
                        continue
                    extracted.append(
                        ExtractedTable(
                            page_number=page_number,
                            dataframe=frame,
                            is_rigging_table=is_rigging,
                            table_title=title,
                            total_weight=total_weight,
                        )
                    )

        # If no rigging tables were found via text extraction, the PDF likely has
        # no text layer (AutoCAD vector export).  Fall back to OCR.
        rigging_found = any(t.is_rigging_table for t in extracted)
        if not rigging_found:
            if progress_callback:
                progress_callback(
                    "No text-layer table found. Switching to OCR-based extraction…"
                )
            from mto_reader.services.ocr_reader import extract_via_ocr  # lazy import
            ocr_tables = extract_via_ocr(
                pdf_path=pdf_path,
                page_indexes=selected_page_indexes,
                progress_callback=progress_callback,
            )
            extracted.extend(ocr_tables)

        return extracted
