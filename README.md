# MTOReader (PySide6)

Desktop application to extract MTO-like tables from PDF drawings and export them to Excel.

## Features

- Open a PDF drawing file.
- Extract tables from selected pages (or all pages).
- Basic table cleanup and normalization.
- Export merged results to `.xlsx`.

## Project Structure

- `main.py`: application entrypoint.
- `mto_reader/app.py`: Qt app bootstrap.
- `mto_reader/ui/main_window.py`: desktop UI and user workflow.
- `mto_reader/ui/workers.py`: background worker for extraction/export.
- `mto_reader/services/pdf_reader.py`: PDF table extraction logic.
- `mto_reader/services/excel_writer.py`: Excel export logic.
- `mto_reader/models.py`: shared data model.

## Requirements

- Python 3.10+
- See `requirements.txt`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

## Notes

- This starter uses `pdfplumber` to detect table structures from text-based PDFs.
- Scanned/image-only PDFs may require OCR as a future enhancement.
- MTO formats vary significantly between drawings, so parsing rules may need to be customized per template.
