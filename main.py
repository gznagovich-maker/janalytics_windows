import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QTextEdit, QInputDialog, QMessageBox, QStackedWidget, QLabel
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from parser_worker import ParserWorker
from database.connection import init_db
from database.pokedex_sync import sync_pokedex
from database.metadata_sync import sync_metadata
from views.replay_views import ReplayListWidget
from views.replay_analyzer_ui import ReplayAnalyzerUI
from views.pokedex_views import PokedexWidget
from views.catalog_views import MovesWidget, ItemsWidget, AbilitiesWidget, MoveDetailWidget
from views.meta_stats_view import MetaStatsWidget
from views.mass_import_view import MassImportWidget


class ImportWidget(QWidget):
    """Schermata per incollare e salvare nuovi log"""

    def __init__(self, parent_main):
        super().__init__()
        self.parent_main = parent_main
        self.job_queue = []
        self.success_count = 0
        self.error_count = 0

        self.log_text_edit = QTextEdit()
        self.log_text_edit.setPlaceholderText("Incolla qui il log di Showdown, o multipli link (uno per riga) per l'importazione massiva...")

        self.save_button = QPushButton("Salva Replay nel DB")
        self.save_button.clicked.connect(self.on_save_clicked)

        layout = QVBoxLayout(self)
        layout.addWidget(self.log_text_edit)
        layout.addWidget(self.save_button)

    def on_save_clicked(self):
        log_content = self.log_text_edit.toPlainText().strip()
        if not log_content:
            QMessageBox.warning(self, "Attenzione", "Inserisci un log o dei link di Showdown!")
            return

        lines = [line.strip() for line in log_content.split('\n') if line.strip()]
        
        # Check if it's bulk import (multiple lines, all are links)
        if len(lines) > 1 and all(l.startswith("http://") or l.startswith("https://") for l in lines):
            self.save_button.setEnabled(False)
            self.job_queue = lines
            self.success_count = 0
            self.error_count = 0
            self.process_next_job()
            return

        # Single import logic
        default_name = ""
        if log_content.startswith("http://") or log_content.startswith("https://"):
            url = log_content
            if not url.endswith(".log"):
                url += ".log"
            
            try:
                import urllib.request
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    log_content = response.read().decode('utf-8')
            except Exception as e:
                QMessageBox.critical(self, "Errore di Rete", f"Impossibile scaricare il replay dal link:\n{e}")
                return
            
            default_name = url.split("/")[-1].replace(".log", "")

        match_name, ok = QInputDialog.getText(
            self, "Salva Replay", "Inserisci un ID o nome per questo match:",
            text=default_name
        )

        if ok and match_name.strip():
            self.save_button.setEnabled(False)
            self.worker = ParserWorker(log_content, match_name.strip())
            self.worker.finished.connect(self.on_parsing_finished)
            self.worker.error.connect(self.on_parsing_error)
            self.worker.start()

    def process_next_job(self):
        if not self.job_queue:
            self.save_button.setEnabled(True)
            QMessageBox.information(self, "Bulk Import", f"Importazione massiva completata!\n\nReplay aggiunti: {self.success_count}\nErrori: {self.error_count}")
            self.log_text_edit.clear()
            self.parent_main.list_view.load_replays()
            self.parent_main.show_list_view()
            return
            
        url = self.job_queue.pop(0)
        if not url.endswith(".log"):
            url += ".log"
        match_name = url.split("/")[-1].replace(".log", "")
        
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                log_content = response.read().decode('utf-8')
        except Exception as e:
            self.error_count += 1
            print(f"Errore bulk download per {url}: {e}")
            self.process_next_job()
            return
            
        self.worker = ParserWorker(log_content, match_name)
        self.worker.finished.connect(self.on_bulk_parsing_finished)
        self.worker.error.connect(self.on_bulk_parsing_error)
        self.worker.start()

    def on_bulk_parsing_finished(self, parsed_data):
        self.success_count += 1
        self.process_next_job()
        
    def on_bulk_parsing_error(self, error_msg):
        self.error_count += 1
        print(f"Errore bulk parsing: {error_msg}")
        self.process_next_job()

    def on_parsing_finished(self, parsed_data):
        self.save_button.setEnabled(True)
        QMessageBox.information(self, "Successo", "Replay salvato con successo!")
        self.log_text_edit.clear()
        self.parent_main.list_view.load_replays()
        self.parent_main.show_list_view()

    def on_parsing_error(self, error_msg):
        self.save_button.setEnabled(True)
        QMessageBox.critical(self, "Errore", f"Errore durante il salvataggio:\n{error_msg}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VGC Replay Analyzer")

        init_db()

        # Layout principale con Navbar in alto e StackedWidget sotto
        main_layout = QVBoxLayout()

        # Navigation Bar Container
        self.nav_container = QWidget()
        self.nav_container.setStyleSheet("background-color: #000000;")
        self.nav_container.setFixedHeight(70)
        nav_layout = QHBoxLayout(self.nav_container)
        nav_layout.setContentsMargins(10, 0, 10, 0)
        
        self.btn_nav_import = QPushButton("Importa Nuovo Log")
        self.btn_nav_mass_import = QPushButton("Import Multiplo")
        self.btn_nav_list = QPushButton("Libreria Replay")
        self.btn_nav_meta_stats = QPushButton("Statistiche Meta")

        self.btn_nav_import.clicked.connect(self.show_import_view)
        self.btn_nav_mass_import.clicked.connect(self.show_mass_import_view)
        self.btn_nav_list.clicked.connect(self.show_list_view)
        self.btn_nav_meta_stats.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(8))

        nav_layout.addWidget(self.btn_nav_import)
        nav_layout.addWidget(self.btn_nav_mass_import)
        nav_layout.addWidget(self.btn_nav_list)
        nav_layout.addWidget(self.btn_nav_meta_stats)
        nav_layout.addStretch()
        
        self.lbl_logo = QLabel()
        pixmap = QPixmap(r"C:\Users\Mirco\Documents\Jorkcorp\janalytics_windows\assets\logo\J_stondo_nero.png")
        self.lbl_logo.setPixmap(pixmap.scaledToHeight(60, Qt.TransformationMode.SmoothTransformation))
        nav_layout.addWidget(self.lbl_logo)
        
        main_layout.addWidget(self.nav_container)

        # StackedWidget per le diverse schermate
        self.stacked_widget = QStackedWidget()

        # Le 3 schermate
        self.import_view = ImportWidget(self)
        self.list_view = ReplayListWidget()
        self.detail_view = ReplayAnalyzerUI()
        self.pokedex_view = PokedexWidget()
        self.moves_view = MovesWidget()
        self.items_view = ItemsWidget()
        self.abilities_view = AbilitiesWidget()
        self.move_detail_view = MoveDetailWidget()
        self.meta_stats_view = MetaStatsWidget()
        self.mass_import_view = MassImportWidget(self)

        # Storico per navigazione
        self.previous_page_index = 1

        self.stacked_widget.addWidget(self.import_view)  # Indice 0
        self.stacked_widget.addWidget(self.list_view)  # Indice 1
        self.stacked_widget.addWidget(self.detail_view)  # Indice 2
        self.stacked_widget.addWidget(self.pokedex_view) # Indice 3
        self.stacked_widget.addWidget(self.moves_view)   # Indice 4
        self.stacked_widget.addWidget(self.items_view)   # Indice 5
        self.stacked_widget.addWidget(self.abilities_view)# Indice 6
        self.stacked_widget.addWidget(self.move_detail_view) # Indice 7
        self.stacked_widget.addWidget(self.meta_stats_view) # Indice 8
        self.stacked_widget.addWidget(self.mass_import_view) # Indice 9

        main_layout.addWidget(self.stacked_widget)
        
        # Signal connections
        self.list_view.replay_selected.connect(self.show_detail_view)
        self.detail_view.back_requested.connect(self.show_list_view)
        self.detail_view.link_clicked.connect(self.navigate_to_catalog)
        self.move_detail_view.back_requested.connect(self.go_back)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Connessioni dei segnali tra schermate
        self.list_view.replay_selected.connect(self.show_detail_view)
        self.detail_view.back_requested.connect(self.show_list_view)

    def show_import_view(self):
        self.stacked_widget.setCurrentIndex(0)

    def show_mass_import_view(self):
        self.stacked_widget.setCurrentIndex(9)

    def show_list_view(self):
        self.list_view.load_replays()
        self.stacked_widget.setCurrentIndex(1)

    def show_detail_view(self, match_id: str):
        self.detail_view.display_match(match_id)
        self.stacked_widget.setCurrentIndex(2)

    def go_back(self):
        self.stacked_widget.setCurrentIndex(self.previous_page_index)

    def navigate_to_catalog(self, link_str: str):
        # formattato come type:nome es. move:protect
        if ":" not in link_str: return
        cat, val = link_str.split(":", 1)
        
        # Salva la pagina attuale prima di cambiare
        self.previous_page_index = self.stacked_widget.currentIndex()
        
        if cat == "move":
            self.move_detail_view.display_move(val)
            self.stacked_widget.setCurrentIndex(7)
        elif cat == "item":
            self.stacked_widget.setCurrentIndex(5)
            self.items_view.set_search(val)
        elif cat == "ability":
            self.stacked_widget.setCurrentIndex(6)
            self.abilities_view.set_search(val)
        elif cat == "pokedex":
            self.stacked_widget.setCurrentIndex(3)
            self.pokedex_view.search_bar.setText(val)
            self.pokedex_view.load_data()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Applica il Dark Theme Globale
    app.setStyle("Fusion")
    dark_stylesheet = """
    QWidget {
        background-color: #121212;
        color: #ffffff;
        font-size: 14px;
    }
    QPushButton {
        background-color: #2c3e50;
        border: 1px solid #34495e;
        padding: 6px 12px;
        border-radius: 4px;
        color: #ffffff;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #34495e;
    }
    QLineEdit, QTextEdit, QTableWidget, QTreeWidget {
        background-color: #1e1e1e;
        color: #ffffff;
        border: 1px solid #444444;
        selection-background-color: #2980b9;
    }
    QHeaderView::section {
        background-color: #2c3e50;
        padding: 4px;
        border: 1px solid #444444;
        font-weight: bold;
        color: #ffffff;
    }
    QGroupBox {
        border: 1px solid #444444;
        margin-top: 10px;
        font-weight: bold;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top center;
        padding: 0 5px;
    }
    """
    app.setStyleSheet(dark_stylesheet)
    
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())