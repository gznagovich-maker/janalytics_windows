import math
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QMessageBox, QToolTip,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QCompleter, QSlider, QSpinBox,
    QListWidget, QListWidgetItem, QGridLayout, QCheckBox
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtCharts import (
    QChart, QChartView, QStackedBarSeries, QBarSet, QBarCategoryAxis, QValueAxis, QLineSeries
)

from database.connection import SessionLocal
from database.models import Match, Team, PokemonBuild, PokemonSpecies, Item


class MetaStatsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QVBoxLayout(self)
        
        # State tracking
        self.selected_pokemon = None
        self.selected_nature = None
        self.selected_item = None
        self.selected_move = None
        
        self.stat_colors = {
            "hp": "#2ecc71",   # Green
            "atk": "#e74c3c",  # Red
            "def": "#f39c12",  # Orange
            "spa": "#3498db",  # Blue
            "spd": "#9b59b6",  # Purple
            "spe": "#ff9ff3"   # Pink
        }
        
        # Header Controls
        self.controls_layout = QHBoxLayout()
        
        self.format_label = QLabel("Formato:")
        self.format_combo = QComboBox()
        self.format_combo.currentIndexChanged.connect(self.on_format_changed)
        
        self.refresh_btn = QPushButton("Aggiorna Formati")
        self.refresh_btn.clicked.connect(self.load_formats)
        
        self.controls_layout.addWidget(self.format_label)
        self.controls_layout.addWidget(self.format_combo)
        self.controls_layout.addWidget(self.refresh_btn)
        self.controls_layout.addStretch()
        
        self.layout.addLayout(self.controls_layout)
        
        # Tabs
        self.tabs = QTabWidget()
        
        # Tab 1: Statistiche Base (Grafico) + Calcolatore
        self.tab_stats = QWidget()
        self.tab_stats_layout = QHBoxLayout(self.tab_stats)
        
        # Left side: Chart
        self.chart_container = QWidget()
        self.chart_layout = QVBoxLayout(self.chart_container)
        
        stats_controls = QHBoxLayout()
        self.stat_label = QLabel("Statistica nel Grafico:")
        self.stat_combo = QComboBox()
        self.stat_combo.addItems(["Speed", "HP", "Attack", "Defense", "Sp. Atk", "Sp. Def"])
        self.stat_combo.setCurrentText("Speed")
        self.stat_combo.currentIndexChanged.connect(self.update_chart)
        stats_controls.addWidget(self.stat_label)
        stats_controls.addWidget(self.stat_combo)
        stats_controls.addStretch()
        self.chart_layout.addLayout(stats_controls)
        
        self.chart = QChart()
        self.chart.setTitle("Statistiche Meta dei Pokémon (Livello 50)")
        self.chart.setAnimationOptions(QChart.SeriesAnimations)
        
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_layout.addWidget(self.chart_view)
        
        self.tab_stats_layout.addWidget(self.chart_container, stretch=3)
        
        # Right side: Tabs (Simulatore / Filtri & Roster)
        self.right_tabs = QTabWidget()
        
        # Tab Simulatore
        self.calc_container = QWidget()
        self.calc_layout = QVBoxLayout(self.calc_container)
        
        calc_title = QLabel("Simulatore Soglia (Liv. 50)")
        calc_title.setStyleSheet("font-weight: bold; font-size: 16px; margin-bottom: 10px;")
        self.calc_layout.addWidget(calc_title)
        
        # Network Manager for downloading sprites
        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self.on_image_downloaded)
        self.current_pokemon_image_name = None
        
        # Image Label
        self.pokemon_image_label = QLabel()
        self.pokemon_image_label.setFixedSize(120, 120)
        self.pokemon_image_label.setAlignment(Qt.AlignCenter)
        self.calc_layout.addWidget(self.pokemon_image_label, alignment=Qt.AlignCenter)
        
        self.calc_layout.addWidget(QLabel("Pokémon da Testare:"))
        self.calc_pokemon_combo = QComboBox()
        self.calc_pokemon_combo.setEditable(True)
        self.calc_pokemon_combo.setInsertPolicy(QComboBox.NoInsert)
        completer = QCompleter(self)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.calc_pokemon_combo.setCompleter(completer)
        self.calc_pokemon_combo.currentIndexChanged.connect(self.update_threshold)
        self.calc_layout.addWidget(self.calc_pokemon_combo)
        
        self.calc_layout.addWidget(QLabel("Natura:"))
        self.calc_nature_combo = QComboBox()
        self.calc_nature_combo.addItems([
            "Hardy", "Lonely (+Atk, -Def)", "Brave (+Atk, -Spe)", "Adamant (+Atk, -SpA)", "Naughty (+Atk, -SpD)",
            "Bold (+Def, -Atk)", "Docile", "Relaxed (+Def, -Spe)", "Impish (+Def, -SpA)", "Lax (+Def, -SpD)",
            "Timid (+Spe, -Atk)", "Hasty (+Spe, -Def)", "Serious", "Jolly (+Spe, -SpA)", "Naive (+Spe, -SpD)",
            "Modest (+SpA, -Atk)", "Mild (+SpA, -Def)", "Quiet (+SpA, -Spe)", "Bashful", "Rash (+SpA, -SpD)",
            "Calm (+SpD, -Atk)", "Gentle (+SpD, -Def)", "Sassy (+SpD, -Spe)", "Careful (+SpD, -SpA)", "Quirky"
        ])
        self.calc_nature_combo.currentIndexChanged.connect(self.update_threshold)
        self.calc_layout.addWidget(self.calc_nature_combo)
        
        self.ev_remaining_label = QLabel("EVs Rimasti: 508 / 508")
        self.ev_remaining_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #3498db; margin-top: 5px; margin-bottom: 5px;")
        self.calc_layout.addWidget(self.ev_remaining_label)
        
        self.stats_grid = QGridLayout()
        self.calc_layout.addLayout(self.stats_grid)
        
        self.stats_grid.addWidget(QLabel("Stat"), 0, 0)
        self.stats_grid.addWidget(QLabel("Base"), 0, 1)
        self.stats_grid.addWidget(QLabel("IV"), 0, 2)
        self.stats_grid.addWidget(QLabel("EV/SP"), 0, 3, 1, 2)
        self.stats_grid.addWidget(QLabel("Totale"), 0, 5)
        self.stats_grid.addWidget(QLabel("Mostra"), 0, 6)
        
        self.stat_rows = {}
        row_idx = 1
        for stat_name, stat_key in [("HP", "hp"), ("Atk", "atk"), ("Def", "def"), ("SpA", "spa"), ("SpD", "spd"), ("Spe", "spe")]:
            lbl_name = QLabel(stat_name)
            lbl_name.setStyleSheet(f"color: {self.stat_colors[stat_key]}; font-weight: bold;")
            lbl_base = QLabel("0")
            
            spin_iv = QSpinBox()
            spin_iv.setRange(0, 31)
            spin_iv.setValue(31)
            spin_iv.valueChanged.connect(self.update_threshold)
            
            slider_ev = QSlider(Qt.Horizontal)
            slider_ev.setRange(0, 252)
            slider_ev.setSingleStep(4)
            slider_ev.setTickInterval(4)
            
            spin_ev = QSpinBox()
            spin_ev.setRange(0, 252)
            spin_ev.setSingleStep(4)
            
            def make_sync(sl, sp, key):
                def on_sl_change(val):
                    sp.blockSignals(True)
                    sp.setValue(val)
                    sp.blockSignals(False)
                    self.on_ev_changed(key, val)
                def on_sp_change(val):
                    sl.blockSignals(True)
                    sl.setValue(val)
                    sl.blockSignals(False)
                    self.on_ev_changed(key, val)
                return on_sl_change, on_sp_change
                
            on_sl, on_sp = make_sync(slider_ev, spin_ev, stat_key)
            slider_ev.valueChanged.connect(on_sl)
            spin_ev.valueChanged.connect(on_sp)
            
            lbl_total = QLabel("0")
            lbl_total.setStyleSheet("font-weight: bold;")
            
            cb_show = QCheckBox()
            # If the user wants the chart stat to be shown, we could check it initially, but leave unchecked for now
            cb_show.stateChanged.connect(self.update_threshold)
            
            self.stats_grid.addWidget(lbl_name, row_idx, 0)
            self.stats_grid.addWidget(lbl_base, row_idx, 1)
            self.stats_grid.addWidget(spin_iv, row_idx, 2)
            self.stats_grid.addWidget(slider_ev, row_idx, 3)
            self.stats_grid.addWidget(spin_ev, row_idx, 4)
            self.stats_grid.addWidget(lbl_total, row_idx, 5)
            self.stats_grid.addWidget(cb_show, row_idx, 6)
            
            self.stat_rows[stat_key] = {
                "base": lbl_base,
                "iv": spin_iv,
                "slider": slider_ev,
                "spin": spin_ev,
                "total": lbl_total,
                "check": cb_show
            }
            row_idx += 1
            
        self.btn_champions_mode = QPushButton("Modalità Champions")
        self.btn_champions_mode.setCheckable(True)
        self.btn_champions_mode.setStyleSheet("background-color: #333333; color: white; font-weight: bold; padding: 5px; margin-top: 10px;")
        self.btn_champions_mode.clicked.connect(self.set_champions_mode)
        self.calc_layout.addWidget(self.btn_champions_mode)
        
        self.calc_layout.addStretch()
        self.right_tabs.addTab(self.calc_container, "Simulatore")
        
        # Tab Filtri & Roster
        self.roster_container = QWidget()
        self.roster_layout = QVBoxLayout(self.roster_container)
        
        roster_title = QLabel("Roster & Filtri Meta")
        roster_title.setStyleSheet("font-weight: bold; font-size: 16px; margin-bottom: 10px;")
        self.roster_layout.addWidget(roster_title)
        
        self.btn_elimina_sotto = QPushButton("Elimina Pokémon Sotto Soglia")
        self.btn_elimina_sotto.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; padding: 5px;")
        self.btn_elimina_sotto.clicked.connect(self.elimina_sotto_soglia)
        self.roster_layout.addWidget(self.btn_elimina_sotto)
        
        type_layout = QHBoxLayout()
        self.filter_type_1 = QComboBox()
        self.filter_type_1.addItem("Tutti i tipi")
        self.filter_type_2 = QComboBox()
        self.filter_type_2.addItem("Tutti i tipi")
        
        pokemon_types = ["Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"]
        self.filter_type_1.addItems(pokemon_types)
        self.filter_type_2.addItems(pokemon_types)
        
        self.filter_type_1.currentIndexChanged.connect(self.apply_roster_filters)
        self.filter_type_2.currentIndexChanged.connect(self.apply_roster_filters)
        
        type_layout.addWidget(QLabel("Tipo 1:"))
        type_layout.addWidget(self.filter_type_1)
        type_layout.addWidget(QLabel("Tipo 2:"))
        type_layout.addWidget(self.filter_type_2)
        self.roster_layout.addLayout(type_layout)
        
        usage_layout = QHBoxLayout()
        self.filter_usage = QSlider(Qt.Horizontal)
        self.filter_usage.setRange(0, 100)
        self.filter_usage.setValue(0)
        self.filter_usage.valueChanged.connect(self.apply_roster_filters)
        self.usage_label_value = QLabel("≥ 0")
        usage_layout.addWidget(QLabel("Uso Minimo (Count):"))
        usage_layout.addWidget(self.filter_usage)
        usage_layout.addWidget(self.usage_label_value)
        self.roster_layout.addLayout(usage_layout)
        
        self.roster_list = QListWidget()
        self.roster_list.itemChanged.connect(self.on_roster_item_changed)
        self.roster_layout.addWidget(self.roster_list)
        
        self.right_tabs.addTab(self.roster_container, "Roster & Filtri")
        
        self.tab_stats_layout.addWidget(self.right_tabs, stretch=1)
        
        # Tab 2: Usage, Win Rate & Nature
        self.tab_usage = QWidget()
        self.tab_usage_layout = QHBoxLayout(self.tab_usage)
        
        # Left side: Usage Table
        self.usage_table = QTableWidget()
        self.usage_table.setColumnCount(4)
        self.usage_table.setHorizontalHeaderLabels(["Pokémon", "Usage (Count)", "Win Rate (%)", "Index (Ratio)"])
        self.usage_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.usage_table.setSortingEnabled(True)
        self.usage_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.usage_table.setSelectionMode(QTableWidget.SingleSelection)
        self.usage_table.itemSelectionChanged.connect(self.on_usage_selection_changed)
        self.tab_usage_layout.addWidget(self.usage_table, stretch=2)
        
        # Right side: Nature, Item, Moves Tables
        right_layout = QVBoxLayout()
        
        self.nature_label = QLabel("Distribuzione Nature")
        self.nature_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(self.nature_label)
        
        self.nature_table = QTableWidget()
        self.nature_table.setColumnCount(2)
        self.nature_table.setHorizontalHeaderLabels(["Natura", "Percentuale (%)"])
        self.nature_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.nature_table.setSortingEnabled(True)
        self.nature_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.nature_table.setSelectionMode(QTableWidget.SingleSelection)
        self.nature_table.itemSelectionChanged.connect(self.on_nature_selection_changed)
        right_layout.addWidget(self.nature_table)
        
        self.item_label = QLabel("Distribuzione Strumenti")
        self.item_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(self.item_label)
        
        self.item_table = QTableWidget()
        self.item_table.setColumnCount(2)
        self.item_table.setHorizontalHeaderLabels(["Strumento", "Percentuale (%)"])
        self.item_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.item_table.setSortingEnabled(True)
        self.item_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.item_table.setSelectionMode(QTableWidget.SingleSelection)
        self.item_table.itemSelectionChanged.connect(self.on_item_selection_changed)
        right_layout.addWidget(self.item_table)
        
        self.moves_label = QLabel("Distribuzione Mosse")
        self.moves_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(self.moves_label)
        
        self.moves_table = QTableWidget()
        self.moves_table.setColumnCount(2)
        self.moves_table.setHorizontalHeaderLabels(["Mossa", "Percentuale (%)"])
        self.moves_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.moves_table.setSortingEnabled(True)
        self.moves_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.moves_table.setSelectionMode(QTableWidget.SingleSelection)
        self.moves_table.itemSelectionChanged.connect(self.on_move_selection_changed)
        right_layout.addWidget(self.moves_table)
        
        self.tab_usage_layout.addLayout(right_layout, stretch=1)
        
        self.tabs.addTab(self.tab_stats, "Distribuzione Statistiche")
        self.tabs.addTab(self.tab_usage, "Usage, Win Rate & Build")
        
        self.layout.addWidget(self.tabs)
        
        # Internal mapping
        self.stat_key_map = {
            "Speed": "spe",
            "HP": "hp",
            "Attack": "atk",
            "Defense": "def",
            "Sp. Atk": "spa",
            "Sp. Def": "spd"
        }
        
        self.tooltip_data = []
        self.current_format_builds = []
        self.last_categories = []
        self.builds_usage = {}
        self.total_builds = 0
        self.current_threshold_val = 0
        
        self.nature_modifiers = {
            "Adamant": {"plus": "atk", "minus": "spa"},
            "Jolly": {"plus": "spe", "minus": "spa"},
            "Timid": {"plus": "spe", "minus": "atk"},
            "Modest": {"plus": "spa", "minus": "atk"},
            "Quiet": {"plus": "spa", "minus": "spe"},
            "Brave": {"plus": "atk", "minus": "spe"},
            "Bold": {"plus": "def", "minus": "atk"},
            "Impish": {"plus": "def", "minus": "spa"},
            "Relaxed": {"plus": "def", "minus": "spe"},
            "Calm": {"plus": "spd", "minus": "atk"},
            "Careful": {"plus": "spd", "minus": "spa"},
            "Sassy": {"plus": "spd", "minus": "spe"},
        }
        
        self.load_formats()
        
    def load_formats(self):
        session = SessionLocal()
        try:
            formats = session.query(Match.format).distinct().all()
            self.format_combo.blockSignals(True)
            self.format_combo.clear()
            for (f,) in formats:
                if f:
                    self.format_combo.addItem(f)
            self.format_combo.blockSignals(False)
            
            all_species = session.query(PokemonSpecies).order_by(PokemonSpecies.name).all()
            self.calc_pokemon_combo.blockSignals(True)
            self.calc_pokemon_combo.clear()
            for sp in all_species:
                self.calc_pokemon_combo.addItem(sp.name, sp.base_stats)
            self.calc_pokemon_combo.completer().setModel(self.calc_pokemon_combo.model())
            self.calc_pokemon_combo.blockSignals(False)
            
            if self.format_combo.count() > 0:
                self.on_format_changed()
        except Exception as e:
            QMessageBox.warning(self, "Errore", f"Impossibile caricare i formati: {e}")
        finally:
            session.close()
            
    def on_format_changed(self):
        fmt = self.format_combo.currentText()
        if not fmt:
            return
            
        session = SessionLocal()
        try:
            builds = session.query(
                PokemonSpecies.name,
                Team.trainer_id,
                Match.winner_id,
                PokemonBuild.nature,
                PokemonBuild.item_id,
                PokemonBuild.moves
            ).join(PokemonBuild.team)\
             .join(Team.match)\
             .join(PokemonSpecies, PokemonBuild.species_id == PokemonSpecies.id)\
             .filter(Match.format == fmt).all()
            self.current_format_builds = builds
            
            self.builds_usage = {}
            for name, trainer_id, winner_id, nature, item_name, moves in builds:
                self.builds_usage[name] = self.builds_usage.get(name, 0) + 1
            self.total_builds = len(builds)
            
            max_usage = max(self.builds_usage.values()) if self.builds_usage else 0
            self.filter_usage.blockSignals(True)
            self.filter_usage.setRange(0, max_usage)
            self.filter_usage.setValue(0)
            self.usage_label_value.setText("≥ 0")
            self.filter_usage.blockSignals(False)
            
            # Popola Roster
            species_ids = set([s[0] for s in session.query(PokemonBuild.species_id)\
                .join(Team, PokemonBuild.team_id == Team.id)\
                .join(Match, Team.match_id == Match.id)\
                .filter(Match.format == fmt).all() if s[0]])
            
            species_list = session.query(PokemonSpecies).filter(PokemonSpecies.id.in_(species_ids)).order_by(PokemonSpecies.name).all()
            
            self.roster_list.blockSignals(True)
            self.roster_list.clear()
            for sp in species_list:
                item = QListWidgetItem(sp.name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                item.setData(Qt.UserRole, sp)
                self.roster_list.addItem(item)
            self.roster_list.blockSignals(False)
            
            self.selected_pokemon = None
            self.selected_nature = None
            self.selected_item = None
            self.selected_move = None
            
            self.update_chart()
            self.update_usage_table()
            self.update_nature_table()
            self.update_item_table()
            self.update_moves_table()
            
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore durante l'aggiornamento dati: {e}")
        finally:
            session.close()

    def update_usage_table(self):
        self.usage_table.blockSignals(True)
        self.usage_table.setSortingEnabled(False)
        self.usage_table.setRowCount(0)
        
        if not self.current_format_builds:
            self.usage_table.setSortingEnabled(True)
            self.usage_table.blockSignals(False)
            return
            
        stats = {}
        for name, trainer_id, winner_id, nature, item_name, moves in self.current_format_builds:
            if name not in stats:
                stats[name] = {"usage": 0, "wins": 0}
            stats[name]["usage"] += 1
            if trainer_id == winner_id and winner_id is not None:
                stats[name]["wins"] += 1
                
        self.usage_table.setRowCount(len(stats))
        
        for row, (name, data) in enumerate(stats.items()):
            usage = data["usage"]
            wins = data["wins"]
            win_rate = (wins / usage * 100) if usage > 0 else 0
            ratio = usage * (win_rate / 100.0) 
            
            item_name_widget = QTableWidgetItem(name)
            item_usage = QTableWidgetItem()
            item_usage.setData(Qt.EditRole, usage)
            
            item_wr = QTableWidgetItem()
            item_wr.setData(Qt.EditRole, float(f"{win_rate:.2f}"))
            
            item_ratio = QTableWidgetItem()
            item_ratio.setData(Qt.EditRole, float(f"{ratio:.2f}"))
            
            self.usage_table.setItem(row, 0, item_name_widget)
            self.usage_table.setItem(row, 1, item_usage)
            self.usage_table.setItem(row, 2, item_wr)
            self.usage_table.setItem(row, 3, item_ratio)
            
        self.usage_table.setSortingEnabled(True)
        self.usage_table.sortItems(1, Qt.DescendingOrder) 
        self.usage_table.blockSignals(False)
        
    def on_usage_selection_changed(self):
        selected_items = self.usage_table.selectedItems()
        if not selected_items:
            self.selected_pokemon = None
        else:
            row = selected_items[0].row()
            self.selected_pokemon = self.usage_table.item(row, 0).text()
            
        self.selected_nature = None
        self.selected_item = None
        self.selected_move = None
        
        self.nature_table.blockSignals(True)
        self.nature_table.clearSelection()
        self.nature_table.blockSignals(False)
        
        self.item_table.blockSignals(True)
        self.item_table.clearSelection()
        self.item_table.blockSignals(False)

        self.moves_table.blockSignals(True)
        self.moves_table.clearSelection()
        self.moves_table.blockSignals(False)
        
        self.update_nature_table()
        self.update_item_table()
        self.update_moves_table()

    def on_nature_selection_changed(self):
        selected_items = self.nature_table.selectedItems()
        if not selected_items:
            if self.selected_nature is not None:
                self.selected_nature = None
                self.update_item_table()
                self.update_moves_table()
            return
            
        row = selected_items[0].row()
        nature = self.nature_table.item(row, 0).text()
        
        if self.selected_nature != nature:
            self.selected_nature = nature
            
            self.item_table.blockSignals(True)
            self.item_table.clearSelection()
            self.selected_item = None
            self.item_table.blockSignals(False)
            
            self.moves_table.blockSignals(True)
            self.moves_table.clearSelection()
            self.selected_move = None
            self.moves_table.blockSignals(False)
            
            self.update_item_table()
            self.update_moves_table()

    def on_item_selection_changed(self):
        selected_items = self.item_table.selectedItems()
        if not selected_items:
            if self.selected_item is not None:
                self.selected_item = None
                self.update_nature_table()
                self.update_moves_table()
            return
            
        row = selected_items[0].row()
        item = self.item_table.item(row, 0).text()
        
        if self.selected_item != item:
            self.selected_item = item
            
            self.nature_table.blockSignals(True)
            self.nature_table.clearSelection()
            self.selected_nature = None
            self.nature_table.blockSignals(False)
            
            self.moves_table.blockSignals(True)
            self.moves_table.clearSelection()
            self.selected_move = None
            self.moves_table.blockSignals(False)
            
            self.update_nature_table()
            self.update_moves_table()

    def on_move_selection_changed(self):
        selected_items = self.moves_table.selectedItems()
        if not selected_items:
            if self.selected_move is not None:
                self.selected_move = None
                self.update_nature_table()
                self.update_item_table()
            return
            
        row = selected_items[0].row()
        move = self.moves_table.item(row, 0).text()
        
        if self.selected_move != move:
            self.selected_move = move
            
            self.nature_table.blockSignals(True)
            self.nature_table.clearSelection()
            self.selected_nature = None
            self.nature_table.blockSignals(False)
            
            self.item_table.blockSignals(True)
            self.item_table.clearSelection()
            self.selected_item = None
            self.item_table.blockSignals(False)
            
            self.update_nature_table()
            self.update_item_table()

    def update_nature_table(self):
        self.nature_table.blockSignals(True)
        self.nature_table.setSortingEnabled(False)
        self.nature_table.setRowCount(0)
        
        if not self.selected_pokemon or not self.current_format_builds:
            self.nature_label.setText("Distribuzione Nature")
            self.nature_table.setSortingEnabled(True)
            self.nature_table.blockSignals(False)
            return
            
        filters_str = []
        if self.selected_item: filters_str.append(f"Strum: {self.selected_item}")
        if self.selected_move: filters_str.append(f"Mossa: {self.selected_move}")
        
        if filters_str:
            self.nature_label.setText(f"Nature per {self.selected_pokemon} ({', '.join(filters_str)})")
        else:
            self.nature_label.setText(f"Distribuzione Nature per: {self.selected_pokemon}")
            
        natures_count = {}
        total = 0
        
        for name, trainer_id, winner_id, nature, item_name, moves in self.current_format_builds:
            if name == self.selected_pokemon:
                itm = item_name if item_name else "Nessuno"
                mov_list = moves.split(',') if moves else []
                
                if self.selected_item and itm != self.selected_item:
                    continue
                if self.selected_move and self.selected_move not in mov_list:
                    continue
                    
                total += 1
                nat = nature if nature else "Sconosciuta"
                natures_count[nat] = natures_count.get(nat, 0) + 1
                
        self.nature_table.setRowCount(len(natures_count))
        row = 0
        for nat, count in natures_count.items():
            pct = (count / total * 100) if total > 0 else 0
            item_nat = QTableWidgetItem(nat)
            item_pct = QTableWidgetItem()
            item_pct.setData(Qt.EditRole, float(f"{pct:.2f}"))
            
            self.nature_table.setItem(row, 0, item_nat)
            self.nature_table.setItem(row, 1, item_pct)
            row += 1
            
        self.nature_table.setSortingEnabled(True)
        self.nature_table.sortItems(1, Qt.DescendingOrder)
        
        if self.selected_nature:
            for i in range(self.nature_table.rowCount()):
                if self.nature_table.item(i, 0).text() == self.selected_nature:
                    self.nature_table.selectRow(i)
                    break
        self.nature_table.blockSignals(False)

    def update_item_table(self):
        self.item_table.blockSignals(True)
        self.item_table.setSortingEnabled(False)
        self.item_table.setRowCount(0)
        
        if not self.selected_pokemon or not self.current_format_builds:
            self.item_label.setText("Distribuzione Strumenti")
            self.item_table.setSortingEnabled(True)
            self.item_table.blockSignals(False)
            return
            
        filters_str = []
        if self.selected_nature: filters_str.append(f"Nat: {self.selected_nature}")
        if self.selected_move: filters_str.append(f"Mossa: {self.selected_move}")
        
        if filters_str:
            self.item_label.setText(f"Strumenti per {self.selected_pokemon} ({', '.join(filters_str)})")
        else:
            self.item_label.setText(f"Distribuzione Strumenti per: {self.selected_pokemon}")
            
        items_count = {}
        total = 0
        
        for name, trainer_id, winner_id, nature, item_name, moves in self.current_format_builds:
            if name == self.selected_pokemon:
                nat = nature if nature else "Sconosciuta"
                mov_list = moves.split(',') if moves else []
                
                if self.selected_nature and nat != self.selected_nature:
                    continue
                if self.selected_move and self.selected_move not in mov_list:
                    continue
                    
                total += 1
                itm = item_name if item_name else "Nessuno"
                items_count[itm] = items_count.get(itm, 0) + 1
                
        self.item_table.setRowCount(len(items_count))
        row = 0
        for itm, count in items_count.items():
            pct = (count / total * 100) if total > 0 else 0
            w_itm = QTableWidgetItem(itm)
            w_pct = QTableWidgetItem()
            w_pct.setData(Qt.EditRole, float(f"{pct:.2f}"))
            
            self.item_table.setItem(row, 0, w_itm)
            self.item_table.setItem(row, 1, w_pct)
            row += 1
            
        self.item_table.setSortingEnabled(True)
        self.item_table.sortItems(1, Qt.DescendingOrder)
        
        if self.selected_item:
            for i in range(self.item_table.rowCount()):
                if self.item_table.item(i, 0).text() == self.selected_item:
                    self.item_table.selectRow(i)
                    break
        self.item_table.blockSignals(False)

    def update_moves_table(self):
        self.moves_table.blockSignals(True)
        self.moves_table.setSortingEnabled(False)
        self.moves_table.setRowCount(0)
        
        if not self.selected_pokemon or not self.current_format_builds:
            self.moves_label.setText("Distribuzione Mosse")
            self.moves_table.setSortingEnabled(True)
            self.moves_table.blockSignals(False)
            return
            
        filters_str = []
        if self.selected_nature: filters_str.append(f"Nat: {self.selected_nature}")
        if self.selected_item: filters_str.append(f"Strum: {self.selected_item}")
        
        if filters_str:
            self.moves_label.setText(f"Mosse per {self.selected_pokemon} ({', '.join(filters_str)})")
        else:
            self.moves_label.setText(f"Distribuzione Mosse per: {self.selected_pokemon}")
            
        moves_count = {}
        total = 0
        
        for name, trainer_id, winner_id, nature, item_name, moves in self.current_format_builds:
            if name == self.selected_pokemon:
                nat = nature if nature else "Sconosciuta"
                itm = item_name if item_name else "Nessuno"
                
                if self.selected_nature and nat != self.selected_nature:
                    continue
                if self.selected_item and itm != self.selected_item:
                    continue
                    
                total += 1
                if moves:
                    for mv in moves.split(','):
                        mv = mv.strip()
                        if mv:
                            moves_count[mv] = moves_count.get(mv, 0) + 1
                
        self.moves_table.setRowCount(len(moves_count))
        row = 0
        for mv, count in moves_count.items():
            pct = (count / total * 100) if total > 0 else 0
            w_mv = QTableWidgetItem(mv)
            w_pct = QTableWidgetItem()
            w_pct.setData(Qt.EditRole, float(f"{pct:.2f}"))
            
            self.moves_table.setItem(row, 0, w_mv)
            self.moves_table.setItem(row, 1, w_pct)
            row += 1
            
        self.moves_table.setSortingEnabled(True)
        self.moves_table.sortItems(1, Qt.DescendingOrder)
        
        if self.selected_move:
            for i in range(self.moves_table.rowCount()):
                if self.moves_table.item(i, 0).text() == self.selected_move:
                    self.moves_table.selectRow(i)
                    break
        self.moves_table.blockSignals(False)

    def update_chart(self):
        fmt = self.format_combo.currentText()
        if not fmt:
            return
            
        stat_display = self.stat_combo.currentText()
        stat_key = self.stat_key_map[stat_display]
        is_hp = (stat_key == "hp")
        
        session = SessionLocal()
        try:
            if self.roster_list.count() == 0:
                self.chart.removeAllSeries()
                self.chart.setTitle(f"Nessun Pokémon trovato per {fmt}")
                return
                
            species_list = []
            for i in range(self.roster_list.count()):
                item = self.roster_list.item(i)
                if item.checkState() == Qt.Checked:
                    species_list.append(item.data(Qt.UserRole))
            
            if not species_list:
                self.chart.removeAllSeries()
                self.chart.setTitle(f"Nessun Pokémon filtrato in {fmt}")
                return
            
            categories = []
            self.tooltip_data.clear()
            
            set_transparent = QBarSet("Trasparente")
            set_transparent.setColor(QColor(0, 0, 0, 0)) 
            set_transparent.setBorderColor(QColor(0, 0, 0, 0))
            
            set_blue = QBarSet("Minima -> Neutra (0 EVs)")
            set_blue.setColor(QColor("#3498db")) 
            
            set_green = QBarSet("Neutra (0 EVs) -> Neutra (Max EVs)")
            set_green.setColor(QColor("#2ecc71")) 
            
            set_yellow = QBarSet("Neutra (Max EVs) -> Favorevole (Max EVs)")
            set_yellow.setColor(QColor("#f1c40f")) 
            
            species_list.sort(key=lambda x: x.base_stats.get(stat_key, 0))
            
            max_y_value = 0
            
            for pkmn in species_list:
                base = pkmn.base_stats.get(stat_key, 0)
                categories.append(pkmn.name)
                
                if is_hp:
                    min_val = base + 75
                    max_val = base + 107
                    
                    self.tooltip_data.append({
                        "name": pkmn.name,
                        "min": min_val,
                        "max": max_val
                    })
                    
                    set_transparent.append(min_val)
                    set_blue.append(max_val - min_val)
                    set_green.append(0)
                    set_yellow.append(0)
                    
                    if max_val > max_y_value:
                        max_y_value = max_val
                else:
                    val_min = math.floor((base + 20) * 0.9)
                    val_quasi_min = base + 20
                    val_quasi_max = base + 52
                    val_max = math.floor((base + 52) * 1.1)
                    
                    self.tooltip_data.append({
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
                    
                    if val_max > max_y_value:
                        max_y_value = val_max
                        
            series = QStackedBarSeries()
            series.append(set_transparent)
            series.append(set_blue)
            if not is_hp:
                series.append(set_green)
                series.append(set_yellow)
                
            series.hovered.connect(self.on_bar_hovered)
            series.clicked.connect(self.on_bar_clicked)
                
            self.chart.removeAllSeries()
            
            for axis in self.chart.axes():
                self.chart.removeAxis(axis)
                
            self.chart.addSeries(series)
            self.chart.setTitle(f"Distribuzione {stat_display} nel formato: {fmt}")
            
            axisX = QBarCategoryAxis()
            axisX.append(categories)
            if len(categories) > 15:
                axisX.setLabelsAngle(-90)
            
            self.chart.addAxis(axisX, Qt.AlignBottom)
            series.attachAxis(axisX)
            
            axisY = QValueAxis()
            axisY.setRange(0, max_y_value * 1.1)
            self.chart.addAxis(axisY, Qt.AlignLeft)
            series.attachAxis(axisY)
            
            for marker in self.chart.legend().markers():
                if marker.barset() == set_transparent:
                    marker.setVisible(False)
                    
            self.last_categories = categories
            self.update_threshold()
            
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore durante l'aggiornamento del grafico: {e}")
        finally:
            session.close()

    def on_bar_hovered(self, status, index, barset):
        if status and index >= 0 and index < len(self.tooltip_data):
            data = self.tooltip_data[index]
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

    def on_bar_clicked(self, index, barset):
        if index >= 0 and index < len(self.tooltip_data):
            data = self.tooltip_data[index]
            text = f"Valori statistici per {data['name']}:\n\n"
            if 'quasi_min' in data:
                text += f"- Min (Sfavorevole, 0 SP): {data['min']}\n"
                text += f"- Quasi-Min (Neutra, 0 SP): {data['quasi_min']}\n"
                text += f"- Quasi-Max (Neutra, 32 SP): {data['quasi_max']}\n"
                text += f"- Max (Favorevole, 32 SP): {data['max']}"
            else:
                text += f"- Min (0 SP): {data['min']}\n"
                text += f"- Max (32 SP): {data['max']}"
                
            QMessageBox.information(self, f"Dettagli: {data['name']}", text)

    def on_ev_changed(self, changed_key, new_val):
        is_sp_mode = self.btn_champions_mode.isChecked()
        
        total_other_evs = 0
        for k, widgets in self.stat_rows.items():
            if k != changed_key:
                val = widgets["spin"].value()
                if is_sp_mode:
                    total_other_evs += ((val * 8) - 4) if val > 0 else 0
                else:
                    total_other_evs += val
                    
        max_available_ev = 508 - total_other_evs
        
        if is_sp_mode:
            new_ev_cost = ((new_val * 8) - 4) if new_val > 0 else 0
        else:
            new_ev_cost = new_val
            
        if new_ev_cost > max_available_ev:
            if is_sp_mode:
                if max_available_ev < 4:
                    allowed_val = 0
                else:
                    allowed_val = (max_available_ev + 4) // 8
            else:
                allowed_val = max_available_ev
                
            widgets = self.stat_rows[changed_key]
            widgets["spin"].blockSignals(True)
            widgets["slider"].blockSignals(True)
            widgets["spin"].setValue(allowed_val)
            widgets["slider"].setValue(allowed_val)
            widgets["spin"].blockSignals(False)
            widgets["slider"].blockSignals(False)
            
        total_evs = 0
        for k, widgets in self.stat_rows.items():
            val = widgets["spin"].value()
            if is_sp_mode:
                total_evs += ((val * 8) - 4) if val > 0 else 0
            else:
                total_evs += val
                
        rem_ev = 508 - total_evs
        self.ev_remaining_label.setText(f"EVs Rimasti: {rem_ev} / 508")
        self.update_threshold()

    def set_champions_mode(self):
        is_checked = self.btn_champions_mode.isChecked()
        if is_checked:
            self.btn_champions_mode.setStyleSheet("background-color: white; color: black; font-weight: bold; padding: 5px; margin-top: 10px;")
            for k, widgets in self.stat_rows.items():
                widgets["spin"].blockSignals(True)
                widgets["slider"].blockSignals(True)
                widgets["spin"].setRange(0, 32)
                widgets["slider"].setRange(0, 32)
                widgets["spin"].setSingleStep(1)
                widgets["slider"].setSingleStep(1)
                widgets["slider"].setTickInterval(1)
                widgets["spin"].setValue(0)
                widgets["slider"].setValue(0)
                widgets["spin"].blockSignals(False)
                widgets["slider"].blockSignals(False)
                
            self.ev_remaining_label.setText("EVs Rimasti: 508 / 508")
        else:
            self.btn_champions_mode.setStyleSheet("background-color: #333333; color: white; font-weight: bold; padding: 5px; margin-top: 10px;")
            for k, widgets in self.stat_rows.items():
                widgets["spin"].blockSignals(True)
                widgets["slider"].blockSignals(True)
                widgets["spin"].setRange(0, 252)
                widgets["slider"].setRange(0, 252)
                widgets["spin"].setSingleStep(4)
                widgets["slider"].setSingleStep(4)
                widgets["slider"].setTickInterval(4)
                widgets["spin"].setValue(0)
                widgets["slider"].setValue(0)
                widgets["spin"].blockSignals(False)
                widgets["slider"].blockSignals(False)
            
            self.ev_remaining_label.setText("EVs Rimasti: 508 / 508")
            
        self.update_threshold()

    def on_image_downloaded(self, reply):
        if reply.error() == reply.NetworkError.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            self.pokemon_image_label.setPixmap(pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        reply.deleteLater()

    def update_threshold(self):
        if self.calc_pokemon_combo.count() == 0:
            return
            
        pokemon_name = self.calc_pokemon_combo.currentText()
        if self.calc_pokemon_combo.findText(pokemon_name) != -1:
            if self.current_pokemon_image_name != pokemon_name:
                self.current_pokemon_image_name = pokemon_name
                clean_name = pokemon_name.lower().replace(" ", "").replace("-", "").replace("'", "").replace(".", "")
                url = QUrl(f"https://play.pokemonshowdown.com/sprites/gen5/{clean_name}.png")
                request = QNetworkRequest(url)
                self.network_manager.get(request)
                
        base_stats = self.calc_pokemon_combo.currentData()
        if not base_stats:
            # If the user typed an incomplete name, currentData() might be None
            return
        nature_text = self.calc_nature_combo.currentText().split(' ')[0]
        is_sp_mode = self.btn_champions_mode.isChecked()
        level = 50
        
        calculated_stats = {}
        
        for k, widgets in self.stat_rows.items():
            base = base_stats.get(k, 0)
            widgets["base"].setText(str(base))
            
            ev_val = widgets["spin"].value()
            iv = widgets["iv"].value()
            
            if is_sp_mode:
                ev = (ev_val * 8) - 4 if ev_val > 0 else 0
            else:
                ev = ev_val
                
            if k == "hp":
                stat_val = math.floor((2 * base + iv + math.floor(ev / 4)) * level / 100) + level + 10
            else:
                raw_stat = math.floor((2 * base + iv + math.floor(ev / 4)) * level / 100) + 5
                modifier = 1.0
                
                if nature_text in self.nature_modifiers:
                    mods = self.nature_modifiers[nature_text]
                    if mods["plus"] == k:
                        modifier = 1.1
                    elif mods["minus"] == k:
                        modifier = 0.9
                        
                stat_val = math.floor(raw_stat * modifier)
                
            widgets["total"].setText(str(stat_val))
            calculated_stats[k] = stat_val
            
        chart_stat_display = self.stat_combo.currentText()
        chart_stat_key = self.stat_key_map[chart_stat_display]
        target_val = calculated_stats.get(chart_stat_key, 0)
        
        # current_threshold_val is used by "Elimina Sotto Soglia"
        self.current_threshold_val = target_val
        
        lines_to_draw = {}
        for k, widgets in self.stat_rows.items():
            if widgets["check"].isChecked():
                lines_to_draw[k] = calculated_stats.get(k, 0)
                
        self.draw_threshold_lines(lines_to_draw)

    def on_roster_item_changed(self, item):
        self.update_chart()

    def apply_roster_filters(self):
        t1 = self.filter_type_1.currentText()
        t2 = self.filter_type_2.currentText()
        usage_thresh = self.filter_usage.value()
        self.usage_label_value.setText(f"≥ {usage_thresh}")
        
        self.roster_list.blockSignals(True)
        for i in range(self.roster_list.count()):
            item = self.roster_list.item(i)
            sp = item.data(Qt.UserRole)
            
            usage_count = self.builds_usage.get(sp.name, 0)
            
            types = sp.types if sp.types else []
            match_t1 = (t1 == "Tutti i tipi") or (t1 in types)
            match_t2 = (t2 == "Tutti i tipi") or (t2 in types)
            
            if usage_count >= usage_thresh and match_t1 and match_t2:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
                
        self.roster_list.blockSignals(False)
        self.update_chart()

    def elimina_sotto_soglia(self):
        if not hasattr(self, 'current_threshold_val'):
            return
            
        threshold = self.current_threshold_val
        stat_display = self.stat_combo.currentText()
        stat_key = self.stat_key_map[stat_display]
        is_hp = (stat_key == "hp")
        
        self.roster_list.blockSignals(True)
        for i in range(self.roster_list.count()):
            item = self.roster_list.item(i)
            if item.checkState() == Qt.Checked:
                sp = item.data(Qt.UserRole)
                base = sp.base_stats.get(stat_key, 0)
                
                if is_hp:
                    max_stat = math.floor((2 * base + 31 + math.floor(252 / 4)) * 50 / 100) + 50 + 10
                else:
                    raw_stat = math.floor((2 * base + 31 + math.floor(252 / 4)) * 50 / 100) + 5
                    max_stat = math.floor(raw_stat * 1.1)
                    
                if max_stat < threshold:
                    item.setCheckState(Qt.Unchecked)
                    
        self.roster_list.blockSignals(False)
        self.update_chart()

    def draw_threshold_lines(self, lines_dict):
        if not hasattr(self, 'threshold_series_dict'):
            self.threshold_series_dict = {}
            
        for series in self.threshold_series_dict.values():
            if series in self.chart.series():
                self.chart.removeSeries(series)
                
        self.threshold_series_dict.clear()
        
        cat_len = len(getattr(self, 'last_categories', []))
        if cat_len == 0:
            return
            
        for stat_key, val in lines_dict.items():
            series = QLineSeries()
            series.setName(f"Tua {stat_key.upper()}")
            pen = series.pen()
            pen.setColor(QColor(self.stat_colors.get(stat_key, "#ffffff")))
            pen.setWidth(3)
            series.setPen(pen)
            
            series.append(-0.5, val)
            series.append(cat_len - 0.5, val)
            
            self.chart.addSeries(series)
            
            for axis in self.chart.axes():
                series.attachAxis(axis)
                
            self.threshold_series_dict[stat_key] = series
