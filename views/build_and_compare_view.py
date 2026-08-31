import os
from typing import List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QSplitter, QGraphicsDropShadowEffect, QMessageBox, QListWidget,
    QListWidgetItem, QFrame, QScrollArea, QApplication, QDialog,
    QComboBox, QCompleter, QStackedWidget, QSpinBox, QFormLayout
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPixmap, QFont
from config.theme import Palette

from src.domain.team_builder_service import (
    parse_pokepaste, TeamMember,
    get_all_species_names, get_species_types, get_historical_abilities,
    get_historical_moves, get_all_abilities, get_all_moves, get_all_items
)
from src.domain.type_chart import TYPE_DATA, get_multiplier
from views.pokemon_edit_view import PokemonEditPage
from src.domain.type_chart import TYPE_DATA, get_multiplier
from views.pokemon_edit_view import PokemonEditPage
from views.batch_damage_dialogs import BatchDamageConfigDialog, BatchDamageResultDialog
from src.domain.batch_generator_service import BatchGeneratorService
from domain.smogon_calc import SmogonDamageCalc
from domain.batch_analyzer import BatchDamageAnalyzer

TYPE_COLORS = {
    "Normal": "#A8A77A", "Fire": "#EE8130", "Water": "#6390F0",
    "Electric": "#F7D02C", "Grass": "#7AC74C", "Ice": "#96D9D6",
    "Fighting": "#C22E28", "Poison": "#A33EA1", "Ground": "#E2BF65",
    "Flying": "#A98FF3", "Psychic": "#F95587", "Bug": "#A6B91A",
    "Rock": "#B6A136", "Ghost": "#735797", "Dragon": "#6F35FC",
    "Dark": "#705746", "Steel": "#B7B7CE", "Fairy": "#D685AD"
}

from src.utils.icon_utils import get_pokemon_icon_path

def get_pokemon_pixmap(species: str, size: int = 32) -> QPixmap:
    if not species: return None
    path = get_pokemon_icon_path(species)
    if path and os.path.exists(path):
        return QPixmap(path).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return None

class TypeBadge(QLabel):
    def __init__(self, type_name: str):
        super().__init__(type_name)
        color = TYPE_COLORS.get(type_name.capitalize(), "#888888")
        self.setStyleSheet(f"""
            background-color: {color};
            color: #FFFFFF;
            border-radius: 4px;
            padding: 2px 6px;
            font-weight: bold;
            font-size: 11px;
        """)
        self.setAlignment(Qt.AlignCenter)

class PokemonSelectionDialog(QDialog):
    def __init__(self, raw_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pokémon non riconosciuto")
        self.setFixedSize(400, 150)
        self.setStyleSheet(f"background-color: {Palette.BG_SURFACE_ELEVATED}; color: {Palette.TEXT_PRIMARY};")
        
        layout = QVBoxLayout(self)
        
        lbl = QLabel(f"Impossibile riconoscere il Pokémon:\n'{raw_name}'\nSelezionalo manualmente dal database:")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 13px;")
        layout.addWidget(lbl)
        
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setStyleSheet(f"background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY}; padding: 4px;")
        
        all_species = get_all_species_names()
        self.combo.addItems(all_species)
        
        completer = QCompleter(all_species)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.combo.setCompleter(completer)
        
        layout.addWidget(self.combo)
        
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Conferma")
        btn_cancel = QPushButton("Annulla")
        
        btn_style = f"background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY}; padding: 5px 15px; border-radius: 4px;"
        btn_ok.setStyleSheet(btn_style)
        btn_cancel.setStyleSheet(btn_style)
        
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)
        
    def get_selected_pokemon(self):
        return self.combo.currentText()

class BuildAndCompareWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.teams: List[Dict[str, Any]] = []
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.stacked = QStackedWidget()
        main_layout.addWidget(self.stacked)
        
        self.page_explorer = QWidget()
        self._setup_explorer_page(self.page_explorer)
        
        self.page_analysis = QWidget()
        self._setup_analysis_page(self.page_analysis)
        
        self.page_edit = PokemonEditPage(self)
        self.page_edit.go_back.connect(lambda: self.stacked.setCurrentWidget(self.page_explorer))
        self.page_edit.pokemon_updated.connect(self._on_pokemon_updated)
        
        self.stacked.addWidget(self.page_explorer)
        self.stacked.addWidget(self.page_analysis)
        self.stacked.addWidget(self.page_edit)
        
    def _setup_explorer_page(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #333; width: 2px; }")
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 20, 10, 20)
        
        lbl_paste = QLabel("Inserisci PokéPaste:")
        lbl_paste.setStyleSheet(f"color: {Palette.PRIMARY}; font-weight: bold;")
        left_layout.addWidget(lbl_paste)
        
        self.txt_paste = QTextEdit()
        self.txt_paste.setPlaceholderText("Incolla qui il tuo team in formato Showdown...")
        self.txt_paste.setStyleSheet(
            f"background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY};"
            f"border: 1px solid {Palette.BORDER_COLOR}; border-radius: 8px; padding: 8px;"
        )
        self.txt_paste.setMaximumHeight(200)
        left_layout.addWidget(self.txt_paste)
        
        self.btn_add = QPushButton("Carica Team")
        self.btn_add.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.TERTIARY}; color: {Palette.TEXT_PRIMARY}; border: none; padding: 10px; border-radius: 6px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {Palette.SECONDARY}; color: {Palette.BG_APP}; }}"
        )
        self.btn_add.clicked.connect(self.on_add_team)
        left_layout.addWidget(self.btn_add)
        left_layout.addStretch()
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 20, 20, 20)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        
        self.explorer_content = QWidget()
        self.explorer_layout = QVBoxLayout(self.explorer_content)
        self.explorer_layout.addStretch()
        scroll.setWidget(self.explorer_content)
        
        right_layout.addWidget(scroll)
        
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([300, 700])
        
        layout.addWidget(splitter)
        
    def _setup_analysis_page(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(20, 20, 20, 20)
        
        header_layout = QHBoxLayout()
        self.btn_back = QPushButton("← Torna ai Team")
        self.btn_back.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY}; border: 1px solid {Palette.BORDER_COLOR}; padding: 8px 16px; border-radius: 6px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {Palette.TERTIARY}; }}"
        )
        self.btn_back.clicked.connect(lambda: self.stacked.setCurrentWidget(self.page_explorer))
        header_layout.addWidget(self.btn_back)
        
        self.lbl_analyzed_team = QLabel("Analisi Team")
        self.lbl_analyzed_team.setStyleSheet(f"color: {Palette.PRIMARY}; font-weight: bold; font-size: 16px;")
        header_layout.addWidget(self.lbl_analyzed_team)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {Palette.BORDER_COLOR}; border-radius: 8px; background: {Palette.BG_SURFACE_ELEVATED}; }}"
            f"QTabBar::tab {{ background: {Palette.BG_SURFACE}; color: {Palette.TEXT_MUTED}; padding: 8px 16px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }}"
            f"QTabBar::tab:selected {{ background: {Palette.TERTIARY}; color: {Palette.TEXT_PRIMARY}; font-weight: bold; }}"
        )
        layout.addWidget(self.tabs)
        
        # Tab 1: Matchup Difensivo
        self.tab_defensive = QWidget()
        self.layout_defensive = QVBoxLayout(self.tab_defensive)
        self.table_defensive = QTableWidget()
        self._setup_table(self.table_defensive)
        self.table_defensive.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_defensive.horizontalHeader().setDefaultSectionSize(120)
        self.layout_defensive.addWidget(self.table_defensive)
        self.tabs.addTab(self.tab_defensive, "Matchup Difensivo")
        
        # Tab 2: Matchup Offensivo
        self.tab_offensive = QWidget()
        self.layout_offensive = QVBoxLayout(self.tab_offensive)
        scroll_off = QScrollArea()
        scroll_off.setWidgetResizable(True)
        scroll_off.setStyleSheet("border: none; background: transparent;")
        scroll_content = QWidget()
        self.layout_off_scroll = QVBoxLayout(scroll_content)
        
        lbl_phys = QLabel("Matchup Fisico")
        lbl_phys.setStyleSheet(f"color: {Palette.PRIMARY}; font-weight: bold; font-size: 14px;")
        self.table_off_phys = QTableWidget()
        self._setup_table(self.table_off_phys)
        self.table_off_phys.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_off_phys.horizontalHeader().setDefaultSectionSize(80)
        
        lbl_spec = QLabel("Matchup Speciale")
        lbl_spec.setStyleSheet(f"color: {Palette.SECONDARY}; font-weight: bold; font-size: 14px;")
        self.table_off_spec = QTableWidget()
        self._setup_table(self.table_off_spec)
        self.table_off_spec.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_off_spec.horizontalHeader().setDefaultSectionSize(80)
        
        lbl_tot = QLabel("Matchup Totale")
        lbl_tot.setStyleSheet(f"color: {Palette.TERTIARY}; font-weight: bold; font-size: 14px;")
        self.table_off_tot = QTableWidget()
        self._setup_table(self.table_off_tot)
        self.table_off_tot.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_off_tot.horizontalHeader().setDefaultSectionSize(80)
        
        self.layout_off_scroll.addWidget(lbl_phys)
        self.layout_off_scroll.addWidget(self.table_off_phys)
        self.layout_off_scroll.addWidget(lbl_spec)
        self.layout_off_scroll.addWidget(self.table_off_spec)
        self.layout_off_scroll.addWidget(lbl_tot)
        self.layout_off_scroll.addWidget(self.table_off_tot)
        scroll_off.setWidget(scroll_content)
        self.layout_offensive.addWidget(scroll_off)
        self.tabs.addTab(self.tab_offensive, "Matchup Offensivo")
        
        # Tab 3: Matchup VS Altri Team
        self.tab_vs = QWidget()
        self.layout_vs = QVBoxLayout(self.tab_vs)
        
        scroll_vs = QScrollArea()
        scroll_vs.setWidgetResizable(True)
        scroll_vs.setStyleSheet("border: none; background: transparent;")
        vs_content = QWidget()
        self.layout_vs_scroll = QVBoxLayout(vs_content)
        
        lbl_vs_def = QLabel("Difesa VS Mosse Avversarie (Altri Team)")
        lbl_vs_def.setStyleSheet(f"color: {Palette.PRIMARY}; font-weight: bold; font-size: 14px;")
        self.table_vs_def = QTableWidget()
        self._setup_table(self.table_vs_def)
        self.table_vs_def.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_vs_def.horizontalHeader().setDefaultSectionSize(100)
        
        lbl_vs_off = QLabel("Attacco VS Pokémon Avversari (Altri Team)")
        lbl_vs_off.setStyleSheet(f"color: {Palette.SECONDARY}; font-weight: bold; font-size: 14px;")
        self.table_vs_off = QTableWidget()
        self._setup_table(self.table_vs_off)
        self.table_vs_off.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_vs_off.horizontalHeader().setDefaultSectionSize(120)
        
        self.layout_vs_scroll.addWidget(lbl_vs_def)
        self.layout_vs_scroll.addWidget(self.table_vs_def)
        self.layout_vs_scroll.addWidget(lbl_vs_off)
        self.layout_vs_scroll.addWidget(self.table_vs_off)
        
        scroll_vs.setWidget(vs_content)
        self.layout_vs.addWidget(scroll_vs)
        self.tabs.addTab(self.tab_vs, "Matchup VS Altri Team")

    def _setup_table(self, table: QTableWidget):
        table.setStyleSheet(
            f"QTableWidget {{ background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY}; border: 1px solid {Palette.BORDER_COLOR}; border-radius: 4px; gridline-color: {Palette.BORDER_LIGHT}; }}"
            f"QHeaderView::section {{ background-color: {Palette.BG_APP}; font-weight: bold; border: none; border-right: 1px solid {Palette.BORDER_COLOR}; border-bottom: 1px solid {Palette.BORDER_COLOR}; padding: 4px; }}"
        )
        table.verticalHeader().setDefaultSectionSize(35)
        table.horizontalHeader().setMinimumSectionSize(40)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)

    def on_add_team(self):
        paste = self.txt_paste.toPlainText()
        if not paste.strip():
            QMessageBox.warning(self, "Attenzione", "Inserisci un PokéPaste.")
            return
            
        main_win = self.window()
        if hasattr(main_win, "show_loading"):
            main_win.show_loading("Parsing del team in corso...")
        QApplication.processEvents()
        
        if not hasattr(self, 'corrections'):
            self.corrections = {}
            
        try:
            from src.domain.exceptions import EntityNotFoundError
            from views.resolution_modal import EntityResolutionDialog
            
            members = None
            while True:
                try:
                    members = parse_pokepaste(paste, corrections=self.corrections)
                    break
                except EntityNotFoundError as e:
                    if hasattr(main_win, "hide_loading"):
                        main_win.hide_loading()
                    dialog = EntityResolutionDialog(e, self)
                    if dialog.exec() == QDialog.Accepted:
                        self.corrections[e.raw_name] = dialog.selected_name
                        if hasattr(main_win, "show_loading"):
                            main_win.show_loading("Ripresa parsing...")
                        QApplication.processEvents()
                    else:
                        return
                        
            if not members:
                if hasattr(main_win, "hide_loading"):
                    main_win.hide_loading()
                QMessageBox.warning(self, "Errore", "Impossibile parsare il team.")
                return
                
            self.teams.append({"members": members})
            self.txt_paste.clear()
            self._render_explorer()
            
        finally:
            if hasattr(main_win, "hide_loading"):
                main_win.hide_loading()

    def _clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                elif item.layout():
                    self._clear_layout(item.layout())
            layout.deleteLater()

    def _render_explorer(self):
        while self.explorer_layout.count() > 1:
            item = self.explorer_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
                
        for idx, team_data in enumerate(self.teams):
            team_widget = QFrame()
            team_widget.setStyleSheet(f"background: {Palette.BG_SURFACE_ELEVATED}; border: 1px solid {Palette.BORDER_COLOR}; border-radius: 8px; margin-bottom: 15px;")
            team_layout = QVBoxLayout(team_widget)
            
            header_layout = QHBoxLayout()
            lbl_title = QLabel(f"Team {idx + 1}")
            lbl_title.setStyleSheet(f"color: {Palette.PRIMARY}; font-weight: bold; font-size: 16px; border: none;")
            
            btn_analyze = QPushButton("Analizza Questo Team")
            btn_analyze.setStyleSheet(
                f"QPushButton {{ background-color: {Palette.TERTIARY}; color: {Palette.TEXT_PRIMARY}; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold; }}"
                f"QPushButton:hover {{ background-color: {Palette.SECONDARY}; }}"
            )
            btn_analyze.clicked.connect(lambda checked=False, i=idx: self.on_analyze_team(i))
            
            btn_delete = QPushButton("Rimuovi")
            btn_delete.setStyleSheet(
                f"QPushButton {{ background-color: #7F1D1D; color: {Palette.TEXT_PRIMARY}; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold; }}"
                f"QPushButton:hover {{ background-color: #991B1B; }}"
            )
            btn_delete.clicked.connect(lambda checked=False, i=idx: self._delete_team(i))
            
            btn_batch = QPushButton("Analisi Batch Danni")
            btn_batch.setStyleSheet(
                f"QPushButton {{ background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold; }}"
                f"QPushButton:hover {{ background-color: {Palette.TEXT_PRIMARY}; }}"
            )
            btn_batch.clicked.connect(lambda checked=False, i=idx: self.on_batch_damage_analysis(i))
            
            btn_copy = QPushButton("📋 Copia Paste")
            btn_copy.setStyleSheet(
                f"QPushButton {{ background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold; }}"
                f"QPushButton:hover {{ background-color: {Palette.TEXT_PRIMARY}; }}"
            )
            btn_copy.clicked.connect(lambda checked=False, i=idx: self._copy_team(i))
            
            header_layout.addWidget(lbl_title)
            header_layout.addStretch()
            header_layout.addWidget(btn_copy)
            header_layout.addWidget(btn_analyze)
            header_layout.addWidget(btn_batch)
            header_layout.addWidget(btn_delete)
            team_layout.addLayout(header_layout)
            
            grid_layout = QHBoxLayout()
            for m_idx, member in enumerate(team_data["members"]):
                card = QWidget()
                card.setStyleSheet(f"background: {Palette.BG_APP}; border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 6px;")
                card_layout = QVBoxLayout(card)
                
                icon = QLabel()
                pixmap = get_pokemon_pixmap(member.species, 48)
                if pixmap: icon.setPixmap(pixmap)
                
                lbl_name = QLabel(member.species)
                lbl_name.setStyleSheet(f"font-weight: bold; color: {Palette.TEXT_PRIMARY}; border: none;")
                
                btn_edit = QPushButton("Modifica")
                btn_edit.setStyleSheet(
                    f"QPushButton {{ background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_MUTED}; border: 1px solid {Palette.BORDER_LIGHT}; padding: 4px; border-radius: 4px; }}"
                    f"QPushButton:hover {{ color: {Palette.TEXT_PRIMARY}; border-color: {Palette.PRIMARY}; }}"
                )
                btn_edit.clicked.connect(lambda checked=False, t_i=idx, m_i=m_idx: self._edit_member(t_i, m_i))
                
                card_layout.addWidget(icon, alignment=Qt.AlignCenter)
                card_layout.addWidget(lbl_name, alignment=Qt.AlignCenter)
                card_layout.addWidget(btn_edit)
                
                grid_layout.addWidget(card)
                
            grid_layout.addStretch()
            team_layout.addLayout(grid_layout)
            self.explorer_layout.insertWidget(self.explorer_layout.count() - 1, team_widget)
            
    def _delete_team(self, idx: int):
        if 0 <= idx < len(self.teams):
            del self.teams[idx]
            self._render_explorer()
            
    def _copy_team(self, idx: int):
        if not (0 <= idx < len(self.teams)): return
        
        team_data = self.teams[idx]
        paste = ""
        
        def to_champ_ev(val: int) -> int:
            return (val + 4) // 8 if val > 0 else 0
            
        for member in team_data.get("members", []):
            header = member.species.capitalize()
            if member.item:
                header += f" @ {member.item}"
            paste += f"{header}\n"
            
            if member.ability:
                paste += f"Ability: {member.ability}\n"
                
            paste += f"Level: {member.level if hasattr(member, 'level') and member.level else 50}\n"
            
            evs = member.evs
            total_evs = sum(evs.values())
            is_champ = total_evs <= 66
            
            display_labels = ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]
            
            ev_strings = []
            for label in display_labels:
                # Cerca in vari formati di chiave
                val = evs.get(label, evs.get(label.lower(), evs.get(label.upper(), 0)))
                if val > 0:
                    c_val = val if is_champ else to_champ_ev(val)
                    ev_strings.append(f"{c_val} {label}")
                    
            if ev_strings:
                paste += f"EVs: {' / '.join(ev_strings)}\n"
                
            if member.nature:
                paste += f"{member.nature} Nature\n"
                
            for m in member.moves:
                if m:
                    paste += f"- {m}\n"
                    
            paste += "\n"
            
        if paste:
            QApplication.clipboard().setText(paste.strip())
            
    def _edit_member(self, t_idx: int, m_idx: int):
        main_win = self.window()
        if hasattr(main_win, "show_loading"):
            main_win.show_loading("Caricamento Pokemon...")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        
        try:
            member = self.teams[t_idx]["members"][m_idx]
            self.current_editing_team = self.teams[t_idx]
            self.page_edit.load_member(member)
            self.stacked.setCurrentWidget(self.page_edit)
        finally:
            if hasattr(main_win, "hide_loading"):
                main_win.hide_loading()
        
    def _on_pokemon_updated(self):
        self._render_explorer()
            
    def on_batch_damage_analysis(self, index: int):
        team = self.teams[index]
        
        dialog = BatchDamageConfigDialog(self)
        if dialog.exec() == QDialog.Accepted:
            main_win = self.window()
            if hasattr(main_win, "show_loading"):
                main_win.show_loading("Elaborazione batch in corso...")
            QApplication.processEvents()
            
            try:
                target_type = dialog.selected_target_type
                if target_type == "Formato":
                    meta_threats = BatchGeneratorService.generate_threats_from_format(
                        dialog.selected_format, 
                        dialog.min_usage
                    )
                else:
                    # Raccoglie gli altri team caricati
                    other_teams = [t for i, t in enumerate(self.teams) if i != index]
                    meta_threats = BatchGeneratorService.generate_threats_from_teams(other_teams)
                
                # Prepara il team target
                team_data = []
                for m in team["members"]:
                    team_data.append({
                        "name": m.species,
                        "options": {
                            "nature": m.nature,
                            "item": m.item,
                            "evs": m.evs
                        },
                        "moves": [mv for mv in m.moves if mv]
                    })
                
                calc = SmogonDamageCalc(db_path="janalytics.db")
                analyzer = BatchDamageAnalyzer(calc)
                
                def_results, off_results, switch_results = analyzer.perform_full_analysis(team_data, meta_threats)
                
                if hasattr(main_win, "hide_loading"):
                    main_win.hide_loading()
                    
                result_dialog = BatchDamageResultDialog(def_results, off_results, switch_results, team_data, self)
                result_dialog.exec()
                
            except Exception as e:
                if hasattr(main_win, "hide_loading"):
                    main_win.hide_loading()
                QMessageBox.critical(self, "Errore", f"Errore durante l'analisi batch: {e}")

    def on_analyze_team(self, index: int):
        if index < 0 or index >= len(self.teams):
            return
            
        main_win = self.window()
        if hasattr(main_win, "show_loading"):
            main_win.show_loading("Elaborazione dati in corso...")
        QApplication.processEvents()
        
        try:
            team_members = self.teams[index]["members"]
            title = ", ".join([m.species for m in team_members[:3]])
            self.lbl_analyzed_team.setText(f"Analisi Team: {title}...")
            
            self._update_defensive_table(team_members)
            self._update_offensive_tables(team_members)
            self._update_vs_tables(index)
            
            self.stacked.setCurrentWidget(self.page_analysis)
        finally:
            if hasattr(main_win, "hide_loading"):
                main_win.hide_loading()
                
    def _update_defensive_table(self, members: List[TeamMember]):
        table = self.table_defensive
        all_types = list(TYPE_DATA.keys())
        
        table.setRowCount(len(all_types))
        table.setColumnCount(len(members))
        
        table.setHorizontalHeaderLabels([m.species for m in members])
        
        for i, atk_type in enumerate(all_types):
            badge = TypeBadge(atk_type)
            table.setCellWidget(i, -1, badge)
            table.setVerticalHeaderItem(i, QTableWidgetItem(atk_type))
            
            for j, member in enumerate(members):
                if not member.types:
                    table.setItem(i, j, QTableWidgetItem("-"))
                    continue
                    
                mult = get_multiplier(member.types, atk_type)
                
                text = ""
                bg_color = Palette.BG_SURFACE
                fg_color = Palette.TEXT_PRIMARY
                
                if mult == 0:
                    text = "0"
                    bg_color = "#111827" 
                elif mult == 0.25:
                    text = "¼"
                    bg_color = "#166534"
                elif mult == 0.5:
                    text = "½"
                    bg_color = "#064E3B"
                elif mult == 2.0:
                    text = "2"
                    bg_color = "#7F1D1D"
                    fg_color = "#FECACA"
                elif mult == 4.0:
                    text = "4"
                    bg_color = "#4C1D95"
                    fg_color = "#EDE9FE"
                elif mult == 1.0:
                    text = "1"
                    
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor(bg_color))
                item.setForeground(QColor(fg_color))
                table.setItem(i, j, item)
                
        for i, atk_type in enumerate(all_types):
            item = table.verticalHeaderItem(i)
            if item:
                item.setForeground(QColor(TYPE_COLORS.get(atk_type, "#FFF")))
                font = item.font()
                font.setBold(True)
                item.setFont(font)

    def _update_offensive_tables(self, members: List[TeamMember]):
        all_types = list(TYPE_DATA.keys())
        
        phys_moves = []
        spec_moves = []
        
        for member in members:
            for move in member.moves_data:
                if move.get("category") == "Physical":
                    phys_moves.append(move)
                elif move.get("category") == "Special":
                    spec_moves.append(move)
                    
        self._populate_offensive_table(self.table_off_phys, phys_moves, all_types)
        self._populate_offensive_table(self.table_off_spec, spec_moves, all_types)
        self._populate_offensive_table(self.table_off_tot, phys_moves + spec_moves, all_types)

    def _populate_offensive_table(self, table: QTableWidget, moves: List[Dict[str, Any]], all_types: List[str]):
        table.setRowCount(len(moves) + 1)
        table.setColumnCount(len(all_types))
        
        table.setHorizontalHeaderLabels(all_types)
        for j, atk_type in enumerate(all_types):
            h_item = table.horizontalHeaderItem(j)
            if h_item:
                h_item.setForeground(QColor(TYPE_COLORS.get(atk_type, "#FFF")))
                font = h_item.font()
                font.setBold(True)
                h_item.setFont(font)
        
        sums = {t: 0 for t in all_types}
        
        v_headers = []
        for move in moves:
            v_headers.append(move['name'])
        v_headers.append("SOMMA")
        table.setVerticalHeaderLabels(v_headers)
        
        for i, move in enumerate(moves):
            v_item = table.verticalHeaderItem(i)
            if v_item:
                v_item.setForeground(QColor(TYPE_COLORS.get(move['type'].capitalize(), "#FFF")))
                font = v_item.font()
                font.setBold(True)
                v_item.setFont(font)
                
        sum_item = table.verticalHeaderItem(len(moves))
        if sum_item:
            sum_item.setForeground(QColor(Palette.PRIMARY))
            font = sum_item.font()
            font.setBold(True)
            sum_item.setFont(font)
        
        for i, move in enumerate(moves):
            move_type = move['type']
            for j, def_type in enumerate(all_types):
                mult = get_multiplier([def_type], move_type)
                
                text = ""
                bg_color = Palette.BG_SURFACE
                fg_color = Palette.TEXT_PRIMARY
                
                if mult > 1:
                    text = str(int(mult))
                    bg_color = "#064E3B"
                    sums[def_type] += 1
                elif mult < 1:
                    if mult == 0:
                        text = "0"
                        bg_color = "#111827"
                    else:
                        text = "½"
                        bg_color = "#450A0A"
                        
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor(bg_color))
                item.setForeground(QColor(fg_color))
                table.setItem(i, j, item)
                
        sum_row = len(moves)
        for j, def_type in enumerate(all_types):
            val = sums[def_type]
            text = str(val) if val > 0 else "0"
            bg_color = Palette.TERTIARY if val > 0 else Palette.BG_SURFACE_ELEVATED
            fg_color = Palette.BG_APP if val > 0 else Palette.TEXT_MUTED
            
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            item.setBackground(QColor(bg_color))
            item.setForeground(QColor(fg_color))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            table.setItem(sum_row, j, item)
            
    def _update_vs_tables(self, analyzed_idx: int):
        my_members = self.teams[analyzed_idx]["members"]
        
        other_members = []
        for i, t in enumerate(self.teams):
            if i != analyzed_idx:
                other_members.extend(t["members"])
                
        opposing_moves = []
        opposing_move_names = set()
        for m in other_members:
            for move in m.moves_data:
                if move.get("category") in ["Physical", "Special"] and move["name"] not in opposing_move_names:
                    opposing_moves.append(move)
                    opposing_move_names.add(move["name"])
                    
        self.table_vs_def.setRowCount(len(my_members))
        self.table_vs_def.setColumnCount(len(opposing_moves))
        
        self.table_vs_def.setVerticalHeaderLabels([m.species for m in my_members])
        self.table_vs_def.setHorizontalHeaderLabels([f"{m['name']}" for m in opposing_moves])
        
        for j, move in enumerate(opposing_moves):
            h_item = self.table_vs_def.horizontalHeaderItem(j)
            if h_item:
                h_item.setForeground(QColor(TYPE_COLORS.get(move['type'].capitalize(), "#FFF")))
                font = h_item.font()
                font.setBold(True)
                h_item.setFont(font)
        
        for i, member in enumerate(my_members):
            for j, move in enumerate(opposing_moves):
                mult = get_multiplier(member.types, move['type'])
                text, bg_color, fg_color = self._get_color_for_mult(mult)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor(bg_color))
                item.setForeground(QColor(fg_color))
                self.table_vs_def.setItem(i, j, item)
                
        my_moves = []
        my_move_names = set()
        for m in my_members:
            for move in m.moves_data:
                if move.get("category") in ["Physical", "Special"] and move["name"] not in my_move_names:
                    my_moves.append(move)
                    my_move_names.add(move["name"])
                    
        unique_opposing = []
        seen_species = set()
        for m in other_members:
            if m.species not in seen_species:
                unique_opposing.append(m)
                seen_species.add(m.species)
                
        self.table_vs_off.setRowCount(len(unique_opposing))
        self.table_vs_off.setColumnCount(len(my_moves))
        
        self.table_vs_off.setVerticalHeaderLabels([m.species for m in unique_opposing])
        self.table_vs_off.setHorizontalHeaderLabels([f"{m['name']}" for m in my_moves])
        
        for j, move in enumerate(my_moves):
            h_item = self.table_vs_off.horizontalHeaderItem(j)
            if h_item:
                h_item.setForeground(QColor(TYPE_COLORS.get(move['type'].capitalize(), "#FFF")))
                font = h_item.font()
                font.setBold(True)
                h_item.setFont(font)
                
        for i, opp_member in enumerate(unique_opposing):
            for j, move in enumerate(my_moves):
                mult = get_multiplier(opp_member.types, move['type'])
                text, bg_color, fg_color = self._get_color_for_mult(mult)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor(bg_color))
                item.setForeground(QColor(fg_color))
                self.table_vs_off.setItem(i, j, item)

    def _get_color_for_mult(self, mult: float):
        text = "1"
        bg_color = Palette.BG_SURFACE
        fg_color = Palette.TEXT_PRIMARY
        
        if mult == 0:
            text = "0"
            bg_color = "#111827"
        elif mult == 0.25:
            text = "¼"
            bg_color = "#0284C7"
        elif mult == 0.5:
            text = "½"
            bg_color = "#16A34A"
        elif mult == 2.0:
            text = "2"
            bg_color = "#DC2626"
            fg_color = "#FECACA"
        elif mult == 4.0:
            text = "4"
            bg_color = "#9333EA"
            fg_color = "#EDE9FE"
            
        return text, bg_color, fg_color
