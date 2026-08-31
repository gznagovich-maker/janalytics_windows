import os
from typing import List, Dict, Any, Tuple
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QComboBox, QSpinBox, QStackedWidget, QFrame, QTextEdit, 
    QMessageBox, QScrollArea, QApplication, QCheckBox, QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QColor, QFont
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtGui import QTextDocument

from config.theme import Palette
from domain.smogon_calc import SmogonDamageCalc
from domain.bulk_optimizer import BulkOptimizer
from src.domain.batch_generator_service import BatchGeneratorService
from src.domain.team_builder_service import parse_pokepaste
from src.utils.icon_utils import get_pokemon_icon_path

def get_pokemon_pixmap(species: str, size: int = 48) -> QPixmap:
    if not species: return None
    path = get_pokemon_icon_path(species)
    if path and os.path.exists(path):
        return QPixmap(path).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return None

class BulkOptimizerWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(list) # list of (pokemon_idx, best_spread, report, status_msg)
    error = Signal(str)

    def __init__(self, team_members: list, selected_indices: list, budget: int, format_name: str, top_n: int, screens: dict = None):
        super().__init__()
        self.team_members = team_members
        self.selected_indices = selected_indices
        self.budget = budget
        self.format_name = format_name
        self.top_n = top_n
        self.screens = screens or {}

    def run(self):
        try:
            self.progress.emit(10, "Estrazione Meta Threats...")
            meta_pool = BatchGeneratorService.generate_threats_from_format(self.format_name, 1.0, top_n_species=self.top_n)
            
            if not meta_pool:
                self.error.emit(f"Nessun dato meta trovato per il formato {self.format_name}.")
                return
                
            self.progress.emit(20, "Inizializzazione Motore Smogon...")
            calc = SmogonDamageCalc(db_path="janalytics.db")
            optimizer = BulkOptimizer(calc)
            
            results = []
            
            total_pokemon = len(self.selected_indices)
            for i, p_idx in enumerate(self.selected_indices):
                m = self.team_members[p_idx]
                target_pokemon = {
                    "name": m.species,
                    "options": {
                        "nature": m.nature if m.nature else "Serious",
                        "item": m.item,
                        "evs": m.evs if m.evs else {}
                    }
                }
                
                def cb_prog(pct):
                    base = 20 + int((i / total_pokemon) * 80)
                    step = int((pct / 100) * (80 / total_pokemon))
                    self.progress.emit(base + step, f"Ottimizzazione in corso per {m.species}...")
                    
                best_spread, report, status_msg = optimizer.optimize_pokemon_bulk(
                    target_pokemon, meta_pool, budget=self.budget, report_limit=self.top_n, progress_callback=cb_prog, screens=self.screens
                )
                
                results.append((p_idx, best_spread, report, status_msg))
                
            self.progress.emit(100, "Ottimizzazione completata!")
            self.finished.emit(results)
            
        except Exception as e:
            self.error.emit(str(e))


class BulkOptimizerView(QWidget):
    def __init__(self, parent_main):
        super().__init__()
        self.parent_main = parent_main
        self.parsed_members = []
        self.checkboxes = []
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # --- HEADER ---
        header_layout = QHBoxLayout()
        lbl_title = QLabel("Bulk Optimizer (AOB)")
        lbl_title.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 20px; font-weight: bold;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)
        
        # --- SPLIT LAYOUT ---
        split_layout = QHBoxLayout()
        
        # LEFT: Input and Config
        left_panel = QVBoxLayout()
        
        self.paste_input = QTextEdit()
        self.paste_input.setPlaceholderText("Incolla qui il tuo team in formato PokéPaste per ottimizzarne il bulk...")
        self.paste_input.setMaximumHeight(200)
        self.paste_input.setStyleSheet(f"background: {Palette.BG_APP}; color: {Palette.TEXT_PRIMARY}; border: 1px solid {Palette.BORDER_COLOR};")
        left_panel.addWidget(self.paste_input)
        
        self.btn_parse = QPushButton("Analizza Team")
        self.btn_parse.setCursor(Qt.PointingHandCursor)
        self.btn_parse.setStyleSheet(f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; font-weight: bold; padding: 8px;")
        self.btn_parse.clicked.connect(self._parse_paste)
        left_panel.addWidget(self.btn_parse)
        
        # Pokemon Selection
        self.pokemon_list_frame = QFrame()
        self.pokemon_list_frame.setStyleSheet(f"background: {Palette.BG_SURFACE_ELEVATED}; border: 1px solid {Palette.BORDER_COLOR}; border-radius: 6px;")
        self.pokemon_list_layout = QVBoxLayout(self.pokemon_list_frame)
        self.pokemon_list_layout.addWidget(QLabel("Seleziona i Pokémon da ottimizzare:"))
        left_panel.addWidget(self.pokemon_list_frame)
        
        # EV Config
        config_frame = QFrame()
        config_frame.setStyleSheet(f"background: {Palette.BG_SURFACE_ELEVATED}; border: 1px solid {Palette.BORDER_COLOR}; border-radius: 6px;")
        config_layout = QVBoxLayout(config_frame)
        config_layout.addWidget(QLabel("Configurazione Ottimizzazione (Regole AOB):"))
        
        h_format = QHBoxLayout()
        h_format.addWidget(QLabel("Formato Meta:"))
        self.cb_format = QComboBox()
        self.cb_format.addItems(BatchGeneratorService.get_available_formats())
        h_format.addWidget(self.cb_format)
        config_layout.addLayout(h_format)
        
        h_budget = QHBoxLayout()
        h_budget.addWidget(QLabel("Budget EV per il Bulk:"))
        self.spin_budget = QSpinBox()
        self.spin_budget.setRange(0, 508) # Manteniamo il range max per flessibilità, ma cambiamo il default
        self.spin_budget.setValue(66) # Default reasonable budget
        h_budget.addWidget(self.spin_budget)
        config_layout.addLayout(h_budget)
        
        h_topn = QHBoxLayout()
        h_topn.addWidget(QLabel("Simula contro le Top N minacce:"))
        self.spin_topn = QSpinBox()
        self.spin_topn.setRange(1, 100)
        self.spin_topn.setValue(20) # Top 20 is a good baseline
        h_topn.addWidget(self.spin_topn)
        config_layout.addLayout(h_topn)
        
        # Screens Config
        h_screens = QHBoxLayout()
        h_screens.addWidget(QLabel("Schermi Attivi:"))
        self.chk_reflect = QCheckBox("Reflect")
        self.chk_lightscreen = QCheckBox("Light Screen")
        self.chk_auroraveil = QCheckBox("Aurora Veil")
        h_screens.addWidget(self.chk_reflect)
        h_screens.addWidget(self.chk_lightscreen)
        h_screens.addWidget(self.chk_auroraveil)
        config_layout.addLayout(h_screens)
        
        left_panel.addWidget(config_frame)
        
        self.btn_start = QPushButton("🚀 Avvia Ottimizzazione Bulk")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setStyleSheet(f"background-color: {Palette.SECONDARY}; color: {Palette.BG_APP}; font-weight: bold; padding: 12px;")
        self.btn_start.clicked.connect(self._start_optimization)
        self.btn_start.setEnabled(False)
        left_panel.addWidget(self.btn_start)
        left_panel.addStretch()
        
        split_layout.addLayout(left_panel, 1)
        
        # RIGHT: Results
        right_panel = QVBoxLayout()
        self.btn_export_pdf = QPushButton("📄 Esporta Report PDF")
        self.btn_export_pdf.setCursor(Qt.PointingHandCursor)
        self.btn_export_pdf.setStyleSheet(f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; font-weight: bold; padding: 8px;")
        self.btn_export_pdf.clicked.connect(self._export_pdf)
        self.btn_export_pdf.hide()
        
        right_header = QHBoxLayout()
        right_header.addWidget(QLabel("Risultati Ottimizzazione:"))
        right_header.addStretch()
        right_header.addWidget(self.btn_export_pdf)
        right_panel.addLayout(right_header)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background: transparent; border: none;")
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.results_container)
        
        right_panel.addWidget(scroll)
        split_layout.addLayout(right_panel, 2)
        
        main_layout.addLayout(split_layout)

    def _parse_paste(self):
        text = self.paste_input.toPlainText().strip()
        if not text:
            return
            
        self.parsed_members = parse_pokepaste(text, corrections={})
        if not self.parsed_members:
            QMessageBox.warning(self, "Errore", "Nessun Pokémon valido trovato nel paste.")
            return
            
        # Clear old checkboxes
        for i in reversed(range(self.pokemon_list_layout.count())):
            item = self.pokemon_list_layout.itemAt(i)
            if item.widget() and isinstance(item.widget(), QCheckBox):
                item.widget().setParent(None)
                
        self.checkboxes = []
        for idx, member in enumerate(self.parsed_members):
            cb = QCheckBox(member.species)
            cb.setChecked(True)
            self.checkboxes.append((idx, cb))
            self.pokemon_list_layout.addWidget(cb)
            
        self.btn_start.setEnabled(True)

    def _start_optimization(self):
        selected_indices = [idx for idx, cb in self.checkboxes if cb.isChecked()]
        if not selected_indices:
            QMessageBox.warning(self, "Attenzione", "Seleziona almeno un Pokémon da ottimizzare.")
            return
            
        format_name = self.cb_format.currentText()
        if not format_name:
            QMessageBox.warning(self, "Attenzione", "Nessun formato Meta selezionato.")
            return
            
        self.parent_main.show_loading("Inizializzazione Ottimizzatore Bulk...")
        self.btn_start.setEnabled(False)
        self.btn_parse.setEnabled(False)
        
        # Clear results
        for i in reversed(range(self.results_layout.count())):
            item = self.results_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
                
        self.btn_export_pdf.hide()
        self.current_results_html = "" # store for PDF export
        
        screens = {
            "isReflect": self.chk_reflect.isChecked(),
            "isLightScreen": self.chk_lightscreen.isChecked(),
            "isAuroraVeil": self.chk_auroraveil.isChecked()
        }
        
        self.worker = BulkOptimizerWorker(
            team_members=self.parsed_members,
            selected_indices=selected_indices,
            budget=self.spin_budget.value(),
            format_name=format_name,
            top_n=self.spin_topn.value(),
            screens=screens
        )
        self.worker.progress.connect(self._update_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _update_progress(self, pct: int, msg: str):
        if hasattr(self.parent_main, "_loading_overlay"):
            self.parent_main._loading_overlay._message = f"{msg} ({pct}%)"

    def _on_finished(self, results):
        self.parent_main.hide_loading()
        self.btn_start.setEnabled(True)
        self.btn_parse.setEnabled(True)
        
        html_report = f"<h1>Report Algoritmo Ottimizzazione Bulk (AOB)</h1>\n<p>Meta: {self.cb_format.currentText()} - Budget EV: {self.spin_budget.value()}</p>\n<hr>\n"
        
        for p_idx, spread, report, status_msg in results:
            member = self.parsed_members[p_idx]
            
            frame = QFrame()
            frame.setStyleSheet(f"background: {Palette.BG_SURFACE}; border: 1px solid {Palette.BORDER_COLOR}; border-radius: 8px; padding: 10px;")
            layout = QVBoxLayout(frame)
            
            # Header del pokemon
            h_header = QHBoxLayout()
            icon_lbl = QLabel()
            pix = get_pokemon_pixmap(member.species, 48)
            if pix: icon_lbl.setPixmap(pix)
            h_header.addWidget(icon_lbl)
            
            v_title = QVBoxLayout()
            title = QLabel(f"{member.species} - Spread Ottimale: {spread['hp']} HP / {spread['def']} Def / {spread['spd']} SpD (Usati: {spread.get('total', 0)} EV)")
            title.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 16px; font-weight: bold;")
            v_title.addWidget(title)
            
            nature_name = spread.get('nature', 'Serious').capitalize()
            stats_str = f"Natura: {nature_name} | Statistiche L.50 -> HP: {spread.get('final_hp', '?')} | Def: {spread.get('final_def', '?')} | SpD: {spread.get('final_spd', '?')}"
            subtitle = QLabel(stats_str)
            subtitle.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 14px;")
            v_title.addWidget(subtitle)
            
            h_header.addLayout(v_title)
            h_header.addStretch()
            layout.addLayout(h_header)
            
            lbl_status = QLabel(status_msg)
            lbl_status.setStyleSheet("color: #a0a0a0; font-style: italic;")
            layout.addWidget(lbl_status)
            
            # Tabella Danni
            table = QTableWidget()
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels(["Attaccante (Build)", "Mossa", "Categoria", "Danno Max (Base/Schermi)"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setRowCount(len(report))
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            
            html_report += f"<h2>{member.species}</h2>\n"
            html_report += f"<p>Spread: <b>{spread['hp']} HP / {spread['def']} Def / {spread['spd']} SpD</b></p>\n"
            html_report += f"<p>Statistiche L.50: <b>Natura {nature_name} | HP {spread.get('final_hp', '?')} | Def {spread.get('final_def', '?')} | SpD {spread.get('final_spd', '?')}</b></p>\n"
            html_report += f"<p><i>{status_msg}</i></p>\n"
            html_report += "<table border='1' cellspacing='0' cellpadding='5' width='100%'>\n"
            html_report += "<tr><th>Attaccante (Build)</th><th>Mossa</th><th>Categoria</th><th>Danno Max (Base/Schermi)</th></tr>\n"
            
            for row_idx, r in enumerate(report):
                atk_build = f"{r['attacker']}\n({r.get('attacker_nature','')} | {r.get('attacker_ev',0)} {r.get('attacker_stat','')} | {r.get('attacker_item','')})"
                table.setItem(row_idx, 0, QTableWidgetItem(atk_build))
                table.setItem(row_idx, 1, QTableWidgetItem(r["move"]))
                table.setItem(row_idx, 2, QTableWidgetItem(r["category"]))
                
                pct_str = f"{r['damage_pct']:.1f}% ({r['damage_abs']} HP)"
                if 'damage_no_screen_pct' in r and r['damage_no_screen_pct'] != r['damage_pct']:
                    pct_str = f"Base: {r['damage_no_screen_pct']:.1f}%\nSchermi: {r['damage_pct']:.1f}% ({r['damage_abs']} HP)"
                    
                item_dmg = QTableWidgetItem(pct_str)
                if r["ko"]:
                    item_dmg.setForeground(QColor("#ff4444"))
                else:
                    item_dmg.setForeground(QColor("#44ff44"))
                    
                table.setItem(row_idx, 3, item_dmg)
                
                # HTML builder
                ko_color = "red" if r["ko"] else "green"
                atk_build_html = f"<b>{r['attacker']}</b><br><small>{r.get('attacker_nature','')} | {r.get('attacker_ev',0)} {r.get('attacker_stat','')} | {r.get('attacker_item','')}</small>"
                
                html_pct = f"{r['damage_pct']:.1f}% ({r['damage_abs']} HP)"
                if 'damage_no_screen_pct' in r and r['damage_no_screen_pct'] != r['damage_pct']:
                    html_pct = f"<span style='color:gray;'>Base: {r['damage_no_screen_pct']:.1f}%</span><br><b>Schermi: {r['damage_pct']:.1f}%</b> ({r['damage_abs']} HP)"
                
                html_report += f"<tr><td>{atk_build_html}</td><td>{r['move']}</td><td>{r['category']}</td><td style='color:{ko_color};'>{html_pct}</td></tr>\n"
                
            table.resizeRowsToContents()
            html_report += "</table><br><br>\n"
            
            # Fissa altezza tabella per non scrollare due volte
            table.setMinimumHeight(200)
            layout.addWidget(table)
            
            self.results_layout.addWidget(frame)
            
        self.current_results_html = html_report
        self.btn_export_pdf.show()

    def _export_pdf(self):
        if not self.current_results_html:
            return
            
        import os
        from PySide6.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Salva Report PDF", "Report_Bulk.pdf", "PDF Files (*.pdf)")
        if file_path:
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(file_path)
            
            doc = QTextDocument()
            doc.setHtml(self.current_results_html)
            doc.print_(printer)
            QMessageBox.information(self, "Completato", f"Report esportato con successo in:\n{file_path}")

    def _on_error(self, err):
        self.parent_main.hide_loading()
        self.btn_start.setEnabled(True)
        self.btn_parse.setEnabled(True)
        QMessageBox.critical(self, "Errore", f"Errore durante l'ottimizzazione Bulk:\n{err}")
