import os
from collections import Counter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout, QScrollArea, QFrame,
    QTableWidget, QTableWidgetItem
)
from PySide6.QtCore import Qt, Signal
from database.connection import SessionLocal
from database.models import PokemonBuild, Team
from views.team_analysis_view import get_pokemon_pixmap

class VariantBuildsWidget(QWidget):
    back_signal = Signal()
    
    def __init__(self):
        super().__init__()
        self.variant_data = None
        
        main_layout = QVBoxLayout(self)
        
        header_layout = QGridLayout()
        self.btn_back = QPushButton("Indietro")
        self.btn_back.setFixedWidth(100)
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.clicked.connect(self.back_signal.emit)
        
        self.lbl_title = QLabel("Dettaglio Build Variante")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #B6FAF5;")
        
        header_layout.addWidget(self.btn_back, 0, 0, Qt.AlignLeft)
        header_layout.addWidget(self.lbl_title, 0, 1, Qt.AlignCenter)
        header_layout.setColumnStretch(0, 1)
        header_layout.setColumnStretch(1, 2)
        header_layout.setColumnStretch(2, 1)
        
        main_layout.addLayout(header_layout)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        self.content_widget = QWidget()
        self.content_layout = QGridLayout(self.content_widget)
        scroll.setWidget(self.content_widget)
        
        main_layout.addWidget(scroll)
        
    def normalize_species(self, sp: str) -> str:
        if not sp: return ""
        sp = sp.lower()
        if sp == "floettemega": return "floetteeternal"
        if sp == "sinistchamasterpiece": return "sinistcha"
        if sp.endswith("megax"): return sp[:-5]
        if sp.endswith("megay"): return sp[:-5]
        if sp.endswith("mega"): return sp[:-4]
        return sp

    def load_variant(self, variant: dict):
        self.variant_data = variant
        
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        match_ids = [m["id"] for m in variant["match_ids"]]
        
        session = SessionLocal()
        builds = session.query(PokemonBuild).join(Team).filter(Team.match_id.in_(match_ids)).all()
        
        species_builds = {}
        for b in builds:
            if not b.species_id: continue
            sp = self.normalize_species(b.species_id)
            if sp not in species_builds:
                species_builds[sp] = []
            species_builds[sp].append(b)
            
        target_species = variant.get("species_ids", [])
        
        row = 0
        col = 0
        for sp in target_species:
            sp_builds = species_builds.get(sp, [])
            
            items = Counter()
            abilities = Counter()
            teras = Counter()
            natures = Counter()
            moves = Counter()
            
            for b in sp_builds:
                if b.item_id: items[b.item_id] += 1
                if b.ability and b.ability.name: abilities[b.ability.name] += 1
                if b.tera_type: teras[b.tera_type] += 1
                if b.nature: natures[b.nature] += 1
                if b.moves:
                    for m in b.moves.split(","):
                        m = m.strip()
                        if m: moves[m] += 1
                        
            card = self.create_build_card(sp, len(sp_builds), items, abilities, teras, natures, moves)
            self.content_layout.addWidget(card, row, col)
            
            col += 1
            if col > 2:
                col = 0
                row += 1
                
        # --- TABELLA MATCHUP ---
        from collections import defaultdict
        from src.analytics.archetypes import get_match_team_archetypes
        from sqlalchemy.orm import joinedload
        from database.models import Match, Turn, TurnAction
        
        matches_db = session.query(Match).options(
            joinedload(Match.teams).joinedload(Team.pokemon_builds),
            joinedload(Match.turns).joinedload(Turn.actions)
        ).filter(Match.id.in_(match_ids)).all()
        
        matchups = defaultdict(lambda: defaultdict(lambda: {'wins': 0, 'total': 0}))
        
        our_team_ids = set()
        for t_id in variant["team_ids"]:
            our_team_ids.add(t_id)
            
        for m in matches_db:
            if len(m.teams) != 2:
                continue
            
            our_team = None
            opp_team = None
            for t in m.teams:
                if t.id in our_team_ids:
                    our_team = t
                else:
                    opp_team = t
                    
            if not our_team or not opp_team:
                continue
                
            our_archs = get_match_team_archetypes(our_team)
            opp_archs = get_match_team_archetypes(opp_team)
            is_win = (m.winner_id == our_team.trainer_id)
            
            for oa in our_archs:
                for opa in opp_archs:
                    matchups[oa][opa]['total'] += 1
                    if is_win:
                        matchups[oa][opa]['wins'] += 1
        
        if matchups:
            all_our_archs = sorted(list(matchups.keys()))
            all_opp_archs = set()
            for oa in all_our_archs:
                all_opp_archs.update(matchups[oa].keys())
            all_opp_archs = sorted(list(all_opp_archs))
            
            table = QTableWidget()
            table.setRowCount(len(all_our_archs))
            table.setColumnCount(len(all_opp_archs) * 2)
            
            headers = []
            for opa in all_opp_archs:
                headers.extend([f"{opa}", f"Replay {opa}"])
            table.setHorizontalHeaderLabels(headers)
            table.setVerticalHeaderLabels(all_our_archs)
            
            for i, oa in enumerate(all_our_archs):
                for j, opa in enumerate(all_opp_archs):
                    stats = matchups[oa].get(opa, {'wins': 0, 'total': 0})
                    if stats['total'] > 0:
                        wr_str = f"{round((stats['wins'] / stats['total']) * 100)}%"
                        count_str = str(stats['total'])
                    else:
                        wr_str = "-"
                        count_str = "-"
                        
                    wr_item = QTableWidgetItem(wr_str)
                    wr_item.setTextAlignment(Qt.AlignCenter)
                    count_item = QTableWidgetItem(count_str)
                    count_item.setTextAlignment(Qt.AlignCenter)
                    
                    table.setItem(i, j * 2, wr_item)
                    table.setItem(i, j * 2 + 1, count_item)
            
            table.setStyleSheet("QTableWidget { background-color: #1A1A1A; color: white; border: 1px solid #333; gridline-color: #444; } QHeaderView::section { background-color: #222; color: #aaffaa; border: 1px solid #333; padding: 4px; font-weight: bold; }")
            table.resizeColumnsToContents()
            table.setMinimumHeight(150 + (len(all_our_archs) * 35))
            
            lbl_table = QLabel("Rapporti Matchup")
            lbl_table.setStyleSheet("font-size: 16px; font-weight: bold; color: #aaffaa; margin-top: 20px; margin-bottom: 10px;")
            
            next_row = row + 1 if col > 0 else row
            self.content_layout.addWidget(lbl_table, next_row, 0, 1, 3)
            self.content_layout.addWidget(table, next_row + 1, 0, 1, 3)
            
        session.close()
                
    def create_build_card(self, species, count, items, abilities, teras, natures, moves) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QFrame { background-color: #1A1A1A; border: 1px solid #333; border-radius: 8px; } QLabel { border: none; background: transparent; }")
        
        layout = QVBoxLayout(frame)
        
        title_layout = QHBoxLayout()
        icon_lbl = QLabel()
        pixmap = get_pokemon_pixmap(species, 48)
        if pixmap and not pixmap.isNull():
            icon_lbl.setPixmap(pixmap)
        title_lbl = QLabel(f"<b>{species.capitalize()}</b> <span style='font-size:12px; color:#888;'>({count} uses)</span>")
        title_lbl.setStyleSheet("font-size: 16px;")
        
        title_layout.addWidget(icon_lbl)
        title_layout.addWidget(title_lbl)
        title_layout.addStretch()
        
        layout.addLayout(title_layout)
        
        def format_percentages(counter, total, n=3):
            if not counter or total == 0: return "N/A"
            lines = []
            for k, v in counter.most_common(n):
                pct = round((v / total) * 100, 1)
                lines.append(f"&nbsp;&nbsp;{k} ({pct}%)")
            return "<br>".join(lines)
            
        info = QLabel(
            f"<span style='color:#aaffaa;'><b>Strumenti:</b></span><br>{format_percentages(items, count, 3)}<br>"
            f"<span style='color:#aaffaa;'><b>Abilità:</b></span><br>{format_percentages(abilities, count, 3)}<br>"
            f"<span style='color:#aaffaa;'><b>Tera:</b></span><br>{format_percentages(teras, count, 3)}<br>"
            f"<span style='color:#aaffaa;'><b>Nature:</b></span><br>{format_percentages(natures, count, 3)}<br>"
            f"<span style='color:#aaffaa;'><b>Mosse:</b></span><br>{format_percentages(moves, count, 6)}"
        )
        layout.addWidget(info)
        
        layout.addStretch()
        return frame
