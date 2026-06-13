from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mto_reader.ui.workers import ConversionWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.worker: ConversionWorker | None = None

        self.setWindowTitle("MTOReader - PDF to Excel")
        self.resize(900, 620)

        self.pdf_edit = QLineEdit()
        self.output_edit = QLineEdit()
        self.pages_edit = QLineEdit()
        self.sheet_edit = QLineEdit("MTO")
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)

        self.pages_edit.setPlaceholderText("All pages, or range like 1-3,5")

        self.browse_pdf_button = QPushButton("Browse PDF")
        self.browse_output_button = QPushButton("Select Output")
        self.run_button = QPushButton("Extract and Convert")

        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.browse_pdf_button.clicked.connect(self._browse_pdf)
        self.browse_output_button.clicked.connect(self._browse_output)
        self.run_button.clicked.connect(self._run_conversion)

        self._build_layout()

    def _build_layout(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        form = QFormLayout()
        form.addRow("PDF File", self._row_with_button(self.pdf_edit, self.browse_pdf_button))
        form.addRow("Output Excel", self._row_with_button(self.output_edit, self.browse_output_button))
        form.addRow("Pages", self.pages_edit)
        form.addRow("Sheet Name", self.sheet_edit)

        layout.addLayout(form)
        layout.addWidget(self.run_button)
        layout.addWidget(QLabel("Execution Log"))
        layout.addWidget(self.log_edit)
        layout.addWidget(self.status_label)

        self.setCentralWidget(root)

    @staticmethod
    def _row_with_button(field: QLineEdit, button: QPushButton) -> QWidget:
        wrapper = QWidget()
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(field)
        row.addWidget(button)
        return wrapper

    def _browse_pdf(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF Drawing",
            "",
            "PDF Files (*.pdf)",
        )
        if not file_path:
            return

        self.pdf_edit.setText(file_path)

        current_output = self.output_edit.text().strip()
        if not current_output:
            suggested_output = str(Path(file_path).with_suffix(".xlsx"))
            self.output_edit.setText(suggested_output)

    def _browse_output(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Output Excel",
            self.output_edit.text().strip() or "mto_output.xlsx",
            "Excel Files (*.xlsx)",
        )
        if file_path:
            self.output_edit.setText(file_path)

    def _run_conversion(self) -> None:
        pdf_path = self.pdf_edit.text().strip()
        output_path = self.output_edit.text().strip()
        page_selection = self.pages_edit.text().strip()
        sheet_name = self.sheet_edit.text().strip() or "MTO"

        if not pdf_path:
            self._show_warning("Please select a PDF file.")
            return

        if not Path(pdf_path).exists():
            self._show_warning("Selected PDF file does not exist.")
            return

        if not output_path:
            self._show_warning("Please select an output Excel path.")
            return

        self.run_button.setEnabled(False)
        self.status_label.setText("Running...")
        self.log_edit.clear()
        self._append_log(f"Input PDF: {pdf_path}")
        self._append_log(f"Output XLSX: {output_path}")
        self._append_log(f"Pages: {page_selection or 'all'}")

        self.worker = ConversionWorker(
            pdf_path=pdf_path,
            output_path=output_path,
            page_selection=page_selection,
            sheet_name=sheet_name,
        )
        self.worker.progress.connect(self._append_log)
        self.worker.failed.connect(self._on_failure)
        self.worker.completed.connect(self._on_success)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _append_log(self, message: str) -> None:
        self.log_edit.append(message)

    def _on_success(self, message: str) -> None:
        self.status_label.setText("Completed")
        self._append_log(message)
        QMessageBox.information(self, "Completed", message)

    def _on_failure(self, error_message: str) -> None:
        self.status_label.setText("Failed")
        self._append_log(f"Error: {error_message}")
        QMessageBox.critical(self, "Failed", error_message)

    def _on_finished(self) -> None:
        self.run_button.setEnabled(True)

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, "Missing Input", message)
