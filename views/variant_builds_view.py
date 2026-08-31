import os
from collections import Counter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout, QScrollArea, QFrame,
    QTableWidget, QTableWidgetItem
)
from PySide6.QtCore import Qt, Signal
from database.connection import SessionLocal
from database.models_v2 import MatchTeamV2, TeamVariantV2, PokemonBuild
from views.team_analysis_view import get_pokemon_pixmap
from config.theme import Palette

class VariantBuildsWidget(QWidget):
    back_signal = Signal()
    import_signal = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.variant_data = None
        
        main_layout = QVBoxLayout(self)
        
        header_layout = QHBoxLayout()
        self.btn_back = QPushButton("🔙 Torna all'analisi archetipi")
        self.btn_back.setFixedWidth(200)
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.clicked.connect(self.back_signal.emit)
        
        header_layout.addWidget(self.btn_back)
        
        self.btn_import = QPushButton("📥 Importa in Costruisci e Confronta")
        self.btn_import.setCursor(Qt.PointingHandCursor)
        self.btn_import.setStyleSheet(
            f"background-color: {Palette.TERTIARY}; color: {Palette.TEXT_PRIMARY}; padding: 6px 12px; border-radius: 4px; font-weight: bold;"
        )
        self.btn_import.clicked.connect(self.on_import_clicked)
        header_layout.addWidget(self.btn_import)
        
        self.btn_copy = QPushButton("📋 Copia Paste")
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setStyleSheet(
            f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; padding: 6px 12px; border-radius: 4px; font-weight: bold;"
        )
        self.btn_copy.clicked.connect(self.on_copy_paste_clicked)
        header_layout.addWidget(self.btn_copy)
        
        header_layout.addStretch()
        
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
        self.current_most_common_paste = ""
        
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        match_ids = [m["id"] for m in variant["match_ids"]]
        
        session = SessionLocal()
        
        chunk_size = 500
        
        team_ids_list = list(variant["team_ids"])
        match_teams = []
        for i in range(0, len(team_ids_list), chunk_size):
            chunk = team_ids_list[i:i+chunk_size]
            if chunk:
                match_teams.extend(session.query(MatchTeamV2).filter(MatchTeamV2.id.in_(chunk)).all())
        
        variant_ids_list = list(set([mt.team_variant_id for mt in match_teams if mt.team_variant_id]))
        team_variants = []
        for i in range(0, len(variant_ids_list), chunk_size):
            chunk = variant_ids_list[i:i+chunk_size]
            if chunk:
                team_variants.extend(session.query(TeamVariantV2).filter(TeamVariantV2.id.in_(chunk)).all())
        
        build_ids = set()
        for tv in team_variants:
            for tvb in tv.builds:
                if tvb.build_id:
                    build_ids.add(tvb.build_id)
                    
        build_ids_list = list(build_ids)
        builds = []
        for i in range(0, len(build_ids_list), chunk_size):
            chunk = build_ids_list[i:i+chunk_size]
            if chunk:
                builds.extend(session.query(PokemonBuild).filter(PokemonBuild.id.in_(chunk)).all())
        
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
                if b.ability_id: abilities[b.ability_id] += 1
                if b.tera_type: teras[b.tera_type] += 1
                if b.nature: natures[b.nature] += 1
                if b.move_slots:
                    for ms in b.move_slots:
                        m_name = ms.move.name if ms.move else ms.move_id
                        if m_name: moves[m_name] += 1
                        
            card = self.create_build_card(sp, len(sp_builds), items, abilities, teras, natures, moves)
            self.content_layout.addWidget(card, row, col)
            
            top_item = items.most_common(1)[0][0] if items else ""
            top_ability = abilities.most_common(1)[0][0] if abilities else ""
            top_nature = natures.most_common(1)[0][0] if natures else ""
            top_moves = [m[0] for m in moves.most_common(4)]
            
            # Calcolo EVs più comuni e conversione in formato Champions (max 32 per stat)
            evs_counter = Counter()
            for b in sp_builds:
                if b.stats_observations:
                    obs = b.stats_observations[0]
                    evs_counter[(obs.ev_hp, obs.ev_atk, obs.ev_def, obs.ev_spa, obs.ev_spd, obs.ev_spe)] = evs_counter.get((obs.ev_hp, obs.ev_atk, obs.ev_def, obs.ev_spa, obs.ev_spd, obs.ev_spe), 0) + 1
                else:
                    evs_counter[(0, 0, 0, 0, 0, 0)] += 1
            
            top_evs = evs_counter.most_common(1)[0][0] if evs_counter else (0, 0, 0, 0, 0, 0)
            
            def to_champ_ev(val: int) -> int:
                return (val + 4) // 8 if val > 0 else 0
                
            total_evs = sum(top_evs)
            champ_evs = top_evs if total_evs <= 66 else tuple(to_champ_ev(v) for v in top_evs)
            
            header = sp.capitalize()
            if top_item:
                header += f" @ {top_item}"
            self.current_most_common_paste += f"{header}\n"
            
            if top_ability:
                self.current_most_common_paste += f"Ability: {top_ability}\n"
                
            self.current_most_common_paste += "Level: 50\n"
            
            ev_labels = ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]
            ev_strings = []
            for i, val in enumerate(champ_evs):
                if val > 0:
                    ev_strings.append(f"{val} {ev_labels[i]}")
                    
            if ev_strings:
                self.current_most_common_paste += f"EVs: {' / '.join(ev_strings)}\n"
                
            if top_nature:
                self.current_most_common_paste += f"{top_nature} Nature\n"
                
            for m in top_moves:
                self.current_most_common_paste += f"- {m}\n"
                
            self.current_most_common_paste += "\n"
            
            col += 1
            if col > 2:
                col = 0
                row += 1
                
    def on_copy_paste_clicked(self):
        if self.current_most_common_paste:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self.current_most_common_paste.strip())
            
        # --- TABELLA MATCHUP ---
        from collections import defaultdict
        from src.analytics.archetypes import get_match_team_archetypes
        from sqlalchemy.orm import joinedload
        from database.models_v2 import MatchV2, TurnV2, TurnActionV2
        
        matches_db = session.query(MatchV2).options(
            joinedload(MatchV2.teams).joinedload(MatchTeamV2.variant),
            joinedload(MatchV2.turns).joinedload(TurnV2.actions)
        ).filter(MatchV2.id.in_(match_ids)).all()
        
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
                
            our_archs = get_match_team_archetypes(our_team, session)
            opp_archs = get_match_team_archetypes(opp_team, session)
            
            # Rimuoviamo l'HTML, prendiamo solo il testo base per la tabella
            def clean_arch(a):
                import re
                return re.sub('<[^<]+>', '', a)
                
            our_archs = [clean_arch(a) for a in our_archs]
            opp_archs = [clean_arch(a) for a in opp_archs]
            
            if not our_archs: our_archs = ["Unclassified"]
            if not opp_archs: opp_archs = ["Unclassified"]
            
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
            
            table.resizeColumnsToContents()
            table.setMinimumHeight(150 + (len(all_our_archs) * 35))
            
            lbl_table = QLabel("Rapporti Matchup")
            lbl_table.setStyleSheet("font-size: 18px; font-weight: 700; color: #C49A3C; margin-top: 24px; margin-bottom: 12px;")
            
            next_row = row + 1 if col > 0 else row
            self.content_layout.addWidget(lbl_table, next_row, 0, 1, 3)
            self.content_layout.addWidget(table, next_row + 1, 0, 1, 3)
            
        session.close()
                
    def create_build_card(self, species, count, items, abilities, teras, natures, moves) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card_elevated")
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet("QLabel { border: none; background: transparent; }")
        
        layout = QVBoxLayout(frame)
        
        title_layout = QHBoxLayout()
        icon_lbl = QLabel()
        pixmap = get_pokemon_pixmap(species, 48)
        if pixmap and not pixmap.isNull():
            icon_lbl.setPixmap(pixmap)
        title_lbl = QLabel(f"<b style='color: #DEDAD4;'>{species.capitalize()}</b> <span style='font-size:12px; color:#6E7285;'>({count} uses)</span>")
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
            f"<span style='color:#A69ACA; font-weight:600;'>Strumenti:</span><br>{format_percentages(items, count, 3)}<br>"
            f"<span style='color:#A69ACA; font-weight:600;'>Abilità:</span><br>{format_percentages(abilities, count, 3)}<br>"
            f"<span style='color:#A69ACA; font-weight:600;'>Tera:</span><br>{format_percentages(teras, count, 3)}<br>"
            f"<span style='color:#A69ACA; font-weight:600;'>Nature:</span><br>{format_percentages(natures, count, 3)}<br>"
            f"<span style='color:#A69ACA; font-weight:600;'>Mosse:</span><br>{format_percentages(moves, count, 6)}"
        )
        layout.addWidget(info)
        
        layout.addStretch()
        return frame

    def on_import_clicked(self):
        if self.current_most_common_paste:
            self.import_signal.emit(self.current_most_common_paste.strip())
