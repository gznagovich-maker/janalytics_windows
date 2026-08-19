import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLineEdit, QPushButton, QStackedWidget,
                               QTableView, QMessageBox)
from parser_worker import ParserWorker, Match
from turn_action_model import TurnActionModel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JAnalytics Parser")
        self.resize(800, 600)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self._setup_input_ui()
        self._setup_visualization_ui()

    def _setup_input_ui(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Inserisci il link del log Showdown...")
        self.parse_btn = QPushButton("Estrai Dati")
        self.parse_btn.clicked.connect(self.start_parsing)

        input_layout.addWidget(self.url_input)
        input_layout.addWidget(self.parse_btn)

        layout.addLayout(input_layout)
        self.stack.addWidget(page)

    def _setup_visualization_ui(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.table_view = QTableView()
        self.table_view.horizontalHeader().setStretchLastSection(True)

        back_btn = QPushButton("Torna all'inserimento")
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))

        layout.addWidget(self.table_view)
        layout.addWidget(back_btn)

        self.stack.addWidget(page)

    def start_parsing(self):
        url = self.url_input.text().strip()
        if not url:
            return

        self.parse_btn.setEnabled(False)
        self.parse_btn.setText("Elaborazione...")

        self.worker = ParserWorker(url)
        self.worker.finished.connect(self.on_parsing_finished)
        self.worker.error.connect(self.on_parsing_error)
        self.worker.start()

    def on_parsing_finished(self, match_data: Match):
        self.parse_btn.setEnabled(True)
        self.parse_btn.setText("Estrai Dati")

        # Inietta i dati nel modello della tabella
        model = TurnActionModel(match_data)
        self.table_view.setModel(model)

        # Passa alla seconda schermata
        self.stack.setCurrentIndex(1)

    def on_parsing_error(self, err_msg: str):
        self.parse_btn.setEnabled(True)
        self.parse_btn.setText("Estrai Dati")
        QMessageBox.critical(self, "Errore", f"Impossibile analizzare il log:\n{err_msg}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())