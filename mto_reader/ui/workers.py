from PySide6.QtCore import QThread, Signal

from mto_reader.services.excel_writer import export_tables_to_excel
from mto_reader.services.pdf_reader import PDFTableExtractor


class ConversionWorker(QThread):
    progress = Signal(str)
    failed = Signal(str)
    completed = Signal(str)

    def __init__(
        self,
        pdf_path: str,
        output_path: str,
        page_selection: str,
        sheet_name: str,
    ) -> None:
        super().__init__()
        self.pdf_path = pdf_path
        self.output_path = output_path
        self.page_selection = page_selection
        self.sheet_name = sheet_name

    def run(self) -> None:
        try:
            self.progress.emit("Starting PDF table extraction.")
            extractor = PDFTableExtractor()
            tables = extractor.extract_tables(
                pdf_path=self.pdf_path,
                page_selection=self.page_selection,
                progress_callback=self.progress.emit,
            )

            if not tables:
                raise ValueError("No structured tables found in the selected pages.")

            self.progress.emit(f"Exporting {len(tables)} tables to Excel.")
            export_tables_to_excel(
                tables=tables,
                output_path=self.output_path,
                sheet_name=self.sheet_name,
            )

            self.completed.emit(
                f"Success. Extracted {len(tables)} tables and wrote '{self.output_path}'."
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.failed.emit(str(exc))
