import os
from typing import List, Dict, Any, Tuple
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QStackedWidget, QFrame, QTextEdit, QTextBrowser,
    QMessageBox, QScrollArea, QApplication, QCheckBox, QGridLayout,
    QRadioButton, QButtonGroup
)
from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QColor, QFont, QTextDocument
from PySide6.QtPrintSupport import QPrinter

from config.theme import Palette, Fonts
from domain.smogon_calc import SmogonDamageCalc
from domain.offense_optimizer import OffenseOptimizer
from src.domain.batch_generator_service import BatchGeneratorService
from src.domain.team_builder_service import parse_pokepaste
from src.utils.icon_utils import get_pokemon_icon_path, get_item_icon_path


def get_pokemon_pixmap(species: str, size: int = 48) -> QPixmap:
    if not species:
        return None
    path = get_pokemon_icon_path(species)
    if path and os.path.exists(path):
        return QPixmap(path).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return None


def get_item_pixmap(item_name: str, size: int = 24) -> QPixmap:
    if not item_name:
        return None
    path = get_item_icon_path(item_name)
    if path and os.path.exists(path):
        return QPixmap(path).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return None


class OffenseOptimizerWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, team_members, selected_indices, budget, target_source,
                 format_name="", top_n=20, paste_targets="", screens=None,
                 vgcpaste_threats=None, is_static_mode=False):
        super().__init__()
        self.team_members = team_members
        self.selected_indices = selected_indices
        self.budget = budget
        self.target_source = target_source
        self.format_name = format_name
        self.top_n = top_n
        self.paste_targets = paste_targets
        self.screens = screens or {}
        self.vgcpaste_threats = vgcpaste_threats or []
        self.is_static_mode = is_static_mode

    def run(self):
        try:
            self.progress.emit(10, "Preparazione Bersagli (Regole 66 EVs)...")
            if self.target_source == "meta":
                defenders = BatchGeneratorService.generate_defensive_threats(
                    self.format_name, 1.0, top_n_species=self.top_n
                )
            elif self.target_source == "vgcpaste":
                defenders = self.vgcpaste_threats
            else:
                defenders = BatchGeneratorService.generate_threats_from_paste(self.paste_targets)

            if not defenders:
                self.error.emit("Nessun bersaglio valido trovato.")
                return

            self.progress.emit(20, "Inizializzazione Motore Smogon...")
            calc = SmogonDamageCalc(db_path="janalytics.db")
            optimizer = OffenseOptimizer(calc)

            results = []

            total_pokemon = len(self.selected_indices)
            for i, p_idx in enumerate(self.selected_indices):
                m = self.team_members[p_idx]

                # Lookup attacker base stats for speed tier comparison
                from database.connection import SessionLocal
                from database.models_v2 import PokemonSpeciesV2
                session = SessionLocal()
                try:
                    sp_model = session.query(PokemonSpeciesV2).filter(
                        PokemonSpeciesV2.name == m.species
                    ).first()
                    attacker_base_stats = {
                        "hp": sp_model.bst_hp if sp_model else 100,
                        "atk": sp_model.bst_atk if sp_model else 100,
                        "def": sp_model.bst_def if sp_model else 100,
                        "spa": sp_model.bst_spa if sp_model else 100,
                        "spd": sp_model.bst_spd if sp_model else 100,
                        "spe": sp_model.bst_spe if sp_model else 100
                    }
                finally:
                    session.close()

                target_pokemon = {
                    "name": m.species,
                    "options": {
                        "nature": m.nature if m.nature else "Serious",
                        "item": m.item,
                        "ability": m.ability,
                        "evs": m.evs if m.evs else {}
                    },
                    "moves": m.moves,
                    "baseStats": attacker_base_stats
                }

                def cb_prog(pct):
                    base = 20 + int((i / total_pokemon) * 80)
                    step = int((pct / 100) * (80 / total_pokemon))
                    self.progress.emit(base + step, f"Ottimizzazione in corso per {m.species}...")

                best_spread, report, status_msg = optimizer.optimize_pokemon_offense(
                    target_pokemon, defenders, budget=self.budget,
                    progress_callback=cb_prog, screens=self.screens,
                    is_static_mode=self.is_static_mode
                )

                results.append((p_idx, best_spread, report, status_msg))

            self.progress.emit(100, "Ottimizzazione completata!")
            self.finished.emit(results)

        except Exception as e:
            self.error.emit(str(e))


class OffenseOptimizerView(QWidget):
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
        lbl_title = QLabel("Offense Optimizer (AOO)")
        lbl_title.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 20px; font-weight: bold;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # --- SPLIT LAYOUT ---
        split_layout = QHBoxLayout()

        # LEFT: Input and Config
        left_panel = QVBoxLayout()

        self.paste_input = QTextEdit()
        self.paste_input.setPlaceholderText("Incolla qui il tuo team in formato PokePaste da ottimizzare offensivamente...")
        self.paste_input.setMaximumHeight(150)
        self.paste_input.setStyleSheet(f"background: {Palette.BG_APP}; color: {Palette.TEXT_PRIMARY}; border: 1px solid {Palette.BORDER_COLOR};")
        left_panel.addWidget(self.paste_input)

        h_buttons = QHBoxLayout()
        self.btn_parse = QPushButton("Analizza Team")
        self.btn_parse.setCursor(Qt.PointingHandCursor)
        self.btn_parse.setStyleSheet(f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; font-weight: bold; padding: 8px;")
        self.btn_parse.clicked.connect(self._parse_paste)
        h_buttons.addWidget(self.btn_parse)

        self.btn_load_vgcpaste = QPushButton("Carica da VGCPastes")
        self.btn_load_vgcpaste.setCursor(Qt.PointingHandCursor)
        self.btn_load_vgcpaste.setStyleSheet(f"background-color: {Palette.SECONDARY}; color: {Palette.BG_APP}; font-weight: bold; padding: 8px;")
        self.btn_load_vgcpaste.clicked.connect(self._load_vgcpaste_team)
        h_buttons.addWidget(self.btn_load_vgcpaste)
        
        left_panel.addLayout(h_buttons)

        # Pokemon Selection
        self.pokemon_list_frame = QFrame()
        self.pokemon_list_frame.setStyleSheet(f"background: {Palette.BG_SURFACE_ELEVATED}; border: 1px solid {Palette.BORDER_COLOR}; border-radius: 6px;")
        self.pokemon_list_layout = QVBoxLayout(self.pokemon_list_frame)
        self.pokemon_list_layout.addWidget(QLabel("Seleziona i Pokemon da ottimizzare:"))
        left_panel.addWidget(self.pokemon_list_frame)

        # Targets Config
        targets_frame = QFrame()
        targets_frame.setStyleSheet(f"background: {Palette.BG_SURFACE_ELEVATED}; border: 1px solid {Palette.BORDER_COLOR}; border-radius: 6px;")
        targets_layout = QVBoxLayout(targets_frame)
        targets_layout.addWidget(QLabel("Sorgente Bersagli:"))

        self.rb_meta = QRadioButton("Top N Meta Threats")
        self.rb_meta.setChecked(True)
        self.rb_paste = QRadioButton("Team Avversario (Showdown Paste)")
        self.rb_vgcpaste = QRadioButton("VGCPastes Import")

        self.bg_targets = QButtonGroup()
        self.bg_targets.addButton(self.rb_meta)
        self.bg_targets.addButton(self.rb_paste)
        self.bg_targets.addButton(self.rb_vgcpaste)

        targets_layout.addWidget(self.rb_meta)
        targets_layout.addWidget(self.rb_paste)
        targets_layout.addWidget(self.rb_vgcpaste)

        # VGCPaste info label
        self.vgcpaste_info_widget = QWidget()
        vgcpaste_info_layout = QVBoxLayout(self.vgcpaste_info_widget)
        vgcpaste_info_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_vgcpaste_count = QLabel("Nessun team importato. Importa prima dalla sezione VGCPastes.")
        self.lbl_vgcpaste_count.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px;")
        self.lbl_vgcpaste_count.setWordWrap(True)
        vgcpaste_info_layout.addWidget(self.lbl_vgcpaste_count)
        targets_layout.addWidget(self.vgcpaste_info_widget)
        self.vgcpaste_info_widget.hide()

        # Meta Config Widget
        self.meta_config_widget = QWidget()
        meta_layout = QVBoxLayout(self.meta_config_widget)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        h_format = QHBoxLayout()
        h_format.addWidget(QLabel("Formato Meta:"))
        self.cb_format = QComboBox()
        self.cb_format.addItems(BatchGeneratorService.get_available_formats())
        h_format.addWidget(self.cb_format)
        meta_layout.addLayout(h_format)

        h_topn = QHBoxLayout()
        h_topn.addWidget(QLabel("Top N minacce:"))
        self.spin_topn = QSpinBox()
        self.spin_topn.setRange(1, 100)
        self.spin_topn.setValue(20)
        h_topn.addWidget(self.spin_topn)
        meta_layout.addLayout(h_topn)
        targets_layout.addWidget(self.meta_config_widget)

        # Paste Config Widget
        self.paste_config_widget = QWidget()
        paste_layout = QVBoxLayout(self.paste_config_widget)
        paste_layout.setContentsMargins(0, 0, 0, 0)
        self.paste_targets_input = QTextEdit()
        self.paste_targets_input.setPlaceholderText("Incolla qui il team bersaglio...")
        self.paste_targets_input.setMaximumHeight(100)
        self.paste_targets_input.setStyleSheet(f"background: {Palette.BG_APP}; color: {Palette.TEXT_PRIMARY}; border: 1px solid {Palette.BORDER_COLOR};")
        paste_layout.addWidget(self.paste_targets_input)
        targets_layout.addWidget(self.paste_config_widget)

        self.paste_config_widget.hide()
        self.rb_meta.toggled.connect(self._toggle_targets)
        self.rb_paste.toggled.connect(self._toggle_targets)
        self.rb_vgcpaste.toggled.connect(self._toggle_targets)

        left_panel.addWidget(targets_frame)

        # EV Config
        config_frame = QFrame()
        config_frame.setStyleSheet(f"background: {Palette.BG_SURFACE_ELEVATED}; border: 1px solid {Palette.BORDER_COLOR}; border-radius: 6px;")
        config_layout = QVBoxLayout(config_frame)
        config_layout.addWidget(QLabel("Configurazione Ottimizzazione (Regole AOO):"))
        
        h_mode = QHBoxLayout()
        h_mode.addWidget(QLabel("Modalità Calcolo:"))
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["Ottimizzazione Algoritmica (Ricerca della miglior spread)", "Calcolo Statico (Usa EVs esatti dal paste incollato)"])
        h_mode.addWidget(self.cb_mode)
        config_layout.addLayout(h_mode)


        h_budget = QHBoxLayout()
        h_budget.addWidget(QLabel("Budget EV per l'Attacco:"))
        self.spin_budget = QSpinBox()
        self.spin_budget.setRange(0, 508)
        self.spin_budget.setValue(66)
        h_budget.addWidget(self.spin_budget)
        config_layout.addLayout(h_budget)

        # Screens Config
        h_screens = QHBoxLayout()
        h_screens.addWidget(QLabel("Difensori sotto schermi:"))
        self.chk_reflect = QCheckBox("Reflect")
        self.chk_lightscreen = QCheckBox("Light Screen")
        self.chk_auroraveil = QCheckBox("Aurora Veil")
        h_screens.addWidget(self.chk_reflect)
        h_screens.addWidget(self.chk_lightscreen)
        h_screens.addWidget(self.chk_auroraveil)
        config_layout.addLayout(h_screens)

        left_panel.addWidget(config_frame)

        self.btn_start = QPushButton("Avvia Ottimizzazione Offensiva")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setStyleSheet(f"background-color: {Palette.SECONDARY}; color: {Palette.BG_APP}; font-weight: bold; padding: 12px;")
        self.btn_start.clicked.connect(self._start_optimization)
        self.btn_start.setEnabled(False)
        left_panel.addWidget(self.btn_start)
        left_panel.addStretch()

        split_layout.addLayout(left_panel, 1)

        # RIGHT: Results
        right_panel = QVBoxLayout()

        right_header = QHBoxLayout()
        right_header.addWidget(QLabel("Risultati Ottimizzazione:"))
        right_header.addStretch()

        self.btn_export_pdf = QPushButton("Esporta Report PDF")
        self.btn_export_pdf.setCursor(Qt.PointingHandCursor)
        self.btn_export_pdf.setStyleSheet(f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; font-weight: bold; padding: 8px;")
        self.btn_export_pdf.clicked.connect(self._export_pdf)
        self.btn_export_pdf.hide()
        right_header.addWidget(self.btn_export_pdf)

        right_panel.addLayout(right_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.results_container)

        right_panel.addWidget(scroll)
        split_layout.addLayout(right_panel, 2)

        main_layout.addLayout(split_layout)

    def showEvent(self, event):
        super().showEvent(event)
        current = self.cb_format.currentText()
        self.cb_format.clear()
        self.cb_format.addItems(BatchGeneratorService.get_available_formats())
        if current:
            idx = self.cb_format.findText(current)
            if idx >= 0:
                self.cb_format.setCurrentIndex(idx)

    def _toggle_targets(self):
        is_meta = self.rb_meta.isChecked()
        is_vgcpaste = self.rb_vgcpaste.isChecked()
        self.meta_config_widget.setVisible(is_meta)
        self.paste_config_widget.setVisible(not is_meta and not is_vgcpaste)
        self.vgcpaste_info_widget.setVisible(is_vgcpaste)
        if is_vgcpaste:
            self._update_vgcpaste_count()

    def _parse_paste(self):
        text = self.paste_input.toPlainText().strip()
        if not text:
            return

        self.parsed_members = parse_pokepaste(text, corrections={})
        if not self.parsed_members:
            QMessageBox.warning(self, "Errore", "Nessun Pokemon valido trovato nel paste.")
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

    def _get_vgcpaste_imported_teams(self):
        if hasattr(self.parent_main, "gsheet_import_view"):
            return getattr(self.parent_main.gsheet_import_view, "_imported_teams", [])
        return []

    def _load_vgcpaste_team(self):
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QCursor
        
        imported_teams = self._get_vgcpaste_imported_teams()
        if not imported_teams:
            QMessageBox.warning(self, "Attenzione", "Nessun team importato. Vai alla sezione VGCPastes Import e carica dei team.")
            return
            
        menu = QMenu(self)
        for team in imported_teams:
            action = menu.addAction(team.team_name)
            action.setData(team)
            
        action = menu.exec(QCursor.pos())
        if action:
            team = action.data()
            self._paste_imported_team(team)
            
    def _paste_imported_team(self, team):
        paste_text = ""
        for member in team.members:
            header = member.species.capitalize()
            if member.item:
                header += f" @ {member.item}"
            paste_text += f"{header}\n"
            
            if member.ability:
                paste_text += f"Ability: {member.ability}\n"
                
            paste_text += f"Level: 50\n"
            
            if member.tera_type:
                paste_text += f"Tera Type: {member.tera_type}\n"
            
            if member.evs:
                ev_strings = []
                for k, v in member.evs.items():
                    if v > 0:
                        ev_strings.append(f"{v} {k.title()}")
                if ev_strings:
                    paste_text += f"EVs: {' / '.join(ev_strings)}\n"
                    
            if member.ivs:
                iv_strings = []
                for k, v in member.ivs.items():
                    if v < 31:
                        iv_strings.append(f"{v} {k.title()}")
                if iv_strings:
                    paste_text += f"IVs: {' / '.join(iv_strings)}\n"
                    
            if member.nature:
                paste_text += f"{member.nature} Nature\n"
                
            for m in member.moves:
                if m:
                    paste_text += f"- {m}\n"
                    
            paste_text += "\n"
            
        self.paste_input.setPlainText(paste_text.strip())
        self._parse_paste()

    def _start_optimization(self):
        selected_indices = [idx for idx, cb in self.checkboxes if cb.isChecked()]
        if not selected_indices:
            QMessageBox.warning(self, "Attenzione", "Seleziona almeno un Pokemon da ottimizzare.")
            return

        is_meta = self.rb_meta.isChecked()
        is_vgcpaste = self.rb_vgcpaste.isChecked()
        format_name = self.cb_format.currentText()

        if is_meta and not format_name:
            QMessageBox.warning(self, "Attenzione", "Nessun formato Meta selezionato.")
            return

        paste_targets = self.paste_targets_input.toPlainText().strip()
        if not is_meta and not is_vgcpaste and not paste_targets:
            QMessageBox.warning(self, "Attenzione", "Incolla il team bersaglio.")
            return

        # Pre-generate vgcpaste threats if needed
        vgcpaste_threats = []
        if is_vgcpaste:
            imported = self._get_vgcpaste_imported_teams()
            if not imported:
                QMessageBox.warning(
                    self, "Attenzione",
                    "Nessun team importato dalla sezione VGCPastes.\n"
                    "Importa prima i team dalla sezione VGCPastes Import."
                )
                return
            vgcpaste_threats = BatchGeneratorService.generate_threats_from_vgcpaste_imports(imported)
            if not vgcpaste_threats:
                QMessageBox.warning(self, "Attenzione", "Nessun bersaglio valido trovato nei team VGCPastes.")
                return

        # Determine target source
        if is_meta:
            target_source = "meta"
        elif is_vgcpaste:
            target_source = "vgcpaste"
        else:
            target_source = "paste"

        self.parent_main.show_loading("Inizializzazione Ottimizzatore Offensivo...")
        self.btn_start.setEnabled(False)
        self.btn_parse.setEnabled(False)

        # Clear results
        for i in reversed(range(self.results_layout.count())):
            item = self.results_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)

        self.btn_export_pdf.hide()
        self.latest_results = None

        screens = {
            "isReflect": self.chk_reflect.isChecked(),
            "isLightScreen": self.chk_lightscreen.isChecked(),
            "isAuroraVeil": self.chk_auroraveil.isChecked()
        }

        self.worker = OffenseOptimizerWorker(
            team_members=self.parsed_members,
            selected_indices=selected_indices,
            budget=self.spin_budget.value(),
            target_source=target_source,
            format_name=format_name,
            top_n=self.spin_topn.value(),
            paste_targets=paste_targets,
            screens=screens,
            vgcpaste_threats=vgcpaste_threats,
            is_static_mode=(self.cb_mode.currentIndex() == 1)
        )
        self.worker.progress.connect(self._update_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _update_progress(self, pct: int, msg: str):
        if hasattr(self.parent_main, "_loading_overlay"):
            self.parent_main._loading_overlay._message = f"{msg} ({pct}%)"

    # =========================================================================
    # _on_finished  --  Preview sprites + expandable detail cards
    # =========================================================================
    def _on_finished(self, results):
        self.parent_main.hide_loading()
        self.btn_start.setEnabled(True)
        self.btn_parse.setEnabled(True)

        for p_idx, spread, report, status_msg in results:
            member = self.parsed_members[p_idx]
            nature_name = spread.get('nature', 'Serious').capitalize()

            # -- Main Container --
            frame = QFrame()
            frame.setStyleSheet(f"""
                QFrame {{
                    background: {Palette.BG_SURFACE};
                    border: 1px solid {Palette.BORDER_LIGHT};
                    border-radius: 10px;
                    padding: 16px;
                }}
            """)
            v_main = QVBoxLayout(frame)
            v_main.setSpacing(12)

            # == A. HEADER ==
            header_frame = QFrame()
            header_frame.setStyleSheet(f"""
                QFrame {{
                    background: {Palette.BG_SURFACE_ELEVATED};
                    border: 1px solid {Palette.BORDER_LIGHT};
                    border-radius: 8px;
                    padding: 14px;
                }}
            """)
            h_header = QHBoxLayout(header_frame)
            h_header.setSpacing(16)

            icon_lbl = QLabel()
            pix = get_pokemon_pixmap(member.species, 56)
            if pix:
                icon_lbl.setPixmap(pix)
            icon_lbl.setFixedSize(60, 60)
            h_header.addWidget(icon_lbl)

            v_info = QVBoxLayout()
            v_info.setSpacing(4)

            lbl_species = QLabel(member.species)
            lbl_species.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 18px; font-weight: bold; font-family: {Fonts.FAMILY_UI};")
            v_info.addWidget(lbl_species)

            item_text = member.item if member.item else "Nessuno"
            nature_text = member.nature if member.nature else "Serious"
            ability_text = member.ability if member.ability else "Sconosciuta"
            lbl_details = QLabel(f"Strumento: {item_text}  |  Natura: {nature_text}  |  Abilita: {ability_text}")
            lbl_details.setStyleSheet(f"color: {Palette.TEXT_PRIMARY}; font-size: 13px; font-family: {Fonts.FAMILY_UI};")
            v_info.addWidget(lbl_details)

            evs_raw = member.evs if member.evs else {}
            evs_parts = [f"{v} {k}" for k, v in evs_raw.items() if v and v > 0]
            ev_str = " / ".join(evs_parts) if evs_parts else "Nessun EV"
            lbl_evs = QLabel(f"Build: {ev_str}")
            lbl_evs.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px; font-family: {Fonts.FAMILY_DATA};")
            v_info.addWidget(lbl_evs)

            moves = member.moves if member.moves else []
            moves_str = "  |  ".join(mv for mv in moves if mv) if moves else "Nessuna mossa"
            lbl_moves = QLabel(f"Moveset: {moves_str}")
            lbl_moves.setStyleSheet(f"color: {Palette.SECONDARY}; font-size: 12px; font-family: {Fonts.FAMILY_UI};")
            v_info.addWidget(lbl_moves)

            h_header.addLayout(v_info)
            h_header.addStretch()

            # Optimal Spread
            v_spread = QVBoxLayout()
            v_spread.setSpacing(2)
            lbl_st = QLabel("Spread Ottimale")
            lbl_st.setAlignment(Qt.AlignRight)
            lbl_st.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px;")
            v_spread.addWidget(lbl_st)
            lbl_sv = QLabel(f"{spread.get('atk', 0)} Atk / {spread.get('spa', 0)} SpA")
            lbl_sv.setAlignment(Qt.AlignRight)
            lbl_sv.setStyleSheet(f"color: {Palette.PRIMARY_BRIGHT}; font-size: 16px; font-weight: bold; font-family: {Fonts.FAMILY_DATA};")
            v_spread.addWidget(lbl_sv)
            lbl_ss = QLabel(f"L.50: Atk {spread.get('final_atk', '?')} | SpA {spread.get('final_spa', '?')}  (Usati: {spread.get('total', 0)} EV)")
            lbl_ss.setAlignment(Qt.AlignRight)
            lbl_ss.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px; font-family: {Fonts.FAMILY_DATA};")
            v_spread.addWidget(lbl_ss)
            h_header.addLayout(v_spread)
            v_main.addWidget(header_frame)

            lbl_status = QLabel(status_msg)
            lbl_status.setStyleSheet(f"color: {Palette.TERTIARY_LIGHT}; font-style: italic; font-size: 12px;")
            v_main.addWidget(lbl_status)

            # == B. KPI DASHBOARD ==
            ohko_list = report.get("1HKO", [])
            twohko_list = report.get("2HKO", [])
            threehko_list = report.get("3HKO+", [])
            total_targets = len(ohko_list) + len(twohko_list) + len(threehko_list)

            kpi_layout = QHBoxLayout()
            kpi_layout.setSpacing(10)

            def make_kpi_card(value, label, color, border_c):
                card = QFrame()
                card.setFixedHeight(80)
                card.setStyleSheet(f"""
                    QFrame {{ background: {Palette.BG_SURFACE_ELEVATED}; border: 1px solid {border_c}; border-radius: 8px; padding: 8px; }}
                """)
                cl = QVBoxLayout(card)
                cl.setContentsMargins(12, 8, 12, 8)
                cl.setSpacing(2)
                lv = QLabel(str(value))
                lv.setAlignment(Qt.AlignCenter)
                lv.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold; font-family: {Fonts.FAMILY_DATA}; border: none;")
                cl.addWidget(lv)
                ln = QLabel(label)
                ln.setAlignment(Qt.AlignCenter)
                ln.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; font-family: {Fonts.FAMILY_UI}; border: none;")
                cl.addWidget(ln)
                return card

            kpi_layout.addWidget(make_kpi_card(total_targets, "Totale Analizzati", Palette.TEXT_PRIMARY, Palette.BORDER_LIGHT))
            kpi_layout.addWidget(make_kpi_card(len(ohko_list), "1HKO", Palette.SUCCESS, Palette.SUCCESS))
            kpi_layout.addWidget(make_kpi_card(len(twohko_list), "2HKO", Palette.PRIMARY, Palette.PRIMARY_DIM))
            kpi_layout.addWidget(make_kpi_card(len(threehko_list), "3+ HKO", Palette.DANGER, Palette.DANGER))
            v_main.addLayout(kpi_layout)

            # == C/D/E. KO TIER SECTIONS with preview + detail cards ==

            CARD_CSS = f"""
                QFrame {{
                    background: {Palette.BG_SURFACE_ELEVATED};
                    border: 1px solid {Palette.BORDER_LIGHT};
                    border-radius: 8px;
                    padding: 10px 14px;
                    margin: 2px 0;
                }}
                QFrame:hover {{
                    border: 1px solid {Palette.TERTIARY};
                }}
            """

            def _speed_badge(r):
                a_spe = r.get("attacker_base_spe", 0)
                d_spe = r.get("defender_base_spe", 0)
                tier = r.get("speed_tier", "?")
                if tier == "Piu Veloce":
                    return f"Piu Veloce: Base {d_spe} vs {a_spe}", Palette.DANGER_BRIGHT
                elif tier == "Piu Lento":
                    return f"Piu Lento: Base {d_spe} vs {a_spe}", Palette.SUCCESS
                return f"Speed Tie: Base {d_spe} vs {a_spe}", Palette.WARNING

            def _dmg_color_2hko(max_pct):
                if max_pct >= 90:
                    return Palette.DANGER_BRIGHT
                elif max_pct >= 80:
                    return Palette.PRIMARY_BRIGHT
                elif max_pct >= 70:
                    return Palette.SECONDARY
                return Palette.TEXT_MUTED

            def _detail_row(lbl_text, val_text, val_color=Palette.TEXT_PRIMARY, bold=False, font=None):
                row = QHBoxLayout()
                row.setSpacing(6)
                row.setContentsMargins(0, 1, 0, 1)
                l = QLabel(f"{lbl_text}:")
                l.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 11px; font-family: {Fonts.FAMILY_UI}; border: none;")
                l.setFixedWidth(85)
                row.addWidget(l)
                ff = font if font else Fonts.FAMILY_UI
                w = "bold" if bold else "normal"
                v = QLabel(str(val_text))
                v.setStyleSheet(f"color: {val_color}; font-size: 12px; font-weight: {w}; font-family: {ff}; border: none;")
                row.addWidget(v)
                row.addStretch()
                return row

            def build_ko_section(ko_list, title, cat_key=""):
                section = QWidget()
                sl = QVBoxLayout(section)
                sl.setContentsMargins(0, 0, 0, 0)
                sl.setSpacing(8)

                lt = QLabel(f"{title}  ({len(ko_list)})")
                lt.setStyleSheet(f"color: {Palette.SECONDARY}; font-size: 14px; font-weight: bold; font-family: {Fonts.FAMILY_UI}; padding: 8px 0 4px 0;")
                sl.addWidget(lt)

                if not ko_list:
                    le = QLabel("Nessun risultato in questa categoria.")
                    le.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-style: italic; font-size: 12px; padding: 4px 8px;")
                    sl.addWidget(le)
                    return section

                grouped = {}
                for res in ko_list:
                    grouped.setdefault(res["defender"], []).append(res)

                # Sprite preview grid
                pf = QFrame()
                pf.setStyleSheet(f"QFrame {{ background: {Palette.BG_SURFACE_ELEVATED}; border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 8px; padding: 8px; }}")
                pg = QGridLayout(pf)
                pg.setSpacing(6)
                col_idx = 0
                row_idx = 0
                for sp in grouped.keys():
                    slbl = QLabel()
                    px = get_pokemon_pixmap(sp, 40)
                    if px:
                        slbl.setPixmap(px)
                    slbl.setFixedSize(44, 44)
                    slbl.setToolTip(sp)
                    slbl.setStyleSheet(f"background: {Palette.BG_CARD}; border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 6px; padding: 2px;")
                    pg.addWidget(slbl, row_idx, col_idx)
                    col_idx += 1
                    if col_idx >= 8:
                        col_idx = 0
                        row_idx += 1
                sl.addWidget(pf)

                # Toggle button and details container
                toggle_btn = QPushButton("Mostra dettagli build ▼")
                toggle_btn.setCursor(Qt.PointingHandCursor)
                toggle_btn.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {Palette.PRIMARY}; border: none; font-weight: bold; text-align: left; padding: 4px; font-family: {Fonts.FAMILY_UI}; }}
                    QPushButton:hover {{ color: {Palette.PRIMARY_BRIGHT}; }}
                """)
                sl.addWidget(toggle_btn)

                details_container = QWidget()
                dl = QVBoxLayout(details_container)
                dl.setContentsMargins(0, 0, 0, 0)
                dl.setSpacing(4)
                details_container.setVisible(False)
                sl.addWidget(details_container)

                def _toggle_ko(checked=False, c=details_container, btn=toggle_btn):
                    if c.isVisible():
                        c.setVisible(False)
                        btn.setText("Mostra dettagli build ▼")
                    else:
                        c.setVisible(True)
                        btn.setText("Nascondi dettagli build ▲")
                toggle_btn.clicked.connect(_toggle_ko)

                # Detail cards per species
                for species, builds in grouped.items():
                    first = builds[0]
                    spd_text, spd_color = _speed_badge(first)

                    card = QFrame()
                    card.setStyleSheet(CARD_CSS)
                    clayout = QVBoxLayout(card)
                    clayout.setSpacing(4)
                    clayout.setContentsMargins(10, 8, 10, 8)

                    hsp = QHBoxLayout()
                    hsp.setSpacing(8)
                    px = get_pokemon_pixmap(species, 32)
                    if px:
                        ic = QLabel()
                        ic.setPixmap(px)
                        ic.setFixedSize(32, 32)
                        ic.setStyleSheet("border: none;")
                        hsp.addWidget(ic)
                    nl = QLabel(species)
                    nl.setStyleSheet(f"color: {Palette.PRIMARY_BRIGHT}; font-size: 14px; font-weight: bold; font-family: {Fonts.FAMILY_UI}; border: none;")
                    hsp.addWidget(nl)
                    sbl = QLabel(f"[{spd_text}]")
                    sbl.setStyleSheet(f"color: {spd_color}; font-size: 10px; font-weight: bold; border: none;")
                    hsp.addWidget(sbl)
                    hsp.addStretch()
                    clayout.addLayout(hsp)

                    for bi, b in enumerate(builds):
                        if bi > 0:
                            sep = QFrame()
                            sep.setFrameShape(QFrame.HLine)
                            sep.setStyleSheet(f"background: {Palette.BORDER_LIGHT}; max-height: 1px; border: none;")
                            clayout.addWidget(sep)

                        clayout.addLayout(_detail_row("Strumento", b.get('defender_item', 'Nessuno')))
                        clayout.addLayout(_detail_row("Natura", b.get('defender_nature', 'Serious')))
                        clayout.addLayout(_detail_row("Build", f"EVs: {b.get('defender_evs', '0 / 0 / 0')}", Palette.TEXT_MUTED, font=Fonts.FAMILY_DATA))
                        clayout.addLayout(_detail_row("Mossa", b.get('move', '?'), Palette.SECONDARY, bold=True))

                        dc = _dmg_color_2hko(b['damage_pct']) if cat_key == "2HKO" else Palette.TEXT_PRIMARY
                        clayout.addLayout(_detail_row("Danno Min", f"{b['min_pct']:.1f}%", dc, bold=True, font=Fonts.FAMILY_DATA))
                        clayout.addLayout(_detail_row("Danno Max", f"{b['damage_pct']:.1f}%", dc, bold=True, font=Fonts.FAMILY_DATA))

                    dl.addWidget(card)
                return section

            v_main.addWidget(build_ko_section(ohko_list, "1HKO - Pokemon uccisi in un colpo", "1HKO"))
            v_main.addWidget(build_ko_section(twohko_list, "2HKO - Pokemon uccisi in due colpi", "2HKO"))
            v_main.addWidget(build_ko_section(threehko_list, "3+ HKO - Pokemon uccisi in 3 o piu colpi", "3HKO+"))

            # == F. SENSITIVITY ==
            sens = report.get("Sensitivity", {})
            sh = QLabel("Analisi Sensibilita (Variazione EV Attaccante)")
            sh.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 15px; font-weight: bold; font-family: {Fonts.FAMILY_UI}; padding: 10px 0 4px 0;")
            v_main.addWidget(sh)

            def build_sens_section(sens_list, title, is_gain=False):
                section = QWidget()
                sl = QVBoxLayout(section)
                sl.setContentsMargins(0, 0, 0, 0)
                sl.setSpacing(4)

                valid_list = []
                for r in sens_list:
                    has_v = any((is_gain and k.startswith('+')) or (not is_gain and k.startswith('-')) for k in r['sensitivity'].keys())
                    if has_v:
                        valid_list.append(r)

                lt = QLabel(f"{title}  ({len(valid_list)})")
                lt.setStyleSheet(f"color: {Palette.SECONDARY}; font-size: 13px; font-weight: bold; font-family: {Fonts.FAMILY_UI}; padding: 6px 0 2px 0;")
                sl.addWidget(lt)

                if not valid_list:
                    lab = "guadagno" if is_gain else "peggioramento"
                    le = QLabel(f"Nessun {lab} trovato.")
                    le.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-style: italic; font-size: 12px; padding: 4px 8px;")
                    sl.addWidget(le)
                    return section

                grouped = {}
                for r in valid_list:
                    grouped.setdefault(r["defender"], []).append(r)

                # Sprite preview grid
                pf = QFrame()
                pf.setStyleSheet(f"QFrame {{ background: {Palette.BG_SURFACE_ELEVATED}; border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 8px; padding: 8px; }}")
                pg = QGridLayout(pf)
                pg.setSpacing(6)
                col_idx = 0
                row_idx = 0
                for sp in grouped.keys():
                    slbl = QLabel()
                    px = get_pokemon_pixmap(sp, 40)
                    if px:
                        slbl.setPixmap(px)
                    slbl.setFixedSize(44, 44)
                    slbl.setToolTip(sp)
                    slbl.setStyleSheet(f"background: {Palette.BG_CARD}; border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 6px; padding: 2px;")
                    pg.addWidget(slbl, row_idx, col_idx)
                    col_idx += 1
                    if col_idx >= 8:
                        col_idx = 0
                        row_idx += 1
                sl.addWidget(pf)

                # Toggle button and details container
                toggle_btn = QPushButton("Mostra dettagli build ▼")
                toggle_btn.setCursor(Qt.PointingHandCursor)
                toggle_btn.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {Palette.PRIMARY}; border: none; font-weight: bold; text-align: left; padding: 4px; font-family: {Fonts.FAMILY_UI}; }}
                    QPushButton:hover {{ color: {Palette.PRIMARY_BRIGHT}; }}
                """)
                sl.addWidget(toggle_btn)

                details_container = QWidget()
                dl = QVBoxLayout(details_container)
                dl.setContentsMargins(0, 0, 0, 0)
                dl.setSpacing(4)
                details_container.setVisible(False)
                sl.addWidget(details_container)

                def _toggle_sens(checked=False, c=details_container, btn=toggle_btn):
                    if c.isVisible():
                        c.setVisible(False)
                        btn.setText("Mostra dettagli build ▼")
                    else:
                        c.setVisible(True)
                        btn.setText("Nascondi dettagli build ▲")
                toggle_btn.clicked.connect(_toggle_sens)

                for species, builds in grouped.items():
                    card = QFrame()
                    card.setStyleSheet(CARD_CSS)
                    clayout = QVBoxLayout(card)
                    clayout.setSpacing(4)
                    clayout.setContentsMargins(10, 8, 10, 8)

                    hsp = QHBoxLayout()
                    hsp.setSpacing(8)
                    px = get_pokemon_pixmap(species, 28)
                    if px:
                        ic = QLabel()
                        ic.setPixmap(px)
                        ic.setFixedSize(28, 28)
                        ic.setStyleSheet("border: none;")
                        hsp.addWidget(ic)
                    nl = QLabel(species)
                    nl.setStyleSheet(f"color: {Palette.PRIMARY_BRIGHT}; font-size: 13px; font-weight: bold; border: none;")
                    hsp.addWidget(nl)
                    hsp.addStretch()
                    clayout.addLayout(hsp)

                    ei = 0
                    for b in builds:
                        for drop, new_tier in b['sensitivity'].items():
                            if (is_gain and drop.startswith('+')) or (not is_gain and drop.startswith('-')):
                                if ei > 0:
                                    sep = QFrame()
                                    sep.setFrameShape(QFrame.HLine)
                                    sep.setStyleSheet(f"background: {Palette.BORDER_LIGHT}; max-height: 1px; border: none;")
                                    clayout.addWidget(sep)
                                clayout.addLayout(_detail_row("Delta EV", drop, Palette.PRIMARY_BRIGHT, bold=True, font=Fonts.FAMILY_DATA))
                                clayout.addLayout(_detail_row("Strumento", b.get('defender_item', 'Nessuno')))
                                clayout.addLayout(_detail_row("Natura", b.get('defender_nature', 'Serious')))
                                clayout.addLayout(_detail_row("Build", f"EVs: {b.get('defender_evs', '0 / 0 / 0')}", Palette.TEXT_MUTED, font=Fonts.FAMILY_DATA))
                                clayout.addLayout(_detail_row("Mossa", b.get('move', '?'), Palette.SECONDARY, bold=True))
                                ei += 1

                    dl.addWidget(card)
                return section

            v_main.addWidget(build_sens_section(sens.get("Loss_1HKO", []), "Perdita del 1HKO", is_gain=False))
            v_main.addWidget(build_sens_section(sens.get("Loss_2HKO", []), "Perdita del 2HKO", is_gain=False))
            v_main.addWidget(build_sens_section(sens.get("Gain_1HKO", []), "Guadagno 1HKO", is_gain=True))
            v_main.addWidget(build_sens_section(sens.get("Gain_2HKO", []), "Guadagno 2HKO", is_gain=True))

            self.results_layout.addWidget(frame)

        self.latest_results = results
        if results:
            self.btn_export_pdf.show()

    # =========================================================================
    # _export_pdf
    # =========================================================================
    def _export_pdf(self):
        if not hasattr(self, 'latest_results') or not self.latest_results:
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Salva Report PDF", "Report_Offense.pdf", "PDF Files (*.pdf)")
        if not file_path:
            return

        from datetime import datetime
        current_date = datetime.now().strftime("%d/%m/%Y")

        def _dmg_color_css(max_pct, is_2hko=False):
            if not is_2hko:
                return "color: #DEDAD4;"
            if max_pct >= 90:
                return "color: #B04545; font-weight: bold;"
            elif max_pct >= 80:
                return "color: #D4AA52; font-weight: bold;"
            elif max_pct >= 70:
                return "color: #8577A8;"
            return "color: #5E6575;"

        def _speed_badge_html(r):
            a_spe = r.get("attacker_base_spe", 0)
            d_spe = r.get("defender_base_spe", 0)
            tier = r.get("speed_tier", "?")
            if tier == "Piu Veloce":
                return f"<span style='color:#B04545; font-size:8pt; font-weight:bold;'>[Piu Veloce: Base {d_spe} vs {a_spe}]</span>"
            elif tier == "Piu Lento":
                return f"<span style='color:#3D6B50; font-size:8pt; font-weight:bold;'>[Piu Lento: Base {d_spe} vs {a_spe}]</span>"
            return f"<span style='color:#8A6830; font-size:8pt; font-weight:bold;'>[Speed Tie: Base {d_spe} vs {a_spe}]</span>"

        html = f"""
        <html><head>
        <style>
            @page {{ margin: 18mm 15mm 15mm 15mm; }}
            body {{ font-family: 'Segoe UI', 'Inter', Arial, sans-serif; color: #DEDAD4; background-color: #0A0B0D; font-size: 10pt; line-height: 1.3; }}
            .cover {{ text-align: center; padding-top: 120pt; page-break-after: always; }}
            .cover h1 {{ font-size: 28pt; color: #C49A3C; border-bottom: 3pt solid #C49A3C; padding-bottom: 12pt; margin-bottom: 20pt; }}
            .cover h3 {{ font-size: 13pt; color: #8577A8; margin-top: 16pt; font-weight: normal; }}
            h2 {{ color: #C49A3C; font-size: 14pt; border-bottom: 2pt solid #7A6025; padding-bottom: 5pt; margin-top: 20pt; margin-bottom: 10pt; }}
            h3 {{ color: #8577A8; font-size: 12pt; margin-top: 14pt; margin-bottom: 6pt; }}
            .team-grid {{ width: 100%; border-collapse: collapse; margin-top: 10pt; margin-bottom: 12pt; }}
            .team-grid td {{ width: 50%; vertical-align: top; padding: 10pt; border: 1pt solid #252932; background-color: #131519; font-size: 9pt; }}
            .team-name {{ font-size: 12pt; font-weight: bold; color: #C49A3C; margin-bottom: 6pt; }}
            .team-detail {{ color: #DEDAD4; margin-bottom: 3pt; }}
            .team-moves {{ color: #8577A8; font-size: 9pt; }}
            .kpi-row {{ width: 100%; border-collapse: collapse; margin: 12pt 0; }}
            .kpi-cell {{ width: 25%; text-align: center; padding: 10pt 6pt; border: 1pt solid #252932; background-color: #131519; }}
            .kpi-value {{ font-size: 20pt; font-weight: bold; font-family: 'Cascadia Code', 'Consolas', monospace; }}
            .kpi-label {{ font-size: 8pt; color: #5E6575; margin-top: 3pt; }}
            .ko-table {{ width: 100%; border-collapse: collapse; margin-bottom: 10pt; }}
            .ko-table th {{ background-color: #1C1F26; color: #C49A3C; padding: 7pt 8pt; text-align: left; font-size: 9pt; border-bottom: 2pt solid #7A6025; }}
            .ko-table td {{ padding: 6pt 8pt; border-bottom: 1pt solid #252932; font-size: 9pt; vertical-align: top; }}
            .ko-table tr:nth-child(even) {{ background-color: #0E0F12; }}
            .ko-table tr:nth-child(odd) {{ background-color: #131519; }}
            .species-name {{ font-weight: bold; color: #D4AA52; font-size: 10pt; }}
            .move-name {{ color: #8577A8; font-weight: 600; }}
            .dmg-range {{ font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 9pt; }}
            .page-break {{ page-break-after: always; }}
            .status-msg {{ color: #8A9DB0; font-style: italic; font-size: 9pt; margin-bottom: 8pt; }}
            .section-empty {{ color: #5E6575; font-style: italic; padding: 6pt 8pt; font-size: 9pt; }}
        </style>
        </head><body>
        <div class="cover">
            <h1>OFFENSE OPTIMIZATION<br>REPORT</h1>
            <h3>Formato: VGC Doubles</h3>
            <h3>Preparato da: JAnalytics</h3>
            <h3>Data: {current_date}</h3>
        </div>
        """

        html += "<h2>Team Analizzato</h2>"
        html += "<table class='team-grid'>"
        for i in range(0, len(self.parsed_members), 2):
            html += "<tr>"
            for j in range(2):
                if i + j < len(self.parsed_members):
                    m = self.parsed_members[i + j]
                    item_t = m.item if m.item else "Nessuno"
                    nature_t = m.nature if m.nature else "Serious"
                    ability_t = m.ability if m.ability else "Sconosciuta"
                    evs_raw = m.evs if m.evs else {}
                    evs_parts = [f"{v} {k}" for k, v in evs_raw.items() if v and v > 0]
                    ev_s = " / ".join(evs_parts) if evs_parts else "Nessun EV"
                    mvs = m.moves if m.moves else []
                    mvs_s = " | ".join(mv for mv in mvs if mv) if mvs else "-"
                    p_path = get_pokemon_icon_path(m.species)
                    img_t = f"<img src='file:///{p_path.replace(chr(92), '/')}' width='28' height='28' style='vertical-align: middle;'> " if p_path and os.path.exists(p_path) else ""
                    html += f"""
                    <td>
                        <div class='team-name'>{img_t}{m.species}</div>
                        <div class='team-detail'><b>Strumento:</b> {item_t} &nbsp;|&nbsp; <b>Natura:</b> {nature_t}</div>
                        <div class='team-detail'><b>Abilita:</b> {ability_t} &nbsp;|&nbsp; <b>Build:</b> {ev_s}</div>
                        <div class='team-moves'><b>Moveset:</b> {mvs_s}</div>
                    </td>
                    """
                else:
                    html += "<td></td>"
            html += "</tr>"
        html += "</table>"

        for result_idx, (p_idx, spread, report, status_msg) in enumerate(self.latest_results):
            member = self.parsed_members[p_idx]
            nature_name = spread.get('nature', 'Serious').capitalize()
            ohko_list = report.get("1HKO", [])
            twohko_list = report.get("2HKO", [])
            threehko_list = report.get("3HKO+", [])
            total_targets = len(ohko_list) + len(twohko_list) + len(threehko_list)

            if result_idx > 0:
                html += "<div class='page-break'></div>"

            p_path = get_pokemon_icon_path(member.species)
            img_tag = f"<img src='file:///{p_path.replace(chr(92), '/')}' width='36' height='36' style='vertical-align: middle;'> " if p_path and os.path.exists(p_path) else ""
            item_t = member.item if member.item else "Nessuno"

            html += f"""
            <h2>{img_tag}{member.species}</h2>
            <table style='width:100%; border-collapse:collapse; margin-bottom:8pt;'>
                <tr><td style='padding:4pt 0; font-size:10pt; color:#DEDAD4;'>
                    <b>Strumento:</b> {item_t} &nbsp;|&nbsp;
                    <b>Natura:</b> {nature_name} &nbsp;|&nbsp;
                    <b>Spread Ottimale:</b> <span style='color:#D4AA52; font-weight:bold;'>{spread.get('atk',0)} Atk / {spread.get('spa',0)} SpA</span>
                    &nbsp;|&nbsp; <b>L.50:</b> Atk {spread.get('final_atk','?')} / SpA {spread.get('final_spa','?')}
                </td></tr>
            </table>
            <p class='status-msg'>{status_msg}</p>
            """

            html += f"""
            <table class='kpi-row'>
                <tr>
                    <td class='kpi-cell'><div class='kpi-value' style='color:#DEDAD4;'>{total_targets}</div><div class='kpi-label'>Totale</div></td>
                    <td class='kpi-cell'><div class='kpi-value' style='color:#3D6B50;'>{len(ohko_list)}</div><div class='kpi-label'>1HKO</div></td>
                    <td class='kpi-cell'><div class='kpi-value' style='color:#C49A3C;'>{len(twohko_list)}</div><div class='kpi-label'>2HKO</div></td>
                    <td class='kpi-cell'><div class='kpi-value' style='color:#8A3838;'>{len(threehko_list)}</div><div class='kpi-label'>3+ HKO</div></td>
                </tr>
            </table>
            """

            def render_ko_table(report_list, title, is_2hko=False):
                res = f"<h3>{title}  ({len(report_list)})</h3>"
                if not report_list:
                    return res + "<p class='section-empty'>Nessun risultato.</p>"
                res += """<table class='ko-table'>
                    <tr><th style='width:25%;'>Target</th><th style='width:30%;'>Build</th><th style='width:22%;'>Mossa</th><th style='width:23%;'>Danno</th></tr>"""
                grouped = {}
                for r in report_list:
                    grouped.setdefault(r["defender"], []).append(r)
                for species, builds in grouped.items():
                    first = builds[0]
                    badge = _speed_badge_html(first)
                    for bi, b in enumerate(builds):
                        sc = f"<span class='species-name'>{species}</span><br>{badge}" if bi == 0 else ""
                        bt = f"{b['defender_item']}<br>{b['defender_nature']} | EVs: {b['defender_evs']}"
                        mt = f"<span class='move-name'>{b['move']}</span>"
                        ds = _dmg_color_css(b['damage_pct'], is_2hko)
                        dt = f"<span class='dmg-range' style='{ds}'>{b['min_pct']:.1f}% - {b['damage_pct']:.1f}%</span>"
                        res += f"<tr><td>{sc}</td><td>{bt}</td><td>{mt}</td><td>{dt}</td></tr>"
                res += "</table>"
                return res

            html += render_ko_table(ohko_list, "1HKO - Pokemon uccisi in un colpo", False)
            html += render_ko_table(twohko_list, "2HKO - Pokemon uccisi in due colpi", True)
            html += render_ko_table(threehko_list, "3+ HKO - Pokemon uccisi in 3 o piu colpi", False)

            sens = report.get("Sensitivity", {})

            def render_sens_table(sens_list, title, is_gain):
                valid_list = []
                for r in sens_list:
                    if any((is_gain and k.startswith('+')) or (not is_gain and k.startswith('-')) for k in r['sensitivity'].keys()):
                        valid_list.append(r)
                res = f"<h3>{title}</h3>"
                if not valid_list:
                    lab = "guadagno" if is_gain else "peggioramento"
                    return res + f"<p class='section-empty'>Nessun {lab} trovato.</p>"
                res += """<table class='ko-table'>
                    <tr><th style='width:25%;'>Target</th><th style='width:30%;'>Build</th><th style='width:22%;'>Mossa</th><th style='width:23%;'>Delta EV</th></tr>"""
                grouped = {}
                for r in valid_list:
                    grouped.setdefault(r["defender"], []).append(r)
                for species, builds in grouped.items():
                    first_sp = True
                    for b in builds:
                        for drop, nt in b['sensitivity'].items():
                            if (is_gain and drop.startswith('+')) or (not is_gain and drop.startswith('-')):
                                sc = f"<span class='species-name'>{species}</span>" if first_sp else ""
                                first_sp = False
                                bt = f"{b['defender_item']}<br>{b['defender_nature']} | EVs: {b['defender_evs']}"
                                mt = f"<span class='move-name'>{b['move']}</span>"
                                dlt = f"<span style='color:#D4AA52; font-weight:bold;'>{drop} EV</span>"
                                res += f"<tr><td>{sc}</td><td>{bt}</td><td>{mt}</td><td>{dlt}</td></tr>"
                res += "</table>"
                return res

            html += render_sens_table(sens.get("Loss_1HKO", []), "Perdita del 1HKO", False)
            html += render_sens_table(sens.get("Loss_2HKO", []), "Perdita del 2HKO", False)
            html += render_sens_table(sens.get("Gain_1HKO", []), "Guadagno 1HKO", True)
            html += render_sens_table(sens.get("Gain_2HKO", []), "Guadagno 2HKO", True)

        html += "</body></html>"

        try:
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(file_path)
            doc = QTextDocument()
            doc.setHtml(html)
            doc.print_(printer)
            QMessageBox.information(self, "Completato", f"Report esportato con successo in:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile esportare il PDF:\n{str(e)}")

    def _on_error(self, error_msg: str):
        self.parent_main.hide_loading()
        self.btn_start.setEnabled(True)
        self.btn_parse.setEnabled(True)
        QMessageBox.critical(self, "Errore Ottimizzazione", f"Si e verificato un errore durante l'ottimizzazione:\n{error_msg}")

    # ── VGCPastes Integration ────────────────────────────────────────────────

    def _get_vgcpaste_imported_teams(self):
        """Recupera i team importati dalla sezione VGCPastes via parent_main."""
        if hasattr(self.parent_main, "gsheet_import_view"):
            return self.parent_main.gsheet_import_view.get_imported_teams()
        return []

    def _update_vgcpaste_count(self):
        """Aggiorna la label info con il conteggio dei team/pokemon importati."""
        imported = self._get_vgcpaste_imported_teams()
        if imported:
            total_pokemon = sum(len(t.members) for t in imported)
            self.lbl_vgcpaste_count.setText(
                f"✓ {len(imported)} team importati ({total_pokemon} Pokémon disponibili come bersagli)."
            )
            self.lbl_vgcpaste_count.setStyleSheet(f"color: {Palette.SUCCESS}; font-size: 12px;")
        else:
            self.lbl_vgcpaste_count.setText(
                "Nessun team importato. Importa prima dalla sezione VGCPastes."
            )
            self.lbl_vgcpaste_count.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px;")
