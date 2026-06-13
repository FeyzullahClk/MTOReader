"""
Run this script with your PDF to diagnose what pdfplumber sees.
Usage: python debug_pdf.py "path/to/drawing.pdf"
"""
import sys
import pdfplumber

SETTINGS_LINES = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
    "min_words_vertical": 1,
    "min_words_horizontal": 1,
}

pdf_path = sys.argv[1] if len(sys.argv) > 1 else input("PDF path: ").strip()

with pdfplumber.open(pdf_path) as pdf:
    print(f"Total pages: {len(pdf.pages)}\n")
    for page_idx, page in enumerate(pdf.pages):
        page_num = page_idx + 1
        print(f"=== PAGE {page_num} ===")

        # Try line-based strategy
        tables_lines = page.extract_tables(table_settings=SETTINGS_LINES) or []
        print(f"  [lines strategy]   {len(tables_lines)} table(s) found")
        for ti, t in enumerate(tables_lines):
            print(f"    Table {ti+1}: {len(t)} rows x {len(t[0]) if t else 0} cols")
            for ri, row in enumerate(t[:5]):
                print(f"      row {ri}: {row}")

        # Try default strategy
        tables_default = page.extract_tables() or []
        print(f"  [default strategy] {len(tables_default)} table(s) found")
        for ti, t in enumerate(tables_default):
            print(f"    Table {ti+1}: {len(t)} rows x {len(t[0]) if t else 0} cols")
            for ri, row in enumerate(t[:5]):
                print(f"      row {ri}: {row}")

        # Show all words on the page (first 30)
        words = page.extract_words()
        print(f"  [words] first 30 words: {[w['text'] for w in words[:30]]}")
        print()
