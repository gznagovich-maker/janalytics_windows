from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QProgressBar, QMessageBox, QDialog, QSpinBox,
    QGraphicsDropShadowEffect, QFrame
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor
from domain.limitless_scraper import MultiTournamentWorker, TournamentDetailWorker, LimitlessFormatsWorker

from database.connection import SessionLocal
from sqlalchemy.orm import joinedload
from sqlalchemy import select
from collections import defaultdict
from database.models import Match, Team, PokemonBuild, Turn, TurnAction
from domain.limitless_scraper import normalize_limitless_pokemon, build_replay_core_dict
from views.ui_utils import LoadingOverlay



def create_pokemon_build_widget(pkmn_name, pkmn_usage, build_data) -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    
    header = QLabel(f"Statistiche {pkmn_name} (Analizzati {pkmn_usage} set)")
    header.setStyleSheet("font-size: 16px; font-weight: bold;")
    layout.addWidget(header)
    
    tabs = QTabWidget()
    
    def create_stats_table(data_dict, headers=["Elemento", "Utilizzo", "%"]):
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        total = sum(data_dict.values()) if data_dict else 0
        if total == 0: total = 1
        
        sorted_items = sorted(data_dict.items(), key=lambda x: x[1], reverse=True)
        table.setRowCount(len(sorted_items))
        for i, (k, v) in enumerate(sorted_items):
            table.setItem(i, 0, QTableWidgetItem(k))
            
            item_v = QTableWidgetItem()
            item_v.setData(Qt.DisplayRole, v)
            table.setItem(i, 1, item_v)
            
            pct = (v / pkmn_usage) * 100
            item_pct = QTableWidgetItem()
            item_pct.setData(Qt.DisplayRole, round(pct, 1))
            table.setItem(i, 2, item_pct)
            
        table.setSortingEnabled(True)
        return table

    tabs.addTab(create_stats_table(build_data.get('moves', {})), "Mosse")
    tabs.addTab(create_stats_table(build_data.get('items', {})), "Strumenti")
    tabs.addTab(create_stats_table(build_data.get('abilities', {})), "Abilità")
    tabs.addTab(create_stats_table(build_data.get('natures', {})), "Nature")
    tabs.addTab(create_stats_table(build_data.get('evs', {})), "EVs Spread")
    
    layout.addWidget(tabs)
    return container

class LimitlessPokemonBuildDialog(QDialog):
    def __init__(self, pkmn_name, pkmn_usage, build_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Build Dettagliate: {pkmn_name}")
        self.setMinimumSize(600, 400)
        
        layout = QVBoxLayout(self)
        layout.addWidget(create_pokemon_build_widget(pkmn_name, pkmn_usage, build_data))
        
        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

class LimitlessTeamDetailWorker(QThread):
    finished_data = Signal(dict)
    
    def __init__(self, team_names):
        super().__init__()
        self.team_names = team_names
        
    def run(self):
        from database.connection import SessionLocal
        from sqlalchemy.orm import joinedload
        from sqlalchemy import select
        from collections import defaultdict
        from database.models import Match, Turn, MatchTeam, TeamVariant
        from domain.limitless_scraper import normalize_limitless_pokemon, build_replay_core_dict
        from src.analytics.archetypes import analizza_archetipo_team, get_match_team_archetypes
        
        session = SessionLocal()
        try:
            replay_cores = build_replay_core_dict(session)
            norm_team = frozenset([normalize_limitless_pokemon(x) for x in self.team_names])
            
            data = {
                "found": False,
            }
            
            if norm_team in replay_cores:
                t_ids = replay_cores[norm_team]
                teams = session.query(MatchTeam).filter(MatchTeam.id.in_(t_ids)).all()
                
                total_matches = len(teams)
                wins = 0
                for t in teams:
                    if t.match and t.trainer_id == t.match.winner_id:
                        wins += 1
                
                win_rate = round((wins / total_matches) * 100, 2) if total_matches > 0 else 0
                
                arch_str = analizza_archetipo_team("Core", t_ids, session).replace("Team Core : ", "")
                
                stmt = select(MatchTeam).options(
                    joinedload(MatchTeam.match).joinedload(Match.teams).joinedload(MatchTeam.variant),
                    joinedload(MatchTeam.match).joinedload(Match.turns).joinedload(Turn.actions),
                    joinedload(MatchTeam.variant)
                ).filter(MatchTeam.id.in_(t_ids))

                full_teams = session.scalars(stmt).unique().all()

                matrix_stats = defaultdict(lambda: defaultdict(lambda: {"wins": 0, "total": 0}))
                our_all_archs = set()
                oppo_all_archs = set()

                for t in full_teams:
                    match = t.match
                    if not match: continue
                    oppo_t = next((xt for xt in match.teams if xt.id != t.id), None)
                    if not oppo_t: continue
                    
                    our_archs = get_match_team_archetypes(t, session)
                    oppo_archs = get_match_team_archetypes(oppo_t, session)
                    
                    def clean_arch(a):
                        import re
                        return re.sub('<[^<]+>', '', a)
                        
                    our_archs = [clean_arch(a) for a in our_archs]
                    oppo_archs = [clean_arch(a) for a in oppo_archs]
                    
                    if not our_archs: our_archs = ["Unclassified"]
                    if not oppo_archs: oppo_archs = ["Unclassified"]
                    
                    is_win = (t.trainer_id == match.winner_id)
                    
                    for oa in our_archs:
                        our_all_archs.add(oa)
                        for opa in oppo_archs:
                            oppo_all_archs.add(opa)
                            matrix_stats[oa][opa]["total"] += 1
                            if is_win:
                                matrix_stats[oa][opa]["wins"] += 1
                                
                matrix_stats_plain = {}
                for k, v in matrix_stats.items():
                    matrix_stats_plain[k] = dict(v)

                data.update({
                    "found": True,
                    "total_matches": total_matches,
                    "wins": wins,
                    "win_rate": win_rate,
                    "arch_str": arch_str,
                    "our_archs": sorted(list(our_all_archs)),
                    "oppo_archs": sorted(list(oppo_all_archs)),
                    "matrix_stats": matrix_stats_plain
                })
                
        finally:
            session.close()
            
        self.finished_data.emit(data)


class LimitlessTeamDetailDialog(QDialog):
    def __init__(self, team_names, builds, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dettaglio Team e Build")
        self.setMinimumSize(800, 600)
        
        self.team_names = team_names
        self.builds = builds
        
        self.main_layout = QVBoxLayout(self)
        
        self.loading_overlay = LoadingOverlay(self)
        self.loading_overlay.start()
        
        self.worker = LimitlessTeamDetailWorker(team_names)
        self.worker.finished_data.connect(self.build_ui)
        self.worker.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'loading_overlay') and self.loading_overlay:
            self.loading_overlay.resize(self.size())

    def build_ui(self, replay_data):
        if self.loading_overlay:
            self.loading_overlay.stop()
            self.loading_overlay.deleteLater()
            self.loading_overlay = None
            
        header = QLabel(f"Dettaglio Team: {', '.join(self.team_names)}")
        header.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.main_layout.addWidget(header)
        
        main_tabs = QTabWidget()
        
        # TAB 1: Statistiche Replay Locale
        replay_tab = QWidget()
        replay_layout = QVBoxLayout(replay_tab)
        
        if replay_data.get("found"):
            total_matches = replay_data["total_matches"]
            wins = replay_data["wins"]
            win_rate = replay_data["win_rate"]
            arch_str = replay_data["arch_str"]
            
            lbl_stats = QLabel(f"Nei replay salvati localmente, questo team ha giocato <b>{total_matches}</b> partite.<br>"
                               f"Vittorie: <b>{wins}</b><br>"
                               f"Sconfitte: <b>{total_matches - wins}</b><br>"
                               f"Win Rate: <b>{win_rate}%</b>")
            lbl_stats.setStyleSheet("font-size: 14px;")
            replay_layout.addWidget(lbl_stats)
            
            lbl_arch = QLabel(f"Archetipi rilevati in locale: <b>{arch_str}</b>")
            lbl_arch.setStyleSheet("font-size: 14px; margin-top: 10px;")
            replay_layout.addWidget(lbl_arch)

            # --- Inizio Matrice dei Matchup ---
            lbl_matrix = QLabel("<b>Matrice dei Matchup (Win Rate contro Archetipi Avversari)</b>")
            lbl_matrix.setStyleSheet("font-size: 14px; margin-top: 15px; margin-bottom: 5px;")
            replay_layout.addWidget(lbl_matrix)
            
            our_archs_sorted = replay_data["our_archs"]
            oppo_archs_sorted = replay_data["oppo_archs"]
            matrix_stats = replay_data["matrix_stats"]
            
            if our_archs_sorted and oppo_archs_sorted:
                table_matrix = QTableWidget()
                table_matrix.setRowCount(len(our_archs_sorted))
                table_matrix.setColumnCount(len(oppo_archs_sorted))
                
                table_matrix.setVerticalHeaderLabels(our_archs_sorted)
                table_matrix.setHorizontalHeaderLabels(oppo_archs_sorted)
                table_matrix.setEditTriggers(QTableWidget.NoEditTriggers)
                
                for r_idx, r_arch in enumerate(our_archs_sorted):
                    for c_idx, c_arch in enumerate(oppo_archs_sorted):
                        stats = matrix_stats[r_arch].get(c_arch, {"total": 0})
                        if stats["total"] > 0:
                            wr = round((stats["wins"] / stats["total"]) * 100)
                            cell_text = f"{wr}% ({stats['total']})"
                        else:
                            cell_text = "-"
                            
                        item = QTableWidgetItem(cell_text)
                        item.setTextAlignment(Qt.AlignCenter)
                        table_matrix.setItem(r_idx, c_idx, item)
                        
                table_matrix.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
                replay_layout.addWidget(table_matrix)
            else:
                lbl_no_matrix = QLabel("Dati non sufficienti per calcolare la matrice.")
                lbl_no_matrix.setStyleSheet("color: gray; font-style: italic;")
                replay_layout.addWidget(lbl_no_matrix)
                
            replay_layout.addStretch()
        else:
            lbl_stats = QLabel("Questo team esatto (6 Pokémon) non è mai stato registrato nei replay del database locale.")
            lbl_stats.setStyleSheet("font-size: 14px; font-style: italic;")
            replay_layout.addWidget(lbl_stats)
            replay_layout.addStretch()
            
        main_tabs.addTab(replay_tab, "Statistiche Replay (Locale)")
        
        for p in self.team_names:
            b_data = self.builds.get(p, {'items': {}, 'abilities': {}, 'natures': {}, 'evs': {}, 'moves': {}, 'count': 0})
            usage = b_data.get('count', 0)
            if usage == 0: usage = 1
            
            p_widget = create_pokemon_build_widget(p, usage, b_data)
            main_tabs.addTab(p_widget, p)
            
        self.main_layout.addWidget(main_tabs)
        
        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.accept)
        self.main_layout.addWidget(btn_close)


class LimitlessTournamentsWidget(QWidget):
    tournament_selected = Signal(str, str) # id, name

    def __init__(self, parent_main=None):
        super().__init__()
        self.parent_main = parent_main
        self.current_data = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Controls Header
        self.controls_container = QFrame()
        self.controls_container.setFixedHeight(68)
        self.controls_container.setStyleSheet("background-color: #111; border: 1px solid #222; border-radius: 6px;")
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 4)
        self.controls_container.setGraphicsEffect(shadow)
        
        top_layout = QHBoxLayout(self.controls_container)
        top_layout.setContentsMargins(15, 10, 15, 10)
        
        top_layout.addWidget(QLabel("Formato:"))
        
        self.combo_format = QComboBox()
        self.combo_format.addItem("Tutti", "")
        self.combo_format.setEnabled(False)
        top_layout.addWidget(self.combo_format)
        
        top_layout.addWidget(QLabel("Num Tornei:"))
        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, 100)
        self.spin_count.setValue(5)
        top_layout.addWidget(self.spin_count)
        
        self.btn_refresh = QPushButton("Importa Tornei")
        self.btn_refresh.clicked.connect(self.load_tournaments)
        top_layout.addWidget(self.btn_refresh)
        top_layout.addStretch()
        
        layout.addWidget(self.controls_container)
        
        self.lbl_status = QLabel("")
        layout.addWidget(self.lbl_status)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.tabs = QTabWidget()

        # Tab 1: Lista Tornei
        self.tab_tournaments = QWidget()
        tournaments_layout = QVBoxLayout(self.tab_tournaments)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Data", "Nome", "Formato", "Giocatori", "Vincitore"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.on_row_double_clicked)
        tournaments_layout.addWidget(self.table)
        self.tabs.addTab(self.tab_tournaments, "Tornei Trovati")

        # Tab 2: Usage Team Globale
        self.tab_teams = QWidget()
        teams_layout = QVBoxLayout(self.tab_teams)
        self.table_teams = QTableWidget()
        self.table_teams.setColumnCount(5)
        self.table_teams.setHorizontalHeaderLabels(["Team Core", "Utilizzi", "%", "Archetipo (da Replay)", "WR %"])
        self.table_teams.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_teams.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_teams.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_teams.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_teams.cellDoubleClicked.connect(self.on_team_double_clicked)
        teams_layout.addWidget(self.table_teams)
        self.tabs.addTab(self.tab_teams, "Usage Team Globale")

        # Tab 3: Usage Pokemon Globale
        self.tab_pokemon = QWidget()
        pokemon_layout = QVBoxLayout(self.tab_pokemon)
        self.lbl_pkmn_help = QLabel("Fai doppio clic su un Pokémon per vedere le build globali (se disponibili)")
        self.lbl_pkmn_help.setStyleSheet("color: gray; font-style: italic;")
        pokemon_layout.addWidget(self.lbl_pkmn_help)
        
        self.table_pokemon = QTableWidget()
        self.table_pokemon.setColumnCount(3)
        self.table_pokemon.setHorizontalHeaderLabels(["Pokémon", "Utilizzi", "%"])
        self.table_pokemon.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_pokemon.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_pokemon.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_pokemon.cellDoubleClicked.connect(self.on_pokemon_double_clicked)
        pokemon_layout.addWidget(self.table_pokemon)
        self.tabs.addTab(self.tab_pokemon, "Usage Pokémon Globale")

        layout.addWidget(self.tabs)
        
        self.loading_overlay = LoadingOverlay(self.tabs)
        
        # Load formats on start
        self.format_worker = LimitlessFormatsWorker()
        self.format_worker.finished.connect(self.on_formats_loaded)
        self.format_worker.start()

    def on_formats_loaded(self, formats_dict):
        self.combo_format.clear()
        self.combo_format.addItem("Tutti", "")
        # Limitless API returns { "M-B": "Regulation Set M-B", ... }
        for code, name in formats_dict.items():
            self.combo_format.addItem(name, code)
        self.combo_format.setEnabled(True)

    def load_tournaments(self):
        reg = self.combo_format.currentData()
        count = self.spin_count.value()
            
        self.btn_refresh.setEnabled(False)
        self.combo_format.setEnabled(False)
        self.spin_count.setEnabled(False)
        
        self.lbl_status.setText("Inizializzazione importazione multipla API...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.current_data = {}
        
        self.loading_overlay.start()
        
        self.table.setSortingEnabled(False)
        self.table_teams.setSortingEnabled(False)
        self.table_pokemon.setSortingEnabled(False)
        
        self.table.setRowCount(0)
        self.table_teams.setRowCount(0)
        self.table_pokemon.setRowCount(0)
        
        self.worker = MultiTournamentWorker(regulation_filter=reg, count=count)
        self.worker.progress.connect(self.on_progress)
        self.worker.partial_results.connect(self.update_tables)
        self.worker.finished.connect(self.on_load_finished)
        self.worker.error.connect(self.on_load_error)
        self.worker.start()

    def on_progress(self, current, total, message):
        self.lbl_status.setText(message)
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setRange(0, 0)

    def update_tables(self, data):
        self.current_data = data
        total_teams = data.get('total_teams', 1)
        if total_teams == 0: total_teams = 1
        
        self.table.setSortingEnabled(False)
        self.table_teams.setSortingEnabled(False)
        self.table_pokemon.setSortingEnabled(False)
        
        tournaments = data.get('tournaments', [])
        self.table.setRowCount(len(tournaments))
        for i, t in enumerate(tournaments):
            self.table.setItem(i, 0, QTableWidgetItem(t['date'][:10] if t['date'] else ""))
            self.table.setItem(i, 1, QTableWidgetItem(t['name']))
            self.table.setItem(i, 2, QTableWidgetItem(t['format']))
            
            item_players = QTableWidgetItem()
            item_players.setData(Qt.DisplayRole, t['players'])
            self.table.setItem(i, 3, item_players)
            
            self.table.setItem(i, 4, QTableWidgetItem(t['winner']))
            self.table.item(i, 0).setData(Qt.UserRole, t['id'])
            
        teams = data.get('team_usage', [])
        self.table_teams.setRowCount(len(teams))
        for i, team_data in enumerate(teams):
            if len(team_data) == 4:
                team, count, archetype, wr = team_data
            elif len(team_data) == 3:
                team, count, archetype = team_data
                wr = "N/D"
            else:
                team, count = team_data
                archetype = "N/D"
                wr = "N/D"
                
            self.table_teams.setItem(i, 0, QTableWidgetItem(", ".join(team)))
            item_count = QTableWidgetItem()
            item_count.setData(Qt.DisplayRole, count)
            self.table_teams.setItem(i, 1, item_count)
            pct = (count / total_teams) * 100
            item_pct = QTableWidgetItem()
            item_pct.setData(Qt.DisplayRole, round(pct, 1))
            self.table_teams.setItem(i, 2, item_pct)
            item_arch = QTableWidgetItem(archetype) # Testo nascosto per il sort
            self.table_teams.setItem(i, 3, item_arch)
            lbl_arch = QLabel(archetype)
            lbl_arch.setTextFormat(Qt.RichText)
            lbl_arch.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            lbl_arch.setStyleSheet("padding: 2px;")
            self.table_teams.setCellWidget(i, 3, lbl_arch)
            self.table_teams.setItem(i, 4, QTableWidgetItem(wr))
            
        pokemons = data.get('pokemon_usage', [])
        self.table_pokemon.setRowCount(len(pokemons))
        for i, (pkmn, count) in enumerate(pokemons):
            self.table_pokemon.setItem(i, 0, QTableWidgetItem(pkmn))
            item_count = QTableWidgetItem()
            item_count.setData(Qt.DisplayRole, count)
            self.table_pokemon.setItem(i, 1, item_count)
            pct = (count / total_teams) * 100
            item_pct = QTableWidgetItem()
            item_pct.setData(Qt.DisplayRole, round(pct, 1))
            self.table_pokemon.setItem(i, 2, item_pct)
            self.table_pokemon.item(i, 0).setData(Qt.UserRole, pkmn)
            
        self.table.setSortingEnabled(True)
        self.table_teams.setSortingEnabled(True)
        self.table_pokemon.setSortingEnabled(True)

    def on_load_finished(self, data):
        if data:
            self.update_tables(data)
        self.btn_refresh.setEnabled(True)
        self.combo_format.setEnabled(True)
        self.spin_count.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.loading_overlay.stop()
        self.lbl_status.setText("Importazione e calcolo build completati.")

    def on_load_error(self, err):
        self.btn_refresh.setEnabled(True)
        self.combo_format.setEnabled(True)
        self.spin_count.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.loading_overlay.stop()
        self.lbl_status.setText("Errore.")
        QMessageBox.critical(self, "Errore", f"Impossibile caricare i tornei: {err}")

    def on_row_double_clicked(self, row, col):
        t_id = self.table.item(row, 0).data(Qt.UserRole)
        t_name = self.table.item(row, 1).text()
        self.tournament_selected.emit(t_id, t_name)

    
    def on_team_double_clicked(self, row, col):
        team_str = self.table_teams.item(row, 0).text()
        team_names = [x.strip() for x in team_str.split(',')]
        builds = self.current_data.get('builds', {})
        if not builds:
            QMessageBox.information(self, "Dati", "I dati sulle build non sono ancora stati estratti.")
            return
            
        dlg = LimitlessTeamDetailDialog(team_names, builds, self)
        dlg.exec()

    def on_pokemon_double_clicked(self, row, col):
        pkmn_name = self.table_pokemon.item(row, 0).data(Qt.UserRole)
        builds = self.current_data.get('builds', {})
        
        if pkmn_name in builds:
            b_data = builds[pkmn_name]
            if b_data['count'] > 0:
                dlg = LimitlessPokemonBuildDialog(pkmn_name, b_data['count'], b_data, self)
                dlg.exec()
            else:
                QMessageBox.information(self, "Build", "Nessuna teamlist pubblica trovata per questo Pokémon nei tornei importati.")
        else:
            QMessageBox.information(self, "Build", "I dati sulle build non sono ancora stati estratti.")


class LimitlessTournamentDetailWidget(QWidget):
    back_requested = Signal()

    def __init__(self, parent_main=None):
        super().__init__()
        self.parent_main = parent_main
        self.current_data = {}
        layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        self.btn_back = QPushButton("<- Torna Indietro")
        self.btn_back.clicked.connect(self.back_requested.emit)
        top_layout.addWidget(self.btn_back)
        
        self.lbl_title = QLabel("")
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-left: 20px;")
        top_layout.addWidget(self.lbl_title)
        
        top_layout.addStretch()
        layout.addLayout(top_layout)
        
        self.lbl_status = QLabel("")
        layout.addWidget(self.lbl_status)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.tabs = QTabWidget()
        
        # Tab 1: Classifica
        self.tab_standings = QWidget()
        standings_layout = QVBoxLayout(self.tab_standings)
        self.table_standings = QTableWidget()
        self.table_standings.setColumnCount(4)
        self.table_standings.setHorizontalHeaderLabels(["Posizione", "Nome", "Nazione", "Team (Pokémon)"])
        self.table_standings.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_standings.setEditTriggers(QTableWidget.NoEditTriggers)
        standings_layout.addWidget(self.table_standings)
        self.tabs.addTab(self.tab_standings, "Classifica")
        
        # Tab 2: Usage Team
        self.tab_teams = QWidget()
        teams_layout = QVBoxLayout(self.tab_teams)
        self.table_teams = QTableWidget()
        self.table_teams.setColumnCount(5)
        self.table_teams.setHorizontalHeaderLabels(["Team Core", "Utilizzi", "%", "Archetipo (da Replay)", "WR %"])
        self.table_teams.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_teams.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_teams.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_teams.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_teams.cellDoubleClicked.connect(self.on_team_double_clicked)
        teams_layout.addWidget(self.table_teams)
        self.tabs.addTab(self.tab_teams, "Usage Team")
        
        # Tab 3: Usage Pokemon
        self.tab_pokemon = QWidget()
        pokemon_layout = QVBoxLayout(self.tab_pokemon)
        self.lbl_pkmn_help = QLabel("Fai doppio clic su un Pokémon per vedere le build (se disponibili)")
        self.lbl_pkmn_help.setStyleSheet("color: gray; font-style: italic;")
        pokemon_layout.addWidget(self.lbl_pkmn_help)
        
        self.table_pokemon = QTableWidget()
        self.table_pokemon.setColumnCount(3)
        self.table_pokemon.setHorizontalHeaderLabels(["Pokémon", "Utilizzi", "%"])
        self.table_pokemon.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_pokemon.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_pokemon.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_pokemon.cellDoubleClicked.connect(self.on_pokemon_double_clicked)
        pokemon_layout.addWidget(self.table_pokemon)
        self.tabs.addTab(self.tab_pokemon, "Usage Pokémon")
        
        layout.addWidget(self.tabs)
        
        self.loading_overlay = LoadingOverlay(self.tabs)

    def load_tournament(self, tournament_id, tournament_name):
        self.lbl_title.setText(f"Torneo: {tournament_name}")
        self.lbl_status.setText("Caricamento in corso...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.current_data = {}
        
        self.loading_overlay.start()
        
        self.table_standings.setSortingEnabled(False)
        self.table_teams.setSortingEnabled(False)
        self.table_pokemon.setSortingEnabled(False)
        
        self.table_standings.setRowCount(0)
        self.table_teams.setRowCount(0)
        self.table_pokemon.setRowCount(0)
        
        self.worker = TournamentDetailWorker(tournament_id)
        self.worker.progress.connect(self.on_progress)
        self.worker.partial_results.connect(self.update_tables)
        self.worker.finished.connect(self.on_load_finished)
        self.worker.error.connect(self.on_load_error)
        self.worker.start()

    def on_progress(self, current, total, message):
        self.lbl_status.setText(message)
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setRange(0, 0)

    def update_tables(self, data):
        self.current_data = data
        total_teams = data.get('total_teams', 1)
        if total_teams == 0: total_teams = 1
        
        self.table_standings.setSortingEnabled(False)
        self.table_teams.setSortingEnabled(False)
        self.table_pokemon.setSortingEnabled(False)
        
        players = data.get('players', [])
        self.table_standings.setRowCount(len(players))
        for i, p in enumerate(players):
            item_pos = QTableWidgetItem()
            item_pos.setData(Qt.DisplayRole, int(p['placing']))
            self.table_standings.setItem(i, 0, item_pos)
            
            name_text = p['name']
            if p.get('has_list', False):
                name_text += " [TL]"
            self.table_standings.setItem(i, 1, QTableWidgetItem(name_text))
            self.table_standings.setItem(i, 2, QTableWidgetItem(p.get('country', '')))
            self.table_standings.setItem(i, 3, QTableWidgetItem(", ".join(p.get('team', []))))
            
        teams = data.get('team_usage', [])
        self.table_teams.setRowCount(len(teams))
        for i, team_data in enumerate(teams):
            if len(team_data) == 4:
                team, count, archetype, wr = team_data
            elif len(team_data) == 3:
                team, count, archetype = team_data
                wr = "N/D"
            else:
                team, count = team_data
                archetype = "N/D"
                wr = "N/D"
                
            self.table_teams.setItem(i, 0, QTableWidgetItem(", ".join(team)))
            item_count = QTableWidgetItem()
            item_count.setData(Qt.DisplayRole, count)
            self.table_teams.setItem(i, 1, item_count)
            pct = (count / total_teams) * 100
            item_pct = QTableWidgetItem()
            item_pct.setData(Qt.DisplayRole, round(pct, 1))
            self.table_teams.setItem(i, 2, item_pct)
            item_arch = QTableWidgetItem(archetype)
            self.table_teams.setItem(i, 3, item_arch)
            lbl_arch = QLabel(archetype)
            lbl_arch.setTextFormat(Qt.RichText)
            lbl_arch.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            lbl_arch.setStyleSheet("padding: 2px;")
            self.table_teams.setCellWidget(i, 3, lbl_arch)
            self.table_teams.setItem(i, 4, QTableWidgetItem(wr))
            
        pokemons = data.get('pokemon_usage', [])
        self.table_pokemon.setRowCount(len(pokemons))
        for i, (pkmn, count) in enumerate(pokemons):
            self.table_pokemon.setItem(i, 0, QTableWidgetItem(pkmn))
            item_count = QTableWidgetItem()
            item_count.setData(Qt.DisplayRole, count)
            self.table_pokemon.setItem(i, 1, item_count)
            pct = (count / total_teams) * 100
            item_pct = QTableWidgetItem()
            item_pct.setData(Qt.DisplayRole, round(pct, 1))
            self.table_pokemon.setItem(i, 2, item_pct)
            self.table_pokemon.item(i, 0).setData(Qt.UserRole, pkmn)
            
        self.table_standings.setSortingEnabled(True)
        self.table_teams.setSortingEnabled(True)
        self.table_pokemon.setSortingEnabled(True)

    def on_load_finished(self, data):
        self.update_tables(data)
        self.progress_bar.setVisible(False)
        self.loading_overlay.stop()
        self.lbl_status.setText("Estrazione build completata.")

    def on_load_error(self, err):
        self.progress_bar.setVisible(False)
        self.loading_overlay.stop()
        self.lbl_status.setText("Errore durante il caricamento.")
        QMessageBox.critical(self, "Errore", f"Impossibile caricare i dettagli: {err}")

    
    def on_team_double_clicked(self, row, col):
        team_str = self.table_teams.item(row, 0).text()
        team_names = [x.strip() for x in team_str.split(',')]
        builds = self.current_data.get('builds', {})
        if not builds:
            QMessageBox.information(self, "Dati", "I dati sulle build non sono ancora stati estratti.")
            return
            
        dlg = LimitlessTeamDetailDialog(team_names, builds, self)
        dlg.exec()

    def on_pokemon_double_clicked(self, row, col):
        pkmn_name = self.table_pokemon.item(row, 0).data(Qt.UserRole)
        builds = self.current_data.get('builds', {})
        
        if pkmn_name in builds:
            b_data = builds[pkmn_name]
            if b_data['count'] > 0:
                dlg = LimitlessPokemonBuildDialog(pkmn_name, b_data['count'], b_data, self)
                dlg.exec()
            else:
                QMessageBox.information(self, "Build", "Nessuna teamlist pubblica trovata per questo Pokémon.")
        else:
            QMessageBox.information(self, "Build", "I dati sulle build non sono ancora stati estratti.")
