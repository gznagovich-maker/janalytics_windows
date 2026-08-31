import os
from typing import Dict, List, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QSlider, QScrollArea, QGridLayout,
    QCompleter, QFrame, QFormLayout, QMessageBox, QToolTip, QDialog,
    QStackedWidget, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QApplication
)
from PySide6.QtCore import Qt, Signal, QSize, QThread
from PySide6.QtGui import QColor, QFont, QPixmap, QPainter, QIcon
from PySide6.QtCharts import (
    QChart, QChartView, QBarSet, QStackedBarSeries, QBarCategoryAxis,
    QValueAxis, QLineSeries
)
from config.theme import Palette

from src.domain.team_builder_service import (
    TeamMember, get_all_species_names, get_species_types, get_all_items,
    get_pokeapi_legal_moves_and_abilities, calculate_vgc_stat, get_legal_moves_details,
    get_legal_abilities_details, get_all_items_details
)
from database.connection import SessionLocal
from database.models_v2 import MatchV2, PokemonSpeciesV2, MatchTeamV2, TeamVariantV2, PokemonBuild, TeamVariantBuild

from domain.batch_analyzer import BatchDamageAnalyzer, PokemonOptions, FieldOptions
from domain.smogon_calc import SmogonDamageCalc
from src.domain.batch_generator_service import BatchGeneratorService
from src.utils.icon_utils import get_pokemon_icon_path

class CustomSliderLayout(QWidget):
    valueChanged = Signal(str, int)
    
    def __init__(self, stat_name: str, max_val: int = 252):
        super().__init__()
        self.stat_name = stat_name
        self._is_updating = False
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        lbl = QLabel(stat_name)
        lbl.setMinimumWidth(30)
        lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-weight: bold;")
        
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, max_val)
        
        self.spin = QSpinBox()
        self.spin.setRange(0, max_val)
        self.spin.setButtonSymbols(QSpinBox.NoButtons)
        self.spin.setStyleSheet(f"background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY}; padding: 2px;")
        
        layout.addWidget(lbl)
        layout.addWidget(self.slider)
        layout.addWidget(self.spin)
        
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.spin.valueChanged.connect(self._on_spin_changed)
        
    def _on_slider_changed(self, val):
        if self._is_updating: return
        self._is_updating = True
        self.spin.setValue(val)
        self.valueChanged.emit(self.stat_name, val)
        self._is_updating = False
        
    def _on_spin_changed(self, val):
        if self._is_updating: return
        self._is_updating = True
        self.slider.setValue(val)
        self.valueChanged.emit(self.stat_name, val)
        self._is_updating = False

    def value(self):
        return self.spin.value()
        
    def setValue(self, val):
        self._is_updating = True
        self.slider.setValue(val)
        self.spin.setValue(val)
        self._is_updating = False

    def setMaxRange(self, max_val: int):
        self.slider.setRange(0, max_val)
        self.spin.setRange(0, max_val)

class PokemonEditPage(QWidget):
    go_back = Signal()
    pokemon_updated = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.member = None
        self.base_stats = {}
        
        main_layout = QVBoxLayout(self)
        
        # Header
        header_layout = QHBoxLayout()
        btn_back = QPushButton("← Torna ai Team")
        btn_back.setStyleSheet(f"background-color: {Palette.TERTIARY}; color: {Palette.TEXT_PRIMARY}; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_back.clicked.connect(self.go_back.emit)
        
        self.lbl_title = QLabel("Modifica Pokémon")
        self.lbl_title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {Palette.PRIMARY};")
        
        self.btn_champions = QPushButton("★ Modalità Champions")
        self.btn_champions.setCheckable(True)
        self.btn_champions.setChecked(True)
        self.btn_champions.setStyleSheet(f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; font-weight: bold; padding: 5px;")
        self.btn_champions.clicked.connect(self._toggle_champions_mode)
        
        header_layout.addWidget(btn_back)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_champions)
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)
        
        # Splitter Layout (Left: Form, Right: Charts/Moves)
        content_layout = QHBoxLayout()
        
        # --- LEFT PANEL ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        form = QFormLayout()
        self.combo_species = QComboBox()
        self.combo_species.setEditable(True)
        all_species = get_all_species_names()
        self.combo_species.addItems(all_species)
        completer = QCompleter(all_species)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.combo_species.setCompleter(completer)
        self.combo_species.currentTextChanged.connect(self._on_species_changed)
        form.addRow("Specie:", self.combo_species)
        
        self.btn_ability = QPushButton("Seleziona Abilità")
        self.btn_ability.setStyleSheet(f"background-color: {Palette.BG_SURFACE_ELEVATED}; padding: 8px; text-align: left;")
        self.btn_ability.clicked.connect(self._open_ability_selection)
        form.addRow("Abilità:", self.btn_ability)
        
        self.btn_item = QPushButton("Seleziona Strumento")
        self.btn_item.setStyleSheet(f"background-color: {Palette.BG_SURFACE_ELEVATED}; padding: 8px; text-align: left;")
        self.btn_item.clicked.connect(self._open_item_selection)
        form.addRow("Strumento:", self.btn_item)
        
        self.combo_nature = QComboBox()
        self.combo_nature.setEditable(True)
        NATURES_MAP = {
            "Adamant": "(+Atk, -SpA)", "Modest": "(+SpA, -Atk)", "Jolly": "(+Spe, -SpA)", "Timid": "(+Spe, -Atk)",
            "Brave": "(+Atk, -Spe)", "Quiet": "(+SpA, -Spe)", "Relaxed": "(+Def, -Spe)", "Sassy": "(+SpD, -Spe)",
            "Impish": "(+Def, -SpA)", "Careful": "(+SpD, -SpA)", "Bold": "(+Def, -Atk)", "Calm": "(+SpD, -Atk)",
            "Naughty": "(+Atk, -SpD)", "Rash": "(+SpA, -SpD)", "Naive": "(+Spe, -SpD)", "Hasty": "(+Spe, -Def)",
            "Lonely": "(+Atk, -Def)", "Mild": "(+SpA, -Def)", "Lax": "(+Def, -SpD)", "Gentle": "(+SpD, -Def)",
            "Hardy": "(Neutral)", "Docile": "(Neutral)", "Serious": "(Neutral)", "Bashful": "(Neutral)", "Quirky": "(Neutral)"
        }
        for nat, desc in NATURES_MAP.items():
            self.combo_nature.addItem(f"{nat} {desc}", userData=nat)
        self.combo_nature.currentTextChanged.connect(self._update_stats_calc)
        form.addRow("Natura:", self.combo_nature)
        
        self.move_buttons = []
        for i in range(4):
            btn = QPushButton("Nessuna Mossa")
            btn.setStyleSheet(f"background-color: {Palette.BG_SURFACE_ELEVATED}; padding: 8px; text-align: left;")
            btn.clicked.connect(lambda _, idx=i: self._open_move_selection(idx))
            self.move_buttons.append(btn)
            form.addRow(f"Mossa {i+1}:", btn)
            
        left_layout.addLayout(form)
        
        # EVs and IVs
        ev_iv_layout = QGridLayout()
        ev_iv_layout.addWidget(QLabel("Statistica"), 0, 0)
        ev_iv_layout.addWidget(QLabel("IV"), 0, 1)
        ev_iv_layout.addWidget(QLabel("EVs"), 0, 2)
        ev_iv_layout.addWidget(QLabel("Stat Finale"), 0, 3)
        
        self.ev_sliders = {}
        self.iv_spins = {}
        self.stat_labels = {}
        
        stats = ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]
        for i, stat in enumerate(stats):
            # IV
            iv = QSpinBox()
            iv.setRange(0, 31)
            iv.setValue(31)
            iv.valueChanged.connect(self._update_stats_calc)
            self.iv_spins[stat] = iv
            
            # EV Slider
            slider = CustomSliderLayout(stat)
            slider.valueChanged.connect(self._on_ev_changed)
            self.ev_sliders[stat] = slider
            
            # Final Stat Label
            lbl = QLabel("0")
            lbl.setStyleSheet(f"font-weight: bold; color: {Palette.PRIMARY};")
            self.stat_labels[stat] = lbl
            
            ev_iv_layout.addWidget(QLabel(stat), i+1, 0)
            ev_iv_layout.addWidget(iv, i+1, 1)
            ev_iv_layout.addWidget(slider, i+1, 2)
            ev_iv_layout.addWidget(lbl, i+1, 3)
            
        left_layout.addLayout(ev_iv_layout)
        
        self.lbl_ev_total = QLabel("EV Rimanenti: 508")
        self.lbl_ev_total.setStyleSheet("font-weight: bold; color: #E5A353;")
        left_layout.addWidget(self.lbl_ev_total)
        left_layout.addStretch()
        
        # --- RIGHT PANEL ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.currentTextChanged.connect(self._build_charts)
        controls_layout.addWidget(self.format_combo)
        controls_layout.addStretch()
        right_layout.addLayout(controls_layout)
        
        self.right_stack = QStackedWidget()
        
        # Page 0: Charts
        scroll_right = QScrollArea()
        scroll_right.setWidgetResizable(True)
        scroll_right.setStyleSheet("QScrollArea { border: none; }")
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        self.chart_container = QWidget()
        self.chart_layout = QGridLayout(self.chart_container)
        scroll_layout.addWidget(self.chart_container)
        
        # --- SEZIONE DAMAGE CALC (OPZIONE 2) ---
        calc_widget = QFrame()
        calc_widget.setStyleSheet(f"background-color: {Palette.BG_SURFACE_ELEVATED}; border-radius: 8px; margin-top: 10px;")
        calc_layout = QVBoxLayout(calc_widget)
        
        lbl_calc = QLabel("🎯 Damage Calculator Rapido (Testa le mosse equipaggiate sul Meta)")
        lbl_calc.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {Palette.PRIMARY}; margin-bottom: 5px;")
        calc_layout.addWidget(lbl_calc)
        
        # Bottoni delle 4 mosse
        self.calc_move_buttons_layout = QHBoxLayout()
        self.calc_move_btns = []
        for i in range(4):
            btn = QPushButton("Slot Vuoto")
            btn.setStyleSheet(f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT_PRIMARY}; padding: 8px; border-radius: 4px; border: 1px solid {Palette.BORDER_COLOR};")
            btn.setEnabled(False)
            btn.clicked.connect(lambda checked, idx=i: self._run_main_damage_calc(idx))
            self.calc_move_btns.append(btn)
            self.calc_move_buttons_layout.addWidget(btn)
            
        calc_layout.addLayout(self.calc_move_buttons_layout)
        
        # Filtri e Tabella
        calc_filters = QHBoxLayout()
        self.search_calc_pokemon = QLineEdit()
        self.search_calc_pokemon.setPlaceholderText("Filtra per nome...")
        self.search_calc_pokemon.textChanged.connect(self._filter_calc_table)
        self.filter_calc_type = QComboBox()
        self.filter_calc_type.addItems(["Tutti i Tipi", "Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"])
        self.filter_calc_type.currentTextChanged.connect(self._filter_calc_table)
        calc_filters.addWidget(self.search_calc_pokemon)
        calc_filters.addWidget(self.filter_calc_type)
        calc_layout.addLayout(calc_filters)
        
        self.calc_table = QTableWidget()
        self.calc_table.setColumnCount(3)
        self.calc_table.setHorizontalHeaderLabels(["Pokemon", "Max Def", "Min Def"])
        self.calc_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.calc_table.verticalHeader().setVisible(False)
        self.calc_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.calc_table.setMinimumHeight(200)
        self.calc_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {Palette.BG_SURFACE};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_COLOR};
                gridline-color: {Palette.BORDER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {Palette.BG_CARD};
                color: {Palette.TEXT_PRIMARY};
                padding: 4px;
                border: 1px solid {Palette.BORDER_COLOR};
                font-weight: bold;
            }}
        """)
        calc_layout.addWidget(self.calc_table)
        
        scroll_layout.addWidget(calc_widget)
        
        scroll_right.setWidget(scroll_content)
        
        self.right_stack.addWidget(scroll_right)
        
        # Page 1: Move Selection
        self.moves_container_widget = QWidget()
        moves_main_layout = QVBoxLayout(self.moves_container_widget)
        
        header_moves = QHBoxLayout()
        self.lbl_moves_title = QLabel("Seleziona una mossa")
        self.lbl_moves_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {Palette.TEXT_PRIMARY};")
        btn_cancel_moves = QPushButton("Indietro")
        btn_cancel_moves.setStyleSheet(f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; padding: 5px 15px;")
        btn_cancel_moves.clicked.connect(lambda: self.right_stack.setCurrentIndex(0))
        
        header_moves.addWidget(self.lbl_moves_title)
        header_moves.addStretch()
        header_moves.addWidget(btn_cancel_moves)
        moves_main_layout.addLayout(header_moves)
        
        filters_layout = QHBoxLayout()
        self.search_move = QLineEdit()
        self.search_move.setPlaceholderText("Cerca mossa...")
        self.search_move.textChanged.connect(self._filter_moves)
        self.filter_move_type = QComboBox()
        self.filter_move_type.addItems(["Tutti i Tipi", "Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"])
        self.filter_move_type.currentTextChanged.connect(self._filter_moves)
        self.filter_move_cat = QComboBox()
        self.filter_move_cat.addItems(["Tutte", "Physical", "Special", "Status"])
        self.filter_move_cat.currentTextChanged.connect(self._filter_moves)
        filters_layout.addWidget(self.search_move)
        filters_layout.addWidget(self.filter_move_type)
        filters_layout.addWidget(self.filter_move_cat)
        moves_main_layout.addLayout(filters_layout)
        
        scroll_moves = QScrollArea()
        scroll_moves.setWidgetResizable(True)
        scroll_moves.setStyleSheet("QScrollArea { border: none; }")
        self.moves_list_widget = QWidget()
        self.moves_list_layout = QVBoxLayout(self.moves_list_widget)
        self.moves_list_layout.addStretch()
        scroll_moves.setWidget(self.moves_list_widget)
        moves_main_layout.addWidget(scroll_moves)
        self.right_stack.addWidget(self.moves_container_widget)
        
        self.current_calc_data = []

        
        # Page 2: Ability Selection
        self.ability_container_widget = QWidget()
        ability_main_layout = QVBoxLayout(self.ability_container_widget)
        header_ability = QHBoxLayout()
        self.lbl_ability_title = QLabel("Seleziona un'abilità")
        self.lbl_ability_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {Palette.TEXT_PRIMARY};")
        btn_cancel_ability = QPushButton("Indietro")
        btn_cancel_ability.setStyleSheet(f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; padding: 5px 15px;")
        btn_cancel_ability.clicked.connect(lambda: self.right_stack.setCurrentIndex(0))
        header_ability.addWidget(self.lbl_ability_title)
        header_ability.addStretch()
        header_ability.addWidget(btn_cancel_ability)
        ability_main_layout.addLayout(header_ability)
        scroll_ability = QScrollArea()
        scroll_ability.setWidgetResizable(True)
        scroll_ability.setStyleSheet("QScrollArea { border: none; }")
        self.ability_list_widget = QWidget()
        self.ability_list_layout = QVBoxLayout(self.ability_list_widget)
        self.ability_list_layout.addStretch()
        scroll_ability.setWidget(self.ability_list_widget)
        ability_main_layout.addWidget(scroll_ability)
        self.right_stack.addWidget(self.ability_container_widget)
        
        # Page 3: Item Selection
        self.item_container_widget = QWidget()
        item_main_layout = QVBoxLayout(self.item_container_widget)
        header_item = QHBoxLayout()
        self.lbl_item_title = QLabel("Seleziona uno strumento")
        self.lbl_item_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {Palette.TEXT_PRIMARY};")
        btn_cancel_item = QPushButton("Indietro")
        btn_cancel_item.setStyleSheet(f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; padding: 5px 15px;")
        btn_cancel_item.clicked.connect(lambda: self.right_stack.setCurrentIndex(0))
        header_item.addWidget(self.lbl_item_title)
        header_item.addStretch()
        header_item.addWidget(btn_cancel_item)
        item_main_layout.addLayout(header_item)
        self.search_item = QLineEdit()
        self.search_item.setPlaceholderText("Cerca strumento...")
        self.search_item.textChanged.connect(self._filter_items)
        item_main_layout.addWidget(self.search_item)
        scroll_item = QScrollArea()
        scroll_item.setWidgetResizable(True)
        scroll_item.setStyleSheet("QScrollArea { border: none; }")
        self.item_list_widget = QWidget()
        self.item_list_layout = QVBoxLayout(self.item_list_widget)
        self.item_list_layout.addStretch()
        scroll_item.setWidget(self.item_list_widget)
        item_main_layout.addWidget(scroll_item)
        self.right_stack.addWidget(self.item_container_widget)

        
        right_layout.addWidget(self.right_stack)
        
        content_layout.addWidget(left_panel, 1)
        content_layout.addWidget(right_panel, 2)
        
        main_layout.addLayout(content_layout)
        
        self.btn_save = QPushButton("Salva e Chiudi")
        self.btn_save.setStyleSheet(f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; font-weight: bold; padding: 10px;")
        self.btn_save.clicked.connect(self.save_and_exit)
        main_layout.addWidget(self.btn_save)
        
        self.charts = {}
        self.chart_views = {}
        self.chart_lines = {}
        self.move_cards = []
        self.ability_cards = []
        self.item_cards = []
        self.cached_all_items = []
        self._populate_formats()
        
    def _populate_formats(self):
        with SessionLocal() as session:
            formats = session.query(MatchV2.format).distinct().all()
            for f in formats:
                if f[0]:
                    self.format_combo.addItem(f[0])

    def load_member(self, member: TeamMember):
        self.member = member
        self.lbl_title.setText(f"Modifica {member.species}")
        
        self.combo_species.blockSignals(True)
        self.combo_species.setCurrentText(member.species)
        self.combo_species.blockSignals(False)
        
        self.combo_species.blockSignals(False)
        
        if member.item: self.btn_item.setText(member.item)
        if member.nature:
            # Trova l'indice della natura per impostare il testo con i bonus
            idx = self.combo_nature.findData(member.nature)
            if idx >= 0:
                self.combo_nature.setCurrentIndex(idx)
            else:
                self.combo_nature.setCurrentText(member.nature)
        
        self._on_species_changed(member.species)
        
        if member.ability: self.btn_ability.setText(member.ability)
        
        if self.member.moves_data:
            for i in range(4):
                if i < len(self.member.moves_data):
                    mv_name = self.member.moves_data[i].get('name', 'Nessuna Mossa')
                    self.move_buttons[i].setText(mv_name)
                else:
                    self.move_buttons[i].setText("Nessuna Mossa")
                
        self.btn_champions.setChecked(member.is_champions_mode)
        self._toggle_champions_mode(init_load=True)
                
        for stat, val in member.ivs.items():
            if stat in self.iv_spins:
                self.iv_spins[stat].setValue(val)
        for stat, val in member.evs.items():
            if stat in self.ev_sliders:
                self.ev_sliders[stat].setValue(val)
                
        self._update_stats_calc()
        self._build_charts()
        self._update_calc_buttons()

    def _toggle_champions_mode(self, init_load=False):
        is_champ = self.btn_champions.isChecked()
        self._is_updating_evs = True
        
        if is_champ:
            self.btn_champions.setStyleSheet(f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; font-weight: bold; padding: 5px;")
            if not init_load:
                for s in self.ev_sliders.values():
                    ev = s.value()
                    sp = (ev + 4) // 8 if ev > 0 else 0
                    s.setMaxRange(32)
                    s.setValue(sp)
            else:
                for s in self.ev_sliders.values():
                    s.setMaxRange(32)
        else:
            self.btn_champions.setStyleSheet(f"background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY}; font-weight: bold; padding: 5px;")
            if not init_load:
                for s in self.ev_sliders.values():
                    sp = s.value()
                    ev = (sp * 8) - 4 if sp > 0 else 0
                    s.setMaxRange(252)
                    s.setValue(ev)
            else:
                for s in self.ev_sliders.values():
                    s.setMaxRange(252)
                    
        self._is_updating_evs = False
        self._on_ev_changed(None, 0)
        
        if not init_load:
            self._update_stats_calc()

    def _on_species_changed(self, species_name: str):
        if not species_name: return
        with SessionLocal() as session:
            db_pkmn = session.query(PokemonSpeciesV2).filter(PokemonSpeciesV2.name == species_name).first()
            if db_pkmn:
                self.base_stats = {
                    "hp": db_pkmn.bst_hp, "atk": db_pkmn.bst_atk, "def": db_pkmn.bst_def,
                    "spa": db_pkmn.bst_spa, "spd": db_pkmn.bst_spd, "spe": db_pkmn.bst_spe
                }
            else:
                self.base_stats = {"hp": 100, "atk": 100, "def": 100, "spa": 100, "spd": 100, "spe": 100}
        
        self._populate_legal_options(species_name)
        
        import threading
        def fetch_moves():
            self.cached_legal_moves_details = get_legal_moves_details(species_name)
        threading.Thread(target=fetch_moves).start()
        
        self._build_charts()

    def _populate_legal_options(self, species_name: str):
        pass # Abilities are now fetched dynamically in the selection panel
            
        self._update_stats_calc()

    def _on_ev_changed(self, stat_name: str, val: int):
        if getattr(self, '_is_updating_evs', False): return
        
        is_champ = self.btn_champions.isChecked()
        max_total = 66 if is_champ else 508
        
        total = sum(s.value() for s in self.ev_sliders.values())
        if total > max_total and stat_name:
            diff = total - max_total
            new_val = max(0, val - diff)
            
            self._is_updating_evs = True
            self.ev_sliders[stat_name].setValue(new_val)
            self._is_updating_evs = False
            total = max_total
            
        rem = max_total - total
        self.lbl_ev_total.setText(f"EV Rimanenti: {rem} / {max_total}")
        if rem < 0:
            self.lbl_ev_total.setStyleSheet("font-weight: bold; color: #8A3838;") # DANGER
        else:
            self.lbl_ev_total.setStyleSheet("font-weight: bold; color: #E5A353;") # WARNING/BRONZE
            
        self._update_stats_calc()

    def _get_nature_multiplier(self, stat: str, nature: str) -> float:
        nature_map = {
            "Adamant": {"plus": "Atk", "minus": "SpA"},
            "Modest": {"plus": "SpA", "minus": "Atk"},
            "Jolly": {"plus": "Spe", "minus": "SpA"},
            "Timid": {"plus": "Spe", "minus": "Atk"},
            "Brave": {"plus": "Atk", "minus": "Spe"},
            "Quiet": {"plus": "SpA", "minus": "Spe"},
            "Relaxed": {"plus": "Def", "minus": "Spe"},
            "Sassy": {"plus": "SpD", "minus": "Spe"},
            "Impish": {"plus": "Def", "minus": "SpA"},
            "Careful": {"plus": "SpD", "minus": "SpA"},
            "Bold": {"plus": "Def", "minus": "Atk"},
            "Calm": {"plus": "SpD", "minus": "Atk"},
            "Naughty": {"plus": "Atk", "minus": "SpD"},
            "Rash": {"plus": "SpA", "minus": "SpD"},
            "Naive": {"plus": "Spe", "minus": "SpD"},
            "Hasty": {"plus": "Spe", "minus": "Def"},
            "Lonely": {"plus": "Atk", "minus": "Def"},
            "Mild": {"plus": "SpA", "minus": "Def"},
            "Lax": {"plus": "Def", "minus": "SpD"},
            "Gentle": {"plus": "SpD", "minus": "Def"}
        }
        
        mult = 1.0
        if nature in nature_map:
            if nature_map[nature]["plus"] == stat: mult = 1.1
            if nature_map[nature]["minus"] == stat: mult = 0.9
        return mult

    def _update_stats_calc(self, *_):
        if not self.base_stats: return
        nature_full = self.combo_nature.currentText()
        nature = self.combo_nature.currentData() or nature_full.split()[0] if nature_full else "Hardy"
        is_champ = self.btn_champions.isChecked()
        
        self.calculated_stats = {}
        
        for stat in ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]:
            base = self.base_stats.get(stat.lower(), 100)
            iv = self.iv_spins[stat].value()
            slider_val = self.ev_sliders[stat].value()
            
            true_ev = slider_val
            if is_champ:
                true_ev = ((slider_val * 8) - 4) if slider_val > 0 else 0
                
            is_hp = (stat == "HP")
            mult = self._get_nature_multiplier(stat, nature)
            
            final = calculate_vgc_stat(base, iv, true_ev, mult, is_hp)
            self.stat_labels[stat].setText(str(final))
            self.calculated_stats[stat] = final
            
        self._update_chart_lines()

    def _update_chart_lines(self):
        if not hasattr(self, "calculated_stats") or not self.calculated_stats: return
        mapping = {
            "Atk": "Def",
            "SpA": "SpD",
            "Def": "Atk",
            "SpD": "SpA",
            "Spe": "Spe",
            "HP": "HP"
        }
        
        for stat, opp_stat in mapping.items():
            if stat in self.chart_lines and self.chart_lines[stat]:
                my_val = self.calculated_stats.get(stat, 0)
                line = self.chart_lines[stat]
                line.clear()
                line.append(0, my_val)
                line.append(1000, my_val)

    def _build_charts(self):
        fmt = self.format_combo.currentText()
        if not fmt: return
        
        def clear_layout(layout):
            if layout is not None:
                while layout.count():
                    item = layout.takeAt(0)
                    widget = item.widget()
                    if widget is not None:
                        widget.deleteLater()
                    else:
                        sublayout = item.layout()
                        if sublayout is not None:
                            clear_layout(sublayout)
                            sublayout.deleteLater()

        clear_layout(self.chart_layout)
        self.charts = {}
        self.chart_views = {}
        self.chart_lines = {}
        self.move_cards = []
        self.ability_cards = []
        self.item_cards = []
        self.cached_all_items = []
        self.tooltip_data_map = {}
        
        mapping = {
            "Atk": ("Attacco Fisico", "Def", "#8A3838"),
            "SpA": ("Attacco Speciale", "SpD", "#5A5075"),
            "Def": ("Difesa Fisica", "Atk", "#607080"),
            "SpD": ("Difesa Speciale", "SpA", "#8577A8"),
            "Spe": ("Velocità", "Spe", "#C49A3C"),
            "HP": ("HP", "HP", "#3D7A5A")
        }
        
        with SessionLocal() as session:
            match_teams = session.query(MatchTeamV2).join(MatchV2, MatchTeamV2.match_id == MatchV2.id)\
                .filter(MatchV2.format == fmt).all()
            
            variant_ids_list = list(set([mt.team_variant_id for mt in match_teams if mt.team_variant_id]))
            chunk_size = 500
            
            build_ids = set()
            for i in range(0, len(variant_ids_list), chunk_size):
                chunk = variant_ids_list[i:i+chunk_size]
                if chunk:
                    tvbs = session.query(TeamVariantBuild).filter(TeamVariantBuild.team_variant_id.in_(chunk)).all()
                    for tvb in tvbs:
                        if tvb.build_id:
                            build_ids.add(tvb.build_id)
            
            meta_species_set = set()
            build_ids_list = list(build_ids)
            for i in range(0, len(build_ids_list), chunk_size):
                chunk = build_ids_list[i:i+chunk_size]
                if chunk:
                    chunk_species = session.query(PokemonSpeciesV2).join(PokemonBuild, PokemonBuild.species_id == PokemonSpeciesV2.id)\
                        .filter(PokemonBuild.id.in_(chunk)).distinct().all()
                    meta_species_set.update(chunk_species)
                    
            meta_species = list(meta_species_set)

            if not meta_species:
                self.chart_layout.addWidget(QLabel(f"Nessun Pokémon nel metagame {fmt}"), 0, 0)
                return
                
            row, col = 0, 0
            for stat, (title, meta_stat, color) in mapping.items():
                is_hp = (meta_stat == "HP")
                self.tooltip_data_map[stat] = []
                
                chart = QChart()
                chart.setTitle(f"{title} VS {meta_stat} Meta")
                chart.setAnimationOptions(QChart.SeriesAnimations)
                chart.setBackgroundBrush(QColor(Palette.BG_SURFACE))
                chart.setTitleBrush(QColor(Palette.TEXT_PRIMARY))
                
                set_transparent = QBarSet("Trasparente")
                set_transparent.setColor(QColor(0, 0, 0, 0))
                set_transparent.setBorderColor(QColor(0, 0, 0, 0))
                
                set_blue = QBarSet("Min -> Neutra")
                set_blue.setColor(QColor("#B8A9B7"))
                
                set_green = QBarSet("Neutra -> Max")
                set_green.setColor(QColor("#8A7D89"))
                
                set_yellow = QBarSet("Max -> Favorevole")
                set_yellow.setColor(QColor("#C2BFBC"))
                
                meta_species_sorted = sorted(meta_species, key=lambda x: getattr(x, f"bst_{meta_stat.lower()}", 0))
                categories = []
                max_y = 0
                
                import math
                for pkmn in meta_species_sorted:
                    base = getattr(pkmn, f"bst_{meta_stat.lower()}", 100)
                    categories.append(pkmn.name)
                    
                    if is_hp:
                        min_val = base + 75
                        max_val = base + 107
                        self.tooltip_data_map[stat].append({"name": pkmn.name, "min": min_val, "max": max_val})
                        set_transparent.append(min_val)
                        set_blue.append(max_val - min_val)
                        set_green.append(0)
                        set_yellow.append(0)
                        if max_val > max_y: max_y = max_val
                    else:
                        val_min = math.floor((base + 20) * 0.9)
                        val_quasi_min = base + 20
                        val_quasi_max = base + 52
                        val_max = math.floor((base + 52) * 1.1)
                        
                        self.tooltip_data_map[stat].append({
                            "name": pkmn.name,
                            "min": val_min,
                            "quasi_min": val_quasi_min,
                            "quasi_max": val_quasi_max,
                            "max": val_max
                        })
                        
                        set_transparent.append(val_min)
                        set_blue.append(val_quasi_min - val_min)
                        set_green.append(val_quasi_max - val_quasi_min)
                        set_yellow.append(val_max - val_quasi_max)
                        if val_max > max_y: max_y = val_max
                        
                series = QStackedBarSeries()
                series.append(set_transparent)
                series.append(set_blue)
                if not is_hp:
                    series.append(set_green)
                    series.append(set_yellow)
                    
                series.hovered.connect(lambda status, index, barset, s=stat: self.on_bar_hovered(status, index, barset, s))
                series.clicked.connect(lambda index, barset, s=stat: self.on_bar_clicked(index, barset, s))
                    
                chart.addSeries(series)
                
                line_series = QLineSeries()
                line_series.setName(f"Tuo {stat}")
                line_series.setColor(QColor(color))
                pen = line_series.pen()
                pen.setWidth(3)
                line_series.setPen(pen)
                
                my_val = self.calculated_stats.get(stat, 0) if hasattr(self, "calculated_stats") else 0
                line_series.append(0, my_val)
                line_series.append(1000, my_val)
                
                chart.addSeries(line_series)
                self.chart_lines[stat] = line_series
                
                axisX = QBarCategoryAxis()
                axisX.append(categories)
                axisX.setLabelsAngle(-90)
                chart.addAxis(axisX, Qt.AlignBottom)
                series.attachAxis(axisX)
                line_series.attachAxis(axisX)
                
                axisY = QValueAxis()
                axisY.setRange(0, max(max_y, my_val) * 1.1)
                chart.addAxis(axisY, Qt.AlignLeft)
                series.attachAxis(axisY)
                line_series.attachAxis(axisY)
                
                view = QChartView(chart)
                view.setRenderHint(QPainter.RenderHint.Antialiasing)
                view.setMinimumHeight(300)
                view.setRubberBand(QChartView.HorizontalRubberBand)
                
                chart_wrapper = QWidget()
                cw_layout = QVBoxLayout(chart_wrapper)
                cw_layout.setContentsMargins(0, 0, 0, 0)
                
                btn_reset = QPushButton("Reset Zoom")
                btn_reset.setStyleSheet(f"background-color: {Palette.BG_SURFACE_ELEVATED}; color: {Palette.TEXT_PRIMARY}; padding: 4px; border-radius: 4px;")
                btn_reset.clicked.connect(lambda _, ch=chart: ch.zoomReset())
                
                btn_fullscreen = QPushButton("Espandi")
                btn_fullscreen.setStyleSheet(f"background-color: {Palette.BG_SURFACE_ELEVATED}; color: {Palette.TEXT_PRIMARY}; padding: 4px; border-radius: 4px;")
                
                def on_fullscreen(ch=chart, cw=chart_wrapper, lay=cw_layout, v=view, t=title):
                    dlg = QDialog(self)
                    dlg.setWindowTitle(f"Grafico Full Screen: {t}")
                    dlg.resize(1200, 800)
                    dlg.setStyleSheet(f"background-color: {Palette.BG_APP}; color: {Palette.TEXT_PRIMARY};")
                    dlg_layout = QVBoxLayout(dlg)
                    
                    header = QHBoxLayout()
                    btn_dlg_reset = QPushButton("Reset Zoom")
                    btn_dlg_reset.setStyleSheet(btn_reset.styleSheet())
                    btn_dlg_reset.clicked.connect(lambda _, ch2=ch: ch2.zoomReset())
                    
                    btn_close = QPushButton("Chiudi")
                    btn_close.setStyleSheet(btn_reset.styleSheet())
                    btn_close.clicked.connect(dlg.accept)
                    
                    header.addWidget(btn_dlg_reset)
                    header.addStretch()
                    header.addWidget(btn_close)
                    
                    dlg_layout.addLayout(header)
                    dlg_layout.addWidget(v)
                    
                    dlg.exec()
                    lay.addWidget(v)
                    
                btn_fullscreen.clicked.connect(on_fullscreen)
                
                btn_layout = QHBoxLayout()
                btn_layout.addStretch()
                btn_layout.addWidget(btn_reset)
                btn_layout.addWidget(btn_fullscreen)
                
                cw_layout.addLayout(btn_layout)
                cw_layout.addWidget(view)
                
                self.charts[stat] = chart
                self.chart_views[stat] = view
                
                self.chart_layout.addWidget(chart_wrapper, row, col)
                col += 1
                if col > 1:
                    col = 0
                    row += 1
                    
        self._update_chart_lines()
        
    def on_bar_hovered(self, status, index, barset, stat):
        if status and index >= 0 and index < len(self.tooltip_data_map.get(stat, [])):
            data = self.tooltip_data_map[stat][index]
            text = f"<b>{data['name']}</b><br/>"
            if 'quasi_min' in data:
                text += f"Min (Sfavorevole, 0 SP): {data['min']}<br/>"
                text += f"Quasi-Min (Neutra, 0 SP): {data['quasi_min']}<br/>"
                text += f"Quasi-Max (Neutra, 32 SP): {data['quasi_max']}<br/>"
                text += f"Max (Favorevole, 32 SP): {data['max']}"
            else:
                text += f"Min (0 SP): {data['min']}<br/>"
                text += f"Max (32 SP): {data['max']}"
            
            from PySide6.QtGui import QCursor
            QToolTip.showText(QCursor.pos(), text)
        else:
            QToolTip.hideText()

    def on_bar_clicked(self, index, barset, stat):
        if index >= 0 and index < len(self.tooltip_data_map.get(stat, [])):
            data = self.tooltip_data_map[stat][index]
            text = f"Valori statistici per {data['name']}:\n\n"
            if 'quasi_min' in data:
                text += f"- Min (Sfavorevole, 0 SP): {data['min']}\n"
                text += f"- Quasi-Min (Neutra, 0 SP): {data['quasi_min']}\n"
                text += f"- Quasi-Max (Neutra, 32 SP): {data['quasi_max']}\n"
                text += f"- Max (Favorevole, 32 SP): {data['max']}"
            else:
                text += f"- Min (0 SP): {data['min']}\n"
                text += f"- Max (32 SP): {data['max']}"
                
            QMessageBox.information(self, f"Dettagli {data['name']}", text)


    def _filter_moves(self):
        q = self.search_move.text().lower()
        t = self.filter_move_type.currentText()
        c = self.filter_move_cat.currentText()
        for card, mv in self.move_cards:
            match = True
            if q and q not in mv["name"].lower(): match = False
            if t != "Tutti i Tipi" and t != mv["type"]: match = False
            if c != "Tutte" and c != mv["category"]: match = False
            card.setVisible(match)

    def _filter_items(self):
        q = self.search_item.text().lower()
        for card, it in self.item_cards:
            match = True
            if q and q not in it["name"].lower(): match = False
            card.setVisible(match)

    def _open_ability_selection(self):
        self.lbl_ability_title.setText(f"Seleziona Abilità per {self.combo_species.currentText()}")
        
        for i in reversed(range(self.ability_list_layout.count())):
            item = self.ability_list_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
            elif item.spacerItem():
                self.ability_list_layout.removeItem(item)
                
        self.ability_cards.clear()
        
        main_win = self.window()
        if hasattr(main_win, "show_loading"): main_win.show_loading("Caricamento Abilità...")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        
        details = get_legal_abilities_details(self.combo_species.currentText())
        
        if hasattr(main_win, "hide_loading"): main_win.hide_loading()
        
        for ab in details:
            card = QFrame()
            card.setStyleSheet(f"QFrame {{ background-color: {Palette.BG_SURFACE_ELEVATED}; border-radius: 8px; border: 1px solid {Palette.BORDER_COLOR}; }} QFrame:hover {{ border: 1px solid {Palette.PRIMARY}; background-color: #2F333C; }}")
            card_layout = QVBoxLayout(card)
            
            name_lbl = QLabel(ab["name"])
            name_lbl.setStyleSheet("font-size: 16px; font-weight: bold; border: none; background: transparent;")
            card_layout.addWidget(name_lbl)
            
            desc_lbl = QLabel(ab["desc"])
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #aaa; font-size: 12px; border: none; background: transparent;")
            card_layout.addWidget(desc_lbl)
            
            def make_clickable(c, n):
                c.mousePressEvent = lambda e, name=n: self._on_ability_selected(name)
                c.setCursor(Qt.PointingHandCursor)
            make_clickable(card, ab["name"])
            
            self.ability_list_layout.addWidget(card)
            self.ability_cards.append((card, ab))
            
        self.ability_list_layout.addStretch()
        self.right_stack.setCurrentIndex(2)
        
    def _on_ability_selected(self, name: str):
        self.btn_ability.setText(name)
        self.member.ability = name
        self.right_stack.setCurrentIndex(0)

    def _open_item_selection(self):
        self.lbl_item_title.setText("Seleziona Strumento")
        
        for i in reversed(range(self.item_list_layout.count())):
            item = self.item_list_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
            elif item.spacerItem():
                self.item_list_layout.removeItem(item)
                
        self.item_cards.clear()
        
        if not self.cached_all_items:
            main_win = self.window()
            if hasattr(main_win, "show_loading"): main_win.show_loading("Caricamento Strumenti...")
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            self.cached_all_items = get_all_items_details()
            if hasattr(main_win, "hide_loading"): main_win.hide_loading()
            
        for it in self.cached_all_items:
            card = QFrame()
            card.setStyleSheet(f"QFrame {{ background-color: {Palette.BG_SURFACE_ELEVATED}; border-radius: 8px; border: 1px solid {Palette.BORDER_COLOR}; }} QFrame:hover {{ border: 1px solid {Palette.PRIMARY}; background-color: #2F333C; }}")
            card_layout = QVBoxLayout(card)
            
            name_lbl = QLabel(it["name"])
            name_lbl.setStyleSheet("font-size: 16px; font-weight: bold; border: none; background: transparent;")
            card_layout.addWidget(name_lbl)
            
            desc_lbl = QLabel(it["desc"])
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #aaa; font-size: 12px; border: none; background: transparent;")
            card_layout.addWidget(desc_lbl)
            
            def make_clickable(c, n):
                c.mousePressEvent = lambda e, name=n: self._on_item_selected(name)
                c.setCursor(Qt.PointingHandCursor)
            make_clickable(card, it["name"])
            
            self.item_list_layout.addWidget(card)
            self.item_cards.append((card, it))
            
        self.item_list_layout.addStretch()
        self._filter_items() # apply filter immediately
        self.right_stack.setCurrentIndex(3)
        
    def _on_item_selected(self, name: str):
        self.btn_item.setText(name)
        self.member.item = name
        self.right_stack.setCurrentIndex(0)

    def _open_move_selection(self, slot_idx: int):
        self.current_move_slot = slot_idx
        self.lbl_moves_title.setText(f"Seleziona Mossa {slot_idx + 1} per {self.combo_species.currentText()}")
        
        for i in reversed(range(self.moves_list_layout.count())):
            item = self.moves_list_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
            elif item.spacerItem():
                self.moves_list_layout.removeItem(item)
                
        if hasattr(self, 'cached_legal_moves_details') and self.cached_legal_moves_details:
            details = self.cached_legal_moves_details
        else:
            main_win = self.window()
            if hasattr(main_win, "show_loading"): main_win.show_loading("Caricamento Mosse...")
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            details = get_legal_moves_details(self.combo_species.currentText())
            self.cached_legal_moves_details = details
            if hasattr(main_win, "hide_loading"): main_win.hide_loading()

        self.move_cards.clear()
            
        for mv in details:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: {Palette.BG_SURFACE_ELEVATED};
                    border-radius: 8px;
                    border: 1px solid {Palette.BORDER_COLOR};
                }}
                QFrame:hover {{
                    border: 1px solid {Palette.PRIMARY};
                    background-color: #2F333C;
                }}
            """)
            card_layout = QVBoxLayout(card)
            
            header = QHBoxLayout()
            name_lbl = QLabel(mv["name"])
            name_lbl.setStyleSheet("font-size: 16px; font-weight: bold; border: none; background: transparent;")
            
            type_lbl = QLabel(mv["type"])
            type_lbl.setStyleSheet(f"background-color: #555; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px;")
            
            cat_lbl = QLabel(mv["category"])
            cat_lbl.setStyleSheet(f"background-color: #444; color: #ddd; padding: 2px 6px; border-radius: 4px; font-size: 11px;")
            
            header.addWidget(name_lbl)
            header.addWidget(type_lbl)
            header.addWidget(cat_lbl)
            header.addStretch()
            
            stats_lbl = QLabel(f"BP: {mv['basePower']} | Acc: {mv['accuracy']}")
            stats_lbl.setStyleSheet("color: #ccc; font-size: 12px; border: none; background: transparent;")
            header.addWidget(stats_lbl)
            
            card_layout.addLayout(header)
            
            desc_lbl = QLabel(mv["desc"])
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #aaa; font-size: 11px; margin-top: 4px; border: none; background: transparent;")
            card_layout.addWidget(desc_lbl)
            
            tags_layout = QHBoxLayout()
            if mv.get("priority", 0) != 0:
                prio_lbl = QLabel(f"Priority: {mv['priority']:+d}")
                prio_lbl.setStyleSheet("background-color: #C49A3C; color: black; padding: 2px 4px; border-radius: 3px; font-size: 10px; font-weight: bold;")
                tags_layout.addWidget(prio_lbl)
                
            if mv.get("flags", {}).get("contact"):
                cont_lbl = QLabel("Contact")
                cont_lbl.setStyleSheet("background-color: #8A3838; color: white; padding: 2px 4px; border-radius: 3px; font-size: 10px;")
                tags_layout.addWidget(cont_lbl)
                
            if mv.get("boosts"):
                b_text = ", ".join([f"{k} {v:+d}" for k, v in mv["boosts"].items()])
                b_lbl = QLabel(f"Boosts: {b_text}")
                b_lbl.setStyleSheet("background-color: #3D7A5A; color: white; padding: 2px 4px; border-radius: 3px; font-size: 10px;")
                tags_layout.addWidget(b_lbl)
                
            tags_layout.addStretch()
            card_layout.addLayout(tags_layout)
            
            def make_clickable(c, n, d):
                c.mousePressEvent = lambda e: self._on_move_selected(n, d)
                c.setCursor(Qt.PointingHandCursor)
            make_clickable(card, mv["name"], mv)
            
            self.moves_list_layout.addWidget(card)
            self.move_cards.append((card, mv))
            
        self.moves_list_layout.addStretch()
        self._filter_moves()
        self.right_stack.setCurrentIndex(1)
        
    def _on_move_selected(self, move_name: str, move_data: dict):
        self.move_buttons[self.current_move_slot].setText(move_name)
        
        while len(self.member.moves_data) <= self.current_move_slot:
            self.member.moves_data.append({})
        self.member.moves_data[self.current_move_slot] = move_data
        
        self.right_stack.setCurrentIndex(0)
        self._update_calc_buttons()

    def _update_calc_buttons(self):
        for i, btn in enumerate(self.calc_move_btns):
            m = self.move_buttons[i].text()
            if m and m != "Nessuna Mossa":
                btn.setText(f"Calcola: {m}")
                btn.setEnabled(True)
                btn.setStyleSheet(f"background-color: {Palette.SECONDARY}; color: {Palette.BG_APP}; padding: 8px; border-radius: 4px; font-weight: bold;")
            else:
                btn.setText("Slot Vuoto")
                btn.setEnabled(False)
                btn.setStyleSheet(f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT_MUTED}; padding: 8px; border-radius: 4px; border: 1px solid {Palette.BORDER_COLOR};")

    def _run_main_damage_calc(self, move_slot_idx: int):
        move_name = self.move_buttons[move_slot_idx].text()
        if not move_name or move_name == "Nessuna Mossa": return
        
        # Reset selection style
        for i, btn in enumerate(self.calc_move_btns):
            if btn.isEnabled():
                if i == move_slot_idx:
                    btn.setStyleSheet(f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; padding: 8px; border-radius: 4px; font-weight: bold; border: 2px solid white;")
                else:
                    btn.setStyleSheet(f"background-color: {Palette.SECONDARY}; color: {Palette.BG_APP}; padding: 8px; border-radius: 4px; font-weight: bold;")

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._run_damage_calc(move_name)
        except Exception as e:
            QMessageBox.critical(self, "Errore Calcolo Danni", str(e))
        finally:
            QApplication.restoreOverrideCursor()

    def _run_damage_calc(self, move_name: str):
        # 1. Costruisci le options dell'attaccante corrente
        self.save_and_exit(emit_signals=False) # Forza aggiornamento self.member
        attacker_opts = PokemonOptions(
            item=self.member.item,
            nature=self.member.nature,
            evs=self.member.evs,
            ivs=self.member.ivs,
            ability=self.member.ability
        )
        
        # 2. Ottieni Meta Threats
        current_format = self.format_combo.currentText() or "VGC 2024 Reg H"
        meta_threats = BatchGeneratorService.generate_threats_from_format(current_format, 15.0)
        
        # 3. Analisi Singola Mossa
        analyzer = BatchDamageAnalyzer(SmogonDamageCalc())
        results = analyzer.analyze_single_move_vs_meta(self.member.species, attacker_opts, move_name, meta_threats)
        
        # Salva risultati e popola tabella
        self.current_calc_data = results
        self._populate_calc_table()

    def _populate_calc_table(self):
        self.calc_table.setRowCount(0)
        if not self.current_calc_data: return
        
        for row_data in self.current_calc_data:
            row = self.calc_table.rowCount()
            self.calc_table.insertRow(row)
            
            pkm = row_data["name"]
            max_d = row_data["max_def"]
            min_d = row_data["min_def"]
            
            pkm_item = QTableWidgetItem(pkm)
            icon_path = get_pokemon_icon_path(pkm)
            if icon_path and os.path.exists(icon_path):
                pkm_item.setIcon(QIcon(icon_path))
                
            max_item = QTableWidgetItem(f"{max_d:.1f}%")
            max_item.setForeground(QColor("#cc0000" if max_d >= 100 else Palette.TEXT_PRIMARY))
            
            min_item = QTableWidgetItem(f"{min_d:.1f}%")
            min_item.setForeground(QColor("#cc0000" if min_d >= 100 else Palette.TEXT_PRIMARY))
            
            # Nascondi riga per default (sarà il filtro a mostrarla)
            pkm_item.setData(Qt.UserRole, get_species_types(pkm)) # Salva i tipi per il filtro
            
            self.calc_table.setItem(row, 0, pkm_item)
            self.calc_table.setItem(row, 1, max_item)
            self.calc_table.setItem(row, 2, min_item)
            
        self._filter_calc_table()

    def _filter_calc_table(self):
        search_text = self.search_calc_pokemon.text().lower()
        filter_type = self.filter_calc_type.currentText()
        
        for row in range(self.calc_table.rowCount()):
            pkm_item = self.calc_table.item(row, 0)
            if not pkm_item: continue
            
            pkm_name = pkm_item.text()
            pkm_types = pkm_item.data(Qt.UserRole) or []
            
            match_name = search_text in pkm_name.lower()
            match_type = filter_type == "Tutti i Tipi" or filter_type in pkm_types
            
            self.calc_table.setRowHidden(row, not (match_name and match_type))



    def save_and_exit(self, emit_signals=True):
        if not self.member: return
        self.member.species = self.combo_species.currentText()
        self.member.types = get_species_types(self.member.species)
        
        ab_text = self.btn_ability.text()
        self.member.ability = ab_text if ab_text != "Seleziona Abilità" else ""
        
        it_text = self.btn_item.text()
        self.member.item = it_text if it_text != "Seleziona Strumento" else ""
        
        nat_full = self.combo_nature.currentText()
        self.member.nature = self.combo_nature.currentData() or (nat_full.split()[0] if nat_full else "Hardy")
        
        new_moves = []
        for btn in self.move_buttons:
            m = btn.text()
            if m and m != "Nessuna Mossa":
                new_moves.append({"name": m})
        self.member.moves_data = new_moves
        self.member.is_champions_mode = self.btn_champions.isChecked()
        
        for stat in ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]:
            self.member.evs[stat] = self.ev_sliders[stat].value()
            self.member.ivs[stat] = self.iv_spins[stat].value()
            
        if emit_signals:
            self.pokemon_updated.emit()
            self.go_back.emit()
