import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QTextEdit, QInputDialog, QMessageBox, QStackedWidget
)
from parser_worker import ParserWorker
from database.connection import init_db
from views.replay_views import ReplayListWidget, ReplayDetailWidget


class ImportWidget(QWidget):
    """Schermata per incollare e salvare nuovi log"""

    def __init__(self, parent_main):
        super().__init__()
        self.parent_main = parent_main

        self.log_text_edit = QTextEdit()
        self.log_text_edit.setPlaceholderText("Incolla qui il log di Showdown...")

        self.save_button = QPushButton("Salva Replay nel DB")
        self.save_button.clicked.connect(self.on_save_clicked)

        layout = QVBoxLayout(self)
        layout.addWidget(self.log_text_edit)
        layout.addWidget(self.save_button)

    def on_save_clicked(self):
        log_content = self.log_text_edit.toPlainText().strip()
        if not log_content:
            QMessageBox.warning(self, "Attenzione", "Il log è vuoto!")
            return

        match_name, ok = QInputDialog.getText(
            self, "Salva Replay", "Inserisci un ID o nome per questo match:"
        )

        if ok and match_name.strip():
            self.save_button.setEnabled(False)
            self.worker = ParserWorker(log_content, match_name.strip())
            self.worker.finished.connect(self.on_parsing_finished)
            self.worker.error.connect(self.on_parsing_error)
            self.worker.start()

    def on_parsing_finished(self, parsed_data):
        self.save_button.setEnabled(True)
        QMessageBox.information(self, "Successo", "Replay salvato con successo!")
        self.log_text_edit.clear()
        # Aggiorna la lista dei replay e passa alla schermata lista
        self.parent_main.list_view.load_replays()
        self.parent_main.show_list_view()

    def on_parsing_error(self, error_msg):
        self.save_button.setEnabled(True)
        QMessageBox.critical(self, "Errore", f"Errore durante il salvataggio:\n{error_msg}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VGC Replay Analyzer")
        self.resize(800, 600)

        init_db()

        # Layout principale con Navbar in alto e StackedWidget sotto
        main_layout = QVBoxLayout()

        # Navigation Bar
        nav_layout = QHBoxLayout()
        self.btn_nav_import = QPushButton("Importa Nuovo Log")
        self.btn_nav_list = QPushButton("Libreria Replay")

        self.btn_nav_import.clicked.connect(self.show_import_view)
        self.btn_nav_list.clicked.connect(self.show_list_view)

        nav_layout.addWidget(self.btn_nav_import)
        nav_layout.addWidget(self.btn_nav_list)
        nav_layout.addStretch()
        main_layout.addLayout(nav_layout)

        # StackedWidget per le diverse schermate
        self.stacked_widget = QStackedWidget()

        # Le 3 schermate
        self.import_view = ImportWidget(self)
        self.list_view = ReplayListWidget()
        self.detail_view = ReplayDetailWidget()

        self.stacked_widget.addWidget(self.import_view)  # Indice 0
        self.stacked_widget.addWidget(self.list_view)  # Indice 1
        self.stacked_widget.addWidget(self.detail_view)  # Indice 2

        main_layout.addWidget(self.stacked_widget)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Connessioni dei segnali tra schermate
        self.list_view.replay_selected.connect(self.show_detail_view)
        self.detail_view.back_requested.connect(self.show_list_view)

    def show_import_view(self):
        self.stacked_widget.setCurrentIndex(0)

    def show_list_view(self):
        self.list_view.load_replays()
        self.stacked_widget.setCurrentIndex(1)

    def show_detail_view(self, match_id: str):
        self.detail_view.display_match(match_id)
        self.stacked_widget.setCurrentIndex(2)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())