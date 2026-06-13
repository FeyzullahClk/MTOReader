"""
OCR-based table extraction for CAD/engineering PDF drawings where the MTO table
text is not stored in the PDF text layer (common with AutoCAD-exported PDFs).

Requires Tesseract OCR to be installed on the system:
  Windows: https://github.com/UB-Mannheim/tesseract/wiki
           Default install path: C:\\Program Files\\Tesseract-OCR\\tesseract.exe
"""
from __future__ import annotations

import io
import os
from typing import Callable

import fitz  # pymupdf
import pandas as pd
import pytesseract
from PIL import Image

from mto_reader.models import ExtractedTable

# Default Tesseract install path on Windows
_TESSERACT_WINDOWS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Keywords used to detect the table title row
_RIGGING_KEYWORDS = ("rigging", "material", "list")

# Keywords used to identify the column header row
_HEADER_HINTS = {"item", "description", "qty", "wll", "mbl", "length", "weight"}

# Tesseract config: sparse text mode finds text anywhere on the page
_TESS_CONFIG = "--psm 11 --oem 3"

# Rendering DPI – 300 is standard for OCR; higher catches small cell text
_RENDER_DPI = 300


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _setup_tesseract() -> None:
    """Point pytesseract at the Windows default Tesseract location if present."""
    if os.path.isfile(_TESSERACT_WINDOWS):
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_WINDOWS


def _tesseract_available() -> bool:
    """Return True when Tesseract can actually be called."""
    _setup_tesseract()
    try:
        pytesseract.get_tesseract_version()
        return True
    except pytesseract.TesseractNotFoundError:
        return False


def _render_page(pdf_path: str, page_index: int, dpi: int = _RENDER_DPI) -> Image.Image:
    """Render a single PDF page to a grayscale PIL Image."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    img_bytes = pix.tobytes("png")
    doc.close()
    return Image.open(io.BytesIO(img_bytes))


def _ocr_words(img: Image.Image) -> pd.DataFrame:
    """
    Run Tesseract on *img* and return a DataFrame with columns:
    text, left, top, width, height, conf, cx, cy, right, bottom
    """
    raw = pytesseract.image_to_data(img, output_type=pytesseract.Output.DATAFRAME, config=_TESS_CONFIG)
    raw = raw[raw["conf"].notna() & (raw["conf"] > 10)].copy()
    raw["text"] = raw["text"].astype(str).str.strip()
    raw = raw[raw["text"].str.len() > 0].reset_index(drop=True)
    raw["cx"] = raw["left"] + raw["width"] / 2.0
    raw["cy"] = raw["top"] + raw["height"] / 2.0
    raw["right"] = raw["left"] + raw["width"]
    raw["bottom"] = raw["top"] + raw["height"]
    return raw


def _find_table_region(words: pd.DataFrame, img_height: int) -> tuple[int, int] | None:
    """
    Locate the Rigging Material List table by keyword and return
    (y_top, y_bottom) pixel coordinates, or None if not found.
    """
    rigging = words[words["text"].str.lower().str.contains("rigging", na=False)]
    if rigging.empty:
        return None

    y_top = max(0, int(rigging["top"].min()) - 8)

    # Footer: "TOTAL" and "WEIGHT" appear below the title
    below = words[words["top"] > y_top]
    total_w = below[below["text"].str.lower() == "total"]
    weight_w = below[below["text"].str.lower() == "weight"]

    if not total_w.empty and not weight_w.empty:
        y_bottom = int(max(total_w["bottom"].max(), weight_w["bottom"].max())) + 12
    else:
        y_bottom = img_height

    return y_top, y_bottom


def _cluster_rows(words: pd.DataFrame, tolerance: int) -> list[pd.DataFrame]:
    """
    Group words into text rows by y-coordinate proximity.
    Each returned DataFrame is sorted left→right.
    """
    if words.empty:
        return []

    words = words.sort_values("cy").reset_index(drop=True)
    rows: list[list[dict]] = []
    current: list[dict] = [words.iloc[0].to_dict()]
    cur_cy: float = words.iloc[0]["cy"]

    for i in range(1, len(words)):
        w = words.iloc[i].to_dict()
        if abs(w["cy"] - cur_cy) <= tolerance:
            current.append(w)
            cur_cy = sum(d["cy"] for d in current) / len(current)
        else:
            rows.append(current)
            current = [w]
            cur_cy = w["cy"]

    if current:
        rows.append(current)

    return [
        pd.DataFrame(r).sort_values("left").reset_index(drop=True) for r in rows
    ]


def _find_header_row_index(rows: list[pd.DataFrame]) -> int | None:
    """Return the index of the first row that looks like the column header."""
    for i, row in enumerate(rows):
        found = set(row["text"].str.lower()) & _HEADER_HINTS
        if len(found) >= 2:
            return i
    return None


def _is_sub_header_row(row: pd.DataFrame) -> bool:
    """
    Return True when the row looks like a secondary header row
    (unit labels such as '(MT)', '(M)', '(KG)') rather than a data row.
    Items in a data row always start with a digit in the first column.
    """
    texts = row["text"].tolist()
    if not texts:
        return False
    # If the first word is a small integer, it's a data row
    try:
        int(texts[0])
        return False
    except ValueError:
        pass
    # All tokens are short → likely unit labels
    return all(len(t) <= 12 for t in texts)


def _build_columns(
    header_rows: list[pd.DataFrame], img_width: int
) -> list[tuple[float, float, str]]:
    """
    Merge the header rows and use x-position gaps to define column boundaries.
    Returns a list of (col_left, col_right, col_name) tuples.
    """
    all_h = pd.concat(header_rows).sort_values("left").reset_index(drop=True)

    # Adaptive gap: 1.2 % of page width separates distinct columns
    gap_min = img_width * 0.012

    groups: list[list[dict]] = []
    cur_group: list[dict] = [all_h.iloc[0].to_dict()]
    cur_right: float = all_h.iloc[0]["right"]

    for i in range(1, len(all_h)):
        w = all_h.iloc[i].to_dict()
        if w["left"] > cur_right + gap_min:
            groups.append(cur_group)
            cur_group = [w]
        else:
            cur_group.append(w)
        cur_right = max(cur_right, w["right"])

    if cur_group:
        groups.append(cur_group)

    columns: list[tuple[float, float, str]] = []
    half_gap = gap_min / 2
    for g in groups:
        lefts = [d["left"] for d in g]
        rights = [d["right"] for d in g]
        # Build name: sort by (row, x) so sub-header labels appear after main label
        name_parts = " ".join(
            d["text"] for d in sorted(g, key=lambda d: (d["cy"], d["left"]))
        )
        name = " ".join(name_parts.split())
        columns.append((min(lefts) - half_gap, max(rights) + half_gap, name))

    return columns


def _word_to_col_index(cx: float, columns: list[tuple[float, float, str]]) -> int:
    """Return the column index whose range contains *cx*, falling back to nearest centre."""
    for i, (cl, cr, _) in enumerate(columns):
        if cl <= cx <= cr:
            return i
    centres = [(cl + cr) / 2 for cl, cr, _ in columns]
    return min(range(len(centres)), key=lambda i: abs(cx - centres[i]))


def _extract_total_weight(rows: list[pd.DataFrame]) -> str:
    """Return the numeric total-weight value from the footer row."""
    for row in reversed(rows):
        row_lower = " ".join(row["text"].str.lower().tolist())
        if "total" in row_lower and "weight" in row_lower:
            for val in reversed(row["text"].tolist()):
                try:
                    float(str(val).replace(",", ""))
                    return str(val)
                except ValueError:
                    continue
    return ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_via_ocr(
    pdf_path: str,
    page_indexes: list[int],
    progress_callback: Callable[[str], None] | None = None,
) -> list[ExtractedTable]:
    """
    For each requested page, render to image, run OCR, find the Rigging Material
    List table, and return a list of ExtractedTable instances.

    Raises RuntimeError if Tesseract is not installed.
    """
    if not _tesseract_available():
        raise RuntimeError(
            "Tesseract OCR is not installed or not found.\n\n"
            "This PDF has no text layer (AutoCAD export), so OCR is required.\n\n"
            "Please install Tesseract:\n"
            "  https://github.com/UB-Mannheim/tesseract/wiki\n"
            "Then re-run the conversion."
        )

    results: list[ExtractedTable] = []

    for page_index in page_indexes:
        page_number = page_index + 1

        if progress_callback:
            progress_callback(
                f"Page {page_number}: no text layer found – running OCR (this may take a moment)…"
            )

        img = _render_page(pdf_path, page_index)
        words = _ocr_words(img)

        if words.empty:
            if progress_callback:
                progress_callback(f"  Page {page_number}: OCR returned no text.")
            continue

        region = _find_table_region(words, img.height)
        if region is None:
            if progress_callback:
                progress_callback(f"  Page {page_number}: Rigging Material List not found via OCR.")
            continue

        y_top, y_bottom = region
        table_words = words[
            (words["top"] >= y_top) & (words["bottom"] <= y_bottom)
        ].copy()

        if table_words.empty:
            continue

        tolerance = max(4, int(table_words["height"].median() * 0.55))
        rows = _cluster_rows(table_words, tolerance)

        if not rows:
            continue

        # Row 0: spanning title
        title = " ".join(" ".join(rows[0]["text"].tolist()).split())
        if not title:
            title = "RIGGING MATERIAL LIST (OFFSHORE INSTALLATION)"

        header_idx = _find_header_row_index(rows)
        if header_idx is None:
            if progress_callback:
                progress_callback(f"  Page {page_number}: Could not identify header row via OCR.")
            continue

        # Include sub-header row (e.g. unit labels "(MT)", "(KG)") in header block
        header_end = header_idx
        if header_end + 1 < len(rows) and _is_sub_header_row(rows[header_end + 1]):
            header_end += 1

        columns = _build_columns(rows[header_idx : header_end + 1], img.width)
        col_names = [c[2] for c in columns]

        total_weight = _extract_total_weight(rows)

        data: list[list] = []
        for row in rows[header_end + 1 :]:
            row_lower = " ".join(row["text"].str.lower().tolist())
            if "total" in row_lower and "weight" in row_lower:
                break  # footer reached

            cells: dict[int, list[str]] = {i: [] for i in range(len(columns))}
            for _, w in row.iterrows():
                col_i = _word_to_col_index(float(w["cx"]), columns)
                cells[col_i].append(str(w["text"]))

            row_vals: list = [" ".join(cells[i]).strip() or None for i in range(len(columns))]
            if not all(v is None for v in row_vals):
                data.append(row_vals)

        if not data:
            continue

        df = pd.DataFrame(data, columns=col_names)
        df = df.dropna(how="all").reset_index(drop=True)
        if df.empty:
            continue

        if progress_callback:
            progress_callback(f"  ✓ OCR extracted {len(df)} item rows from page {page_number}.")

        results.append(
            ExtractedTable(
                page_number=page_number,
                dataframe=df,
                is_rigging_table=True,
                table_title=title,
                total_weight=total_weight,
            )
        )

    return results
