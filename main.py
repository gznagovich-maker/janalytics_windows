import sys
import os
import ctypes
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QTextEdit, QInputDialog, QMessageBox, QStackedWidget, QLabel
)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QRect
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
from views.core_analysis_view import GlobalMetaWidget
from views.team_analysis_view import TeamAnalysisWidget
from views.variant_builds_view import VariantBuildsWidget


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
        self.nav_container.setObjectName("nav_container")
        self.nav_container.setStyleSheet("#nav_container { background-color: #000000; }")
        self.nav_container.setFixedHeight(103)
        nav_layout = QHBoxLayout(self.nav_container)
        nav_layout.setContentsMargins(10, 0, 10, 0)
        
        self.btn_nav_import = QPushButton("Importa Nuovo Log")
        self.btn_nav_mass_import = QPushButton("Import Multiplo")
        self.btn_nav_list = QPushButton("Libreria Replay")
        self.btn_nav_meta_stats = QPushButton("Statistiche Meta")
        self.btn_nav_core_analysis = QPushButton("Analisi Core")
        self.btn_nav_team_analysis = QPushButton("Team Analysis")

        self.btn_nav_import.clicked.connect(self.show_import_view)
        self.btn_nav_mass_import.clicked.connect(self.show_mass_import_view)
        self.btn_nav_list.clicked.connect(self.show_list_view)
        self.btn_nav_meta_stats.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(8))
        self.btn_nav_core_analysis.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(10))
        self.btn_nav_team_analysis.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(11))

        nav_layout.addWidget(self.btn_nav_import)
        nav_layout.addWidget(self.btn_nav_mass_import)
        nav_layout.addWidget(self.btn_nav_list)
        nav_layout.addWidget(self.btn_nav_meta_stats)
        nav_layout.addWidget(self.btn_nav_core_analysis)
        nav_layout.addWidget(self.btn_nav_team_analysis)
        nav_layout.addStretch()
        
        self.lbl_logo = QLabel()
        self.lbl_logo.setStyleSheet("background-color: #000000; border-radius: 8px; padding: 4px;")
        
        import os
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
            
        logo_path = os.path.join(base_path, "assets", "logo", "3.svg")
        pixmap = QPixmap(logo_path)
        scaled_pixmap = pixmap.scaledToHeight(89, Qt.TransformationMode.SmoothTransformation)
        # Taglia 10 pixel dal fondo
        crop_rect = QRect(0, 0, scaled_pixmap.width(), max(1, scaled_pixmap.height() - 10))
        cropped_pixmap = scaled_pixmap.copy(crop_rect)
        self.lbl_logo.setPixmap(cropped_pixmap)
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
        self.core_analysis_view = GlobalMetaWidget()
        self.team_analysis_view = TeamAnalysisWidget()
        self.variant_builds_view = VariantBuildsWidget()
        
        # Connetti segnali build
        self.team_analysis_view.show_builds_signal.connect(self.show_variant_builds)
        self.variant_builds_view.back_signal.connect(lambda: self.stacked_widget.setCurrentIndex(11))

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
        self.stacked_widget.addWidget(self.core_analysis_view) # Indice 10
        self.stacked_widget.addWidget(self.team_analysis_view) # Indice 11
        self.stacked_widget.addWidget(self.variant_builds_view) # Indice 12

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
        
    def show_variant_builds(self, variant):
        self.variant_builds_view.load_variant(variant)
        self.stacked_widget.setCurrentIndex(12)

    def show_list_view(self):
        self.list_view.load_replays()
        self.stacked_widget.setCurrentIndex(1)

    def show_detail_view(self, match_id: str):
        self.detail_view.display_match(match_id)
        self.stacked_widget.setCurrentIndex(2)

    def navigate_to_catalog(self, url_str: str):
        # Esempio: "move:Incineroar", "item:Leftovers", "ability:Intimidate"
        parts = url_str.split(":", 1)
        if len(parts) == 2:
            cat = parts[0]
            val = parts[1]
            if cat == "move":
                self.moves_view.load_data()
                self.moves_view.filter_input.setText(val)
                self.stacked_widget.setCurrentIndex(4)
            elif cat == "item":
                self.items_view.load_data()
                self.items_view.filter_input.setText(val)
                self.stacked_widget.setCurrentIndex(5)
            elif cat == "ability":
                self.abilities_view.load_data()
                self.abilities_view.filter_input.setText(val)
                self.stacked_widget.setCurrentIndex(6)

    def go_back(self):
        # Ritorna alla lista
        self.show_list_view()


if __name__ == "__main__":
    myappid = 'jorkcorp.janalytics.windows.1.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)
    
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_path, "assets", "logo", "3.svg")
    app.setWindowIcon(QIcon(icon_path))
    
    # Applica il Dark Theme Globale
    app.setStyle("Fusion")
    dark_stylesheet = """
    * {
        font-family: 'Segoe UI', 'Inter', 'Roboto', 'Helvetica Neue', sans-serif;
    }
    QWidget {
        background-color: #000000;
        color: #E0E0E0;
        font-size: 14px;
    }
    /* Depth and shadows for panels (Effetto Scavato) */
    QFrame, QGroupBox, QScrollArea, QStackedWidget {
        background-color: #0A0A0A;
        border-top: 3px solid #000000;
        border-left: 3px solid #000000;
        border-bottom: 1px solid #222222;
        border-right: 1px solid #222222;
        border-radius: 8px;
    }
    /* Transparent background for main container widgets if needed */
    QMainWindow {
        background-color: #000000;
    }
    QPushButton {
        background-color: #B6FAF5; /* Primario: Ciano pastello */
        border: none;
        border-bottom: 3px solid #82B5B1; /* Ombra per effetto 3D */
        color: #0A0A0A;
        padding: 10px 20px;
        border-radius: 18px; /* Effetto Pillola moderno */
        font-weight: 800;
        font-size: 13px;
        letter-spacing: 1px;
        text-transform: uppercase;
    }
    QPushButton:hover {
        background-color: #FAB7F0; /* Secondario: Rosa pastello al passaggio del mouse */
        border-bottom: 3px solid #D69AD0;
        color: #0A0A0A;
    }
    QPushButton:pressed {
        background-color: #467A77; /* Terziario: Verde pastello al click */
        border-bottom: 0px solid transparent;
        margin-top: 3px; /* Simula l'abbassamento del bottone */
        color: #0A0A0A;
    }
    QPushButton:disabled {
        background-color: #1A1A1A;
        border-bottom: 3px solid #111111;
        color: #555555;
    }
    QLineEdit, QTextEdit, QTableWidget, QTreeWidget, QListWidget, QListView {
        background-color: #050505;
        color: #FFFFFF;
        border-top: 2px solid #000000;
        border-left: 2px solid #000000;
        border-bottom: 1px solid #1A1A1A;
        border-right: 1px solid #1A1A1A;
        border-radius: 6px;
        selection-background-color: #467A77; /* Terziario: Verde pastello */
        selection-color: #0A0A0A;
        padding: 4px;
        outline: none;
    }
    QLineEdit:focus, QTextEdit:focus, QTableWidget:focus, QTreeWidget:focus, QListWidget:focus {
        border: 1px solid #467A77;
    }
    QHeaderView::section {
        background-color: #0A0A0A;
        padding: 8px;
        border: none;
        border-bottom: 2px solid #B6FAF5;
        font-weight: bold;
        color: #FAB7F0;
        font-size: 13px;
        text-transform: uppercase;
    }
    QGroupBox {
        border-top: 3px solid #000000;
        border-left: 3px solid #000000;
        border-bottom: 1px solid #222222;
        border-right: 1px solid #222222;
        margin-top: 25px;
        font-weight: bold;
        border-radius: 8px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 8px;
        left: 15px;
        color: #B6FAF5;
        font-size: 14px;
        background-color: #000000; /* Isola il titolo per sembrare scolpito */
        border-radius: 4px;
    }
    /* Scrollbars */
    QScrollBar:vertical {
        background: #000000;
        width: 12px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #1A1A1A;
        min-height: 20px;
        border-radius: 6px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background: #467A77;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    
    QScrollBar:horizontal {
        background: #000000;
        height: 12px;
        margin: 0px;
    }
    QScrollBar::handle:horizontal {
        background: #1A1A1A;
        min-width: 20px;
        border-radius: 6px;
        margin: 2px;
    }
    QScrollBar::handle:horizontal:hover {
        background: #467A77;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
    
    QTableWidget QPushButton {
        padding: 4px 10px;
        font-size: 11px;
        border-radius: 12px;
        border-bottom: 2px solid #82B5B1;
    }
    QTableWidget QPushButton:hover {
        border-bottom: 2px solid #D69AD0;
    }
    """
    app.setStyleSheet(dark_stylesheet)
    
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())