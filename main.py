import sys
import os
import ctypes

# ── HiDPI / Font rendering fix ───────────────────────────────────
# Queste variabili devono essere impostate PRIMA della creazione
# di QApplication altrimenti non hanno effetto.
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")
os.environ["QT_FONT_DPI"] = "96"  # forza 96dpi per Fusion su Windows

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QTextEdit, QInputDialog, QMessageBox, QStackedWidget, QLabel,
    QFrame, QGraphicsDropShadowEffect
)
from PySide6.QtGui import QPixmap, QIcon, QColor, QFont
from PySide6.QtCore import Qt, QRect, QPropertyAnimation, QEasingCurve
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
from views.limitless_views import LimitlessTournamentsWidget, LimitlessTournamentDetailWidget
from views.home_view import HomeWidget
from views.build_and_compare_view import BuildAndCompareWidget
from widgets.loading_overlay import LoadingOverlay




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
        self.save_button.setProperty("class", "primary")
        self.save_button.clicked.connect(self.on_save_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
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

        # Layout principale Verticale (TopBar in alto, poi Body sotto)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -------------------------------------------------------------
        # 1. Top Bar (Header globale, copre l'intera larghezza, z-index più alto)
        # -------------------------------------------------------------
        self.top_bar = QWidget()
        self.top_bar.setFixedHeight(64)
        self.top_bar.setObjectName("top_bar")
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self.top_bar.setGraphicsEffect(shadow)
        
        # Ensures top_bar drops shadow OVER the body
        self.top_bar.raise_() 

        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(24, 0, 24, 0)
        top_bar_layout.setSpacing(16)
        
        self.btn_toggle_sidebar = QPushButton("☰")
        self.btn_toggle_sidebar.setFixedSize(48, 48)
        self.btn_toggle_sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_sidebar.setToolTip("Apri/Chiudi Navigazione")
        self.btn_toggle_sidebar.setStyleSheet(
            "QPushButton { font-size: 22px; background: transparent; border: none;"
            " color: #6E7285; border-radius: 6px; }"
            "QPushButton:hover { background: rgba(166,154,202,0.10); color: #C8BEE8; }"
            "QPushButton:pressed { background: rgba(134,120,168,0.22); color: #C8BEE8; }"
        )
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)
        
        self.lbl_global_title = QLabel("Libreria Replay VGC")
        self.lbl_global_title.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #DEDAD4;"
            "margin: 0; padding: 0; background: transparent; border: none;"
            "letter-spacing: 0.3px; font-family: 'Inter', 'Roboto', 'Segoe UI', sans-serif;"
        )
        
        self.top_logo = QLabel()
        self.top_logo.setStyleSheet("background-color: transparent; border: none;")
        import os
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
            
        logo_path = os.path.join(base_path, "assets", "logo", "j.png")
        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation)
            self.top_logo.setPixmap(scaled_pixmap)
            
        self.top_logo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.top_logo.mousePressEvent = lambda e: self.show_home_view()
        
        top_bar_layout.addWidget(self.btn_toggle_sidebar)
        top_bar_layout.addStretch(1)
        top_bar_layout.addWidget(self.lbl_global_title, alignment=Qt.AlignmentFlag.AlignCenter)
        top_bar_layout.addStretch(1)
        top_bar_layout.addWidget(self.top_logo)
        
        main_layout.addWidget(self.top_bar)

        # -------------------------------------------------------------
        # 2. Body Area (Sidebar a sinistra, StackedWidget a destra)
        # -------------------------------------------------------------
        self.body_widget = QWidget()
        body_layout = QHBoxLayout(self.body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar Container
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(0)
        self.sidebar.setMaximumWidth(232)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 16, 8, 24)
        sidebar_layout.setSpacing(2)
        from widgets.animated_menu_button import AnimatedMenuButton

        self.btn_nav_import = AnimatedMenuButton(" Importa Nuovo Log")
        self.btn_nav_import.setIcons(
            "resources/icons/arrow-down-tray.svg",
            "resources/icons/arrow-down-tray-hover.svg"
        )

        self.btn_nav_mass_import = AnimatedMenuButton(" Import Multiplo")
        self.btn_nav_mass_import.setIcons(
            "resources/icons/arrow-down-on-square-stack.svg",
            "resources/icons/arrow-down-on-square-stack-hover.svg"
        )

        self.btn_nav_list = AnimatedMenuButton(" Libreria Replay")
        self.btn_nav_list.setIcons(
            "resources/icons/film.svg",
            "resources/icons/film-hover.svg"
        )

        self.btn_nav_meta_stats = AnimatedMenuButton(" Meta Analysis")
        self.btn_nav_meta_stats.setIcons(
            "resources/icons/chart-bar.svg",
            "resources/icons/chart-bar-hover.svg"
        )

        self.btn_nav_core_analysis = AnimatedMenuButton(" Analisi Core")
        self.btn_nav_core_analysis.setIcons(
            "resources/icons/beaker.svg",
            "resources/icons/beaker-hover.svg"
        )

        self.btn_nav_team_analysis = AnimatedMenuButton(" Team Analysis")
        self.btn_nav_team_analysis.setIcons(
            "resources/icons/user-group.svg",
            "resources/icons/user-group-hover.svg"
        )

        self.btn_nav_limitless = AnimatedMenuButton(" Tornei Limitless")
        self.btn_nav_limitless.setIcons(
            "resources/icons/trophy.svg",
            "resources/icons/trophy-hover.svg"
        )
        
        self.btn_nav_build_compare = AnimatedMenuButton(" Costruisci e Confronta")
        self.btn_nav_build_compare.setIcons(
            "resources/icons/puzzle-piece.svg",
            "resources/icons/puzzle-piece-hover.svg"
        )


        # Rendiamo i bottoni checkable per simulare le tab
        self.nav_buttons = [
            self.btn_nav_list, self.btn_nav_import, self.btn_nav_mass_import, 
            self.btn_nav_meta_stats, self.btn_nav_core_analysis, 
            self.btn_nav_team_analysis, self.btn_nav_limitless, self.btn_nav_build_compare
        ]
        for btn in self.nav_buttons:
            btn.setCheckable(True)
            sidebar_layout.addWidget(btn)

        self.btn_nav_import.clicked.connect(self.show_import_view)
        self.btn_nav_mass_import.clicked.connect(self.show_mass_import_view)
        self.btn_nav_list.clicked.connect(self.show_list_view)
        self.btn_nav_meta_stats.clicked.connect(self.show_meta_stats)
        self.btn_nav_core_analysis.clicked.connect(self.show_core_analysis)
        self.btn_nav_team_analysis.clicked.connect(self.show_team_analysis)
        self.btn_nav_limitless.clicked.connect(self.show_limitless_tournaments)
        self.btn_nav_build_compare.clicked.connect(self.show_build_compare)

        sidebar_layout.addStretch()
        
        body_layout.addWidget(self.sidebar)

        # StackedWidget per le diverse schermate (nel Body a destra)
        self.stacked_widget = QStackedWidget()
        body_layout.addWidget(self.stacked_widget)
        
        main_layout.addWidget(self.body_widget)
        
        # top_bar needs to be raised so the drop shadow falls over body_widget
        self.top_bar.raise_()

        # Le schermate dell'app
        self.home_view = HomeWidget(self)
        self.home_view.navigate_to_list.connect(self.show_list_view)
        self.home_view.navigate_to_import.connect(self.show_import_view)
        self.home_view.navigate_to_mass_import.connect(self.show_mass_import_view)
        self.home_view.navigate_to_meta_stats.connect(self.show_meta_stats)
        self.home_view.navigate_to_core_analysis.connect(self.show_core_analysis)
        self.home_view.navigate_to_team_analysis.connect(self.show_team_analysis)
        self.home_view.navigate_to_build_compare.connect(self.show_build_compare)

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
        self.limitless_tournaments_view = LimitlessTournamentsWidget(self)
        self.limitless_detail_view = LimitlessTournamentDetailWidget(self)
        self.build_compare_view = BuildAndCompareWidget()
        
        # Connetti segnali build
        self.team_analysis_view.show_builds_signal.connect(self.show_variant_builds)
        self.variant_builds_view.back_signal.connect(self.show_team_analysis)
        self.variant_builds_view.import_signal.connect(self.handle_variant_import)

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
        self.stacked_widget.addWidget(self.limitless_tournaments_view) # Indice 13
        self.stacked_widget.addWidget(self.limitless_detail_view) # Indice 14
        self.stacked_widget.addWidget(self.build_compare_view) # Indice 15
        self.stacked_widget.addWidget(self.home_view) # Indice 16


        # Signal connections
        self.list_view.replay_selected.connect(self.show_detail_view)
        self.detail_view.back_requested.connect(self.show_list_view)
        self.detail_view.link_clicked.connect(self.navigate_to_catalog)
        self.detail_view.title_changed.connect(self.lbl_global_title.setText)
        self.move_detail_view.back_requested.connect(self.go_back)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # ── Loading Overlay globale (sopra tutto il body) ───────────
        # Creato DOPO setCentralWidget per avere il parent corretto
        self._loading_overlay = LoadingOverlay(self.body_widget)
        self._loading_overlay.hide()

        # ── Inizializzazione dimensione sidebar ─────────────────────
        self.sidebar.setMaximumWidth(232)

        # Connessioni dei segnali tra schermate
        self.list_view.replay_selected.connect(self.show_detail_view)
        self.detail_view.back_requested.connect(self.show_list_view)
        self.limitless_tournaments_view.tournament_selected.connect(self.show_limitless_detail)
        self.limitless_detail_view.back_requested.connect(self.show_limitless_tournaments)

        # Mostra la Home all'avvio
        self.show_home_view()

    def update_nav_buttons(self, active_btn):
        for btn in self.nav_buttons:
            if hasattr(self, 'nav_buttons') and btn:
                btn.setChecked(btn == active_btn)

    def toggle_sidebar(self):
        """Slide sidebar in/out con QPropertyAnimation (200ms OutCubic).
        Cambia anche l'icona del bottone per feedback immediato di stato."""
        SIDEBAR_WIDTH = 232
        is_open = self.sidebar.maximumWidth() >= SIDEBAR_WIDTH

        self._sidebar_anim = QPropertyAnimation(self.sidebar, b"maximumWidth")
        self._sidebar_anim.setDuration(200)
        self._sidebar_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        if is_open:
            # Chiudi — collassa sidebar
            self._sidebar_anim.setStartValue(self.sidebar.width())
            self._sidebar_anim.setEndValue(0)
            self.btn_toggle_sidebar.setText("✕")
        else:
            # Apri — espandi sidebar
            self.sidebar.setVisible(True)
            self._sidebar_anim.setStartValue(self.sidebar.width())
            self._sidebar_anim.setEndValue(SIDEBAR_WIDTH)
            self.btn_toggle_sidebar.setText("☰")

        self._sidebar_anim.start()

    def show_loading(self, message: str = "Elaborazione in corso..."):
        """Mostra l'overlay di caricamento globale."""
        self._loading_overlay.show(message)

    def hide_loading(self):
        """Nasconde l'overlay di caricamento globale."""
        self._loading_overlay.hide()

    def show_home_view(self):
        self.update_nav_buttons(None)
        self.lbl_global_title.setText("Home")
        self.stacked_widget.setCurrentIndex(16)
        # Assicura che la sidebar sia chiusa
        SIDEBAR_WIDTH = 232
        if self.sidebar.maximumWidth() >= SIDEBAR_WIDTH:
            self.toggle_sidebar()

    def show_import_view(self):
        self.update_nav_buttons(self.btn_nav_import)
        self.lbl_global_title.setText("Importa Replay")
        self.stacked_widget.setCurrentIndex(0)

    def show_mass_import_view(self):
        self.update_nav_buttons(self.btn_nav_mass_import)
        self.lbl_global_title.setText("Importazione Massiva")
        self.stacked_widget.setCurrentIndex(9)
        
    def show_meta_stats(self):
        self.update_nav_buttons(self.btn_nav_meta_stats)
        self.lbl_global_title.setText("Meta Analysis VGC")
        self.stacked_widget.setCurrentIndex(8)
        
    def show_core_analysis(self):
        self.update_nav_buttons(self.btn_nav_core_analysis)
        self.lbl_global_title.setText("Analisi Core")
        self.stacked_widget.setCurrentIndex(10)
        
    def show_team_analysis(self):
        self.update_nav_buttons(self.btn_nav_team_analysis)
        self.lbl_global_title.setText("Analisi Team & Archetipi")
        self.stacked_widget.setCurrentIndex(11)
        
    def show_variant_builds(self, variant):
        self.lbl_global_title.setText("Dettaglio Build Variante")
        self.variant_builds_view.load_variant(variant)
        self.stacked_widget.setCurrentIndex(12)

    def show_list_view(self):
        self.update_nav_buttons(self.btn_nav_list)
        self.lbl_global_title.setText("Libreria Replay VGC")
        self.list_view.load_replays()
        self.stacked_widget.setCurrentIndex(1)

    def show_detail_view(self, match_id: str):
        self.update_nav_buttons(None)
        self.lbl_global_title.setText("Dettaglio Match")
        self.detail_view.display_match(match_id)
        self.stacked_widget.setCurrentIndex(2)

    def show_limitless_tournaments(self):
        self.update_nav_buttons(self.btn_nav_limitless)
        self.lbl_global_title.setText("Tornei Limitless VGC")
        self.stacked_widget.setCurrentIndex(13)

    def show_limitless_detail(self, tournament_id: str, tournament_name: str):
        self.update_nav_buttons(None)
        self.lbl_global_title.setText("Dettaglio Torneo Limitless")
        self.limitless_detail_view.load_tournament(tournament_id, tournament_name)
        self.stacked_widget.setCurrentIndex(14)

    def show_build_compare(self):
        self.update_nav_buttons(self.btn_nav_build_compare)
        self.lbl_global_title.setText("Costruisci e Confronta")
        self.stacked_widget.setCurrentIndex(15)

    def handle_variant_import(self, paste_text: str):
        self.build_compare_view.txt_paste.setPlainText(paste_text)
        self.build_compare_view.on_add_team()
        self.show_build_compare()

    def navigate_to_catalog(self, url_str: str):
        # Esempio: "move:Incineroar", "item:Leftovers", "ability:Intimidate"
        parts = url_str.split(":", 1)
        if len(parts) == 2:
            cat = parts[0]
            val = parts[1]
            if cat == "move":
                self.lbl_global_title.setText("Catalogo Mosse")
                self.moves_view.load_data()
                self.moves_view.filter_input.setText(val)
                self.stacked_widget.setCurrentIndex(4)
            elif cat == "item":
                self.lbl_global_title.setText("Catalogo Strumenti")
                self.items_view.load_data()
                self.items_view.filter_input.setText(val)
                self.stacked_widget.setCurrentIndex(5)
            elif cat == "ability":
                self.lbl_global_title.setText("Catalogo Abilità")
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
    icon_path = os.path.join(base_path, "assets", "logo", "j.png")
    app.setWindowIcon(QIcon(icon_path))
    
    # ── Font globale nitido (fix header sgranato) ──────────────────
    # PreferFullHinting assicura il rendering ClearType su Windows.
    # Font size 10pt = 13px @96dpi (corrisponde al QSS font-size: 13px)
    _font = QFont("Inter", 10)
    _font.setStyleHint(QFont.StyleHint.SansSerif)
    _font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(_font)

    # Applica il Dark Theme Globale
    app.setStyle("Fusion")
    
    qss_path = os.path.join(base_path, "assets", "styles", "main.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    else:
        print(f"Attenzione: Impossibile trovare il file di stile in {qss_path}")
    
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())