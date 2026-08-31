import os
from typing import List, Dict, Any, Tuple
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QComboBox, QSpinBox, QStackedWidget, QFrame, QTextEdit, 
    QMessageBox, QScrollArea, QApplication, QProgressBar, QRadioButton, QButtonGroup, QTabWidget
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QColor, QFont
from config.theme import Palette

from domain.smogon_calc import SmogonDamageCalc
from domain.team_optimizer import TeamOptimizer
from views.bulk_optimizer_view import BulkOptimizerView
from src.domain.batch_generator_service import BatchGeneratorService
from src.domain.team_builder_service import parse_pokepaste
from src.utils.icon_utils import get_pokemon_icon_path

def get_pokemon_pixmap(species: str, size: int = 48) -> QPixmap:
    if not species: return None
    path = get_pokemon_icon_path(species)
    if path and os.path.exists(path):
        return QPixmap(path).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return None

class OptimizerWorker(QThread):
    progress = Signal(int, str)
    finished_generate = Signal(list, float)
    finished_optimize = Signal(list, float, list)
    error = Signal(str)

    def __init__(self, mode: str, format_name: str, min_usage: float, restarts: int, max_iter: int, top_n: int, initial_paste: str = None):
        super().__init__()
        self.mode = mode
        self.format_name = format_name
        self.min_usage = min_usage
        self.restarts = restarts
        self.max_iter = max_iter
        self.top_n = top_n
        self.initial_paste = initial_paste

    def run(self):
        try:
            self.progress.emit(10, "Generazione Pool e Threats dal DB...")
            # We use threats from format as both the pool and the threats for simplicity and speed.
            # In a full implementation, the pool could be the top 50 most used sets.
            meta_pool = BatchGeneratorService.generate_threats_from_format(self.format_name, self.min_usage, top_n_species=self.top_n)
            
            if not meta_pool:
                self.error.emit(f"Nessun dato trovato per il formato {self.format_name}.")
                return
                
            self.progress.emit(20, f"Inizializzazione Motore su {len(meta_pool)} elementi...")
            calc = SmogonDamageCalc(db_path="janalytics.db")
            optimizer = TeamOptimizer(calc)
            
            def cb_matrices(pct):
                self.progress.emit(20 + int(pct * 0.4), "Calcolo Matrici Danni/Speed...")
                
            optimizer.build_matrices(meta_pool, meta_pool, progress_callback=cb_matrices)
            
            if self.mode == "generate":
                def cb_gen(pct):
                    self.progress.emit(60 + int(pct * 0.2), f"Ottimizzazione Hill Climbing (Restarts)...")
                
                best_team_idx, best_score = optimizer.hill_climb_generate(restarts=self.restarts, progress_callback=cb_gen)
                best_team_builds = [meta_pool[i] for i in best_team_idx]
                
                self.progress.emit(85, "Fase 2: Ottimizzazione EV Spreads...")
                final_team, final_score = optimizer.optimize_evs_for_team(best_team_builds, meta_pool)
                
                self.finished_generate.emit(final_team, final_score)
                
            elif self.mode == "optimize":
                if not self.initial_paste:
                    self.error.emit("Nessun team in input.")
                    return
                    
                members = parse_pokepaste(self.initial_paste, corrections={})
                if not members:
                    self.error.emit("Impossibile parsare il team iniziale.")
                    return
                    
                # Aggiungiamo i membri del team al pool (o li mappiamo)
                # Per semplicità, aggiungiamo il team alla fine del pool temporaneamente
                initial_team_builds = []
                for m in members:
                    initial_team_builds.append({
                        "name": m.species,
                        "options": {
                            "nature": m.nature,
                            "item": m.item,
                            "evs": m.evs if m.evs else {}
                        },
                        "common_moves": [mv for mv in m.moves if mv]
                    })
                    
                # Estendiamo il pool
                extended_pool = meta_pool + initial_team_builds
                
                self.progress.emit(20, "Ricalcolo Matrici con il Team in input...")
                optimizer.build_matrices(extended_pool, meta_pool, progress_callback=cb_matrices)
                
                initial_indices = list(range(len(meta_pool), len(extended_pool)))
                
                def cb_opt(pct):
                    self.progress.emit(60 + int(pct * 0.2), f"Ottimizzazione Team (Iterazioni)...")
                    
                final_team_idx, pre_score, replaced = optimizer.hill_climb_optimize(initial_indices, max_iter=self.max_iter, progress_callback=cb_opt)
                final_team_builds = [extended_pool[i] for i in final_team_idx]
                
                self.progress.emit(85, "Fase 2: Ottimizzazione EV Spreads...")
                final_team, final_score = optimizer.optimize_evs_for_team(final_team_builds, meta_pool)
                
                # Calcoliamo i diff
                diff_info = []
                original_species = [b["name"] for b in initial_team_builds]
                for final_build in final_team:
                    if final_build["name"] not in original_species:
                        diff_info.append("NEW")
                    else:
                        diff_info.append("KEPT")
                        
                self.finished_optimize.emit(final_team, final_score, diff_info)
                
        except Exception as e:
            self.error.emit(str(e))

class TeamOptimizerView(QWidget):
    def __init__(self, parent_main):
        super().__init__()
        self.parent_main = parent_main
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {Palette.BORDER_COLOR}; border-radius: 4px; top: -1px; }}
            QTabBar::tab {{ background: {Palette.BG_SURFACE_ELEVATED}; color: {Palette.TEXT_PRIMARY}; padding: 10px 20px; border: 1px solid {Palette.BORDER_COLOR}; border-bottom-color: {Palette.BORDER_COLOR}; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
            QTabBar::tab:selected {{ background: {Palette.BG_APP}; border-bottom-color: {Palette.BG_APP}; font-weight: bold; color: {Palette.PRIMARY}; }}
        """)
        main_layout.addWidget(self.tabs)
        
        # Tab 1: Hill Climbing (Genera/Ottimizza)
        tab_hill_climbing = QWidget()
        hc_layout = QVBoxLayout(tab_hill_climbing)
        hc_layout.setContentsMargins(20, 20, 20, 20)
        hc_layout.setSpacing(15)
        
        # --- HEADER ---
        header_layout = QHBoxLayout()
        lbl_title = QLabel("Team Builder Ottimizzato (Hill Climbing)")
        lbl_title.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 20px; font-weight: bold;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()
        hc_layout.addLayout(header_layout)
        
        # --- CONFIGURATORE ---
        config_frame = QFrame()
        config_frame.setStyleSheet(f"background: {Palette.BG_SURFACE_ELEVATED}; border: 1px solid {Palette.BORDER_COLOR}; border-radius: 8px;")
        config_layout = QVBoxLayout(config_frame)
        
        # 1. Selettore Formato
        format_layout = QHBoxLayout()
        lbl_fmt = QLabel("Formato di Riferimento:")
        lbl_fmt.setStyleSheet(f"color: {Palette.TEXT_PRIMARY}; font-weight: bold;")
        self.cmb_format = QComboBox()
        formats = BatchGeneratorService.get_available_formats()
        self.cmb_format.addItems(formats)
        format_layout.addWidget(lbl_fmt)
        format_layout.addWidget(self.cmb_format)
        format_layout.addStretch()
        config_layout.addLayout(format_layout)
        
        # 2. Selettore Modalità
        mode_layout = QHBoxLayout()
        self.btn_group_mode = QButtonGroup(self)
        self.radio_generate = QRadioButton("Genera da Zero")
        self.radio_optimize = QRadioButton("Ottimizza Team")
        self.radio_generate.setChecked(True)
        self.btn_group_mode.addButton(self.radio_generate)
        self.btn_group_mode.addButton(self.radio_optimize)
        
        self.radio_generate.toggled.connect(self._on_mode_changed)
        
        mode_layout.addWidget(QLabel("Modalità:"))
        mode_layout.addWidget(self.radio_generate)
        mode_layout.addWidget(self.radio_optimize)
        mode_layout.addStretch()
        config_layout.addLayout(mode_layout)
        
        # 3. Stacked per input specifici
        self.stacked_inputs = QStackedWidget()
        
        # Pagina Genera
        page_gen = QWidget()
        page_gen_layout = QVBoxLayout(page_gen)
        page_gen_layout.setContentsMargins(0,0,0,0)
        
        gen_restarts_layout = QHBoxLayout()
        lbl_restarts = QLabel("Numero di Restarts:")
        self.spn_restarts = QSpinBox()
        self.spn_restarts.setRange(1, 100)
        self.spn_restarts.setValue(10)
        gen_restarts_layout.addWidget(lbl_restarts)
        gen_restarts_layout.addWidget(self.spn_restarts)
        gen_restarts_layout.addStretch()
        
        gen_pool_layout = QHBoxLayout()
        lbl_pool = QLabel("Dimensione Pool (Top N Meta):")
        self.spn_pool = QSpinBox()
        self.spn_pool.setRange(6, 200)
        self.spn_pool.setValue(50)
        gen_pool_layout.addWidget(lbl_pool)
        gen_pool_layout.addWidget(self.spn_pool)
        gen_pool_layout.addStretch()
        
        page_gen_layout.addLayout(gen_pool_layout)
        page_gen_layout.addLayout(gen_restarts_layout)
        page_gen_layout.addStretch()
        self.stacked_inputs.addWidget(page_gen)
        
        # Pagina Ottimizza
        page_opt = QWidget()
        page_opt_layout = QVBoxLayout(page_opt)
        page_opt_layout.setContentsMargins(0,0,0,0)
        
        lbl_paste = QLabel("Incolla PokéPaste del Team di Partenza:")
        self.txt_paste = QTextEdit()
        self.txt_paste.setMaximumHeight(100)
        
        opt_iter_layout = QHBoxLayout()
        lbl_iter = QLabel("Iterazioni Massime (Max_Iter):")
        self.spn_iter = QSpinBox()
        self.spn_iter.setRange(10, 5000)
        self.spn_iter.setValue(500)
        opt_iter_layout.addWidget(lbl_iter)
        opt_iter_layout.addWidget(self.spn_iter)
        opt_iter_layout.addStretch()
        
        page_opt_layout.addWidget(lbl_paste)
        page_opt_layout.addWidget(self.txt_paste)
        page_opt_layout.addLayout(opt_iter_layout)
        self.stacked_inputs.addWidget(page_opt)
        
        config_layout.addWidget(self.stacked_inputs)
        
        # Bottone Avvia
        self.btn_start = QPushButton("Avvia Ottimizzazione")
        self.btn_start.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.TERTIARY}; color: {Palette.TEXT_PRIMARY}; border: none; padding: 10px; border-radius: 6px; font-weight: bold; font-size: 14px; }}"
            f"QPushButton:hover {{ background-color: {Palette.SECONDARY}; color: {Palette.BG_APP}; }}"
            f"QPushButton:disabled {{ background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_MUTED}; }}"
        )
        self.btn_start.clicked.connect(self._start_optimization)
        config_layout.addWidget(self.btn_start)
        
        hc_layout.addWidget(config_frame)
        
        # --- RISULTATI ---
        self.results_frame = QFrame()
        self.results_frame.setStyleSheet(f"background: transparent; border: none;")
        self.results_layout = QVBoxLayout(self.results_frame)
        self.results_layout.setContentsMargins(0,0,0,0)
        
        self.lbl_score_delta = QLabel("")
        self.lbl_score_delta.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        self.btn_copy = QPushButton("📋 Copia Paste")
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setStyleSheet(
            f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold;"
        )
        self.btn_copy.clicked.connect(self._copy_optimized_team)
        self.btn_copy.hide() # Hidden initially
        
        res_header = QHBoxLayout()
        res_header.addWidget(self.lbl_score_delta)
        res_header.addStretch()
        res_header.addWidget(self.btn_copy)
        
        self.results_layout.addLayout(res_header)
        
        self.team_grid_layout = QHBoxLayout()
        self.results_layout.addLayout(self.team_grid_layout)
        self.current_optimized_team = None
        
        hc_layout.addWidget(self.results_frame)
        hc_layout.addStretch()
        
        self.tabs.addTab(tab_hill_climbing, "Costruzione / Ottimizzazione Hill Climbing")
        
        # Tab 2: Bulk Optimizer (AOB)
        self.bulk_opt_view = BulkOptimizerView(self.parent_main)
        self.tabs.addTab(self.bulk_opt_view, "Bulk Optimizer (AOB)")

    def _on_mode_changed(self):
        if self.radio_generate.isChecked():
            self.stacked_inputs.setCurrentIndex(0)
        else:
            self.stacked_inputs.setCurrentIndex(1)

    def _start_optimization(self):
        mode = "generate" if self.radio_generate.isChecked() else "optimize"
        fmt = self.cmb_format.currentText()
        min_u = 2.0
        
        if mode == "optimize" and not self.txt_paste.toPlainText().strip():
            QMessageBox.warning(self, "Attenzione", "Inserisci il team di partenza.")
            return

        self.btn_start.setEnabled(False)
        self.parent_main.show_loading("Avvio Motore...")
        
        self.worker = OptimizerWorker(
            mode=mode,
            format_name=fmt,
            min_usage=min_u,
            restarts=self.spn_restarts.value(),
            max_iter=self.spn_iter.value(),
            top_n=self.spn_pool.value() if mode == "generate" else 100, # Use 100 as default meta threats for optimize
            initial_paste=self.txt_paste.toPlainText() if mode == "optimize" else None
        )
        self.worker.progress.connect(self._update_progress)
        self.worker.finished_generate.connect(self._on_finished_gen)
        self.worker.finished_optimize.connect(self._on_finished_opt)
        self.worker.error.connect(self._on_error)
        self.worker.start()
        
    def _update_progress(self, pct: int, msg: str):
        if hasattr(self.parent_main, "_loading_overlay"):
            self.parent_main._loading_overlay._message = f"{msg} ({pct}%)"

    def _clear_grid(self):
        while self.team_grid_layout.count():
            item = self.team_grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
    def _render_team(self, team: list, diffs: list = None):
        self._clear_grid()
        for i, member in enumerate(team):
            card = QFrame()
            
            border_color = Palette.BORDER_COLOR
            if diffs and i < len(diffs):
                if diffs[i] == "NEW":
                    border_color = "#16A34A" # Green
                else:
                    border_color = Palette.BORDER_COLOR
                    
            card.setStyleSheet(f"background: {Palette.BG_SURFACE}; border: 2px solid {border_color}; border-radius: 8px; padding: 10px;")
            card_layout = QVBoxLayout(card)
            
            icon = QLabel()
            pixmap = get_pokemon_pixmap(member["name"], 64)
            if pixmap: icon.setPixmap(pixmap)
            
            lbl_name = QLabel(member["name"])
            lbl_name.setStyleSheet(f"font-weight: bold; color: {Palette.TEXT_PRIMARY}; border: none;")
            
            lbl_item = QLabel(member.get("options", {}).get("item", "Nessuno"))
            lbl_item.setStyleSheet(f"color: {Palette.TEXT_MUTED}; border: none; font-size: 11px;")
            
            card_layout.addWidget(icon, alignment=Qt.AlignCenter)
            card_layout.addWidget(lbl_name, alignment=Qt.AlignCenter)
            card_layout.addWidget(lbl_item, alignment=Qt.AlignCenter)
            
            self.team_grid_layout.addWidget(card)
            
        self.team_grid_layout.addStretch()

    def _on_finished_gen(self, team, score):
        self.parent_main.hide_loading()
        self.btn_start.setEnabled(True)
        self.lbl_score_delta.setText(f"Score di Vulnerabilità Ottenuto: <span style='color:{Palette.PRIMARY};'>{score:.2f}</span>")
        self.current_optimized_team = team
        self.btn_copy.show()
        self._render_team(team)
        
    def _on_finished_opt(self, team, final_score, diffs):
        self.parent_main.hide_loading()
        self.btn_start.setEnabled(True)
        self.lbl_score_delta.setText(f"Score di Vulnerabilità Finale: <span style='color:{Palette.PRIMARY};'>{final_score:.2f}</span>")
        self.current_optimized_team = team
        self.btn_copy.show()
        self._render_team(team, diffs)
        
    def _copy_optimized_team(self):
        if not self.current_optimized_team:
            return
            
        paste = ""
        
        def to_champ_ev(val: int) -> int:
            return (val + 4) // 8 if val > 0 else 0
            
        for member in self.current_optimized_team:
            opts = member.get("options", {})
            header = member.get("name", "").capitalize()
            item = opts.get("item", "")
            if item:
                header += f" @ {item}"
            paste += f"{header}\n"
            
            ability = opts.get("ability", "")
            if ability:
                paste += f"Ability: {ability}\n"
                
            paste += f"Level: {opts.get('level', 50)}\n"
            
            evs = opts.get("evs", {})
            total_evs = sum(evs.values())
            is_champ = total_evs <= 66
            
            display_labels = ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]
            
            ev_strings = []
            for label in display_labels:
                val = evs.get(label, evs.get(label.lower(), evs.get(label.upper(), 0)))
                if val > 0:
                    c_val = val if is_champ else to_champ_ev(val)
                    ev_strings.append(f"{c_val} {label}")
                    
            if ev_strings:
                paste += f"EVs: {' / '.join(ev_strings)}\n"
                
            nature = opts.get("nature", "")
            if nature:
                paste += f"{nature} Nature\n"
                
            for m in member.get("moves", []):
                if m:
                    paste += f"- {m}\n"
                    
            paste += "\n"
            
        if paste:
            QApplication.clipboard().setText(paste.strip())
            
    def _on_error(self, err):
        self.parent_main.hide_loading()
        self.btn_start.setEnabled(True)
        QMessageBox.critical(self, "Errore", f"Si è verificato un errore durante l'ottimizzazione:\n{err}")
