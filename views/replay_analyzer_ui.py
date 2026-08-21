import os
import json
import urllib.request
import copy
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
    QSplitter, QFrame, QLabel, QListWidget, QListView,
    QListWidgetItem, QPushButton, QTextBrowser, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QPixmap
from database.repository import get_match_details

def get_pokemon_icon_path(species_name):
    if not species_name or species_name == "Vuoto":
        return None
        
    name = species_name.lower().replace(" ", "").replace("-", "")
    icon_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "icons"))
    os.makedirs(icon_dir, exist_ok=True)
    icon_path = os.path.join(icon_dir, f"{name}.png")
    
    if not os.path.exists(icon_path):
        url = f"https://play.pokemonshowdown.com/sprites/dex/{name}.png"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=3) as response:
                with open(icon_path, 'wb') as f:
                    f.write(response.read())
        except Exception as e:
            print(f"Failed to download sprite for {name}: {e}")
            return None
            
    return icon_path.replace("\\", "/")

class ReplayAnalyzerUI(QWidget):
    back_requested = Signal()
    link_clicked = Signal(str) # For future compatibility

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Replay Analyzer")
        
        self.match_data = {}
        
        self.setup_ui()
        self.setup_connections()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)

        # ==========================================
        # TOP BAR
        # ==========================================
        self.top_bar_layout = QHBoxLayout()
        self.lbl_nome_battaglia = QLabel("NomeBattagliaEFormato")
        self.lbl_nome_battaglia.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffcc00;")
        
        self.nav_bar = QFrame()
        self.nav_bar_layout = QHBoxLayout(self.nav_bar)
        self.nav_bar_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_back = QPushButton("🔙 Indietro")
        self.btn_back.clicked.connect(self.back_requested.emit)
        self.nav_bar_layout.addWidget(self.btn_back)
        self.nav_bar_layout.addStretch()
        
        self.top_bar_layout.addWidget(self.lbl_nome_battaglia)
        self.top_bar_layout.addWidget(self.nav_bar)
        self.top_bar_layout.setStretch(1, 1)  
        self.main_layout.addLayout(self.top_bar_layout)

        # ==========================================
        # MIDDLE SECTION
        # ==========================================
        self.middle_section_layout = QHBoxLayout()

        # --- Left: Player 1 Area ---
        self.p1_area_layout = QVBoxLayout()
        self.lbl_p1_info = QLabel("P1 Info")
        self.lbl_p1_info.setStyleSheet("font-weight: bold; color: #3498db;")
        self.p1_area_layout.addWidget(self.lbl_p1_info)
        
        self.p1_frames_layout = QHBoxLayout() 
        
        self.frame_img_p1 = QLabel()
        self.frame_img_p1.setAlignment(Qt.AlignCenter)
        self.frame_img_p1.setStyleSheet("background-color: #222; border: 1px solid #444; border-radius: 4px;")
        self.frame_img_p1.setFixedSize(120, 120)
        
        self.frame_dati_p1 = QFrame()
        self.frame_dati_p1.setFrameShape(QFrame.StyledPanel)
        self.layout_dati_p1 = QVBoxLayout(self.frame_dati_p1)
        self.lbl_dati_p1 = QLabel("Seleziona un Pokémon")
        self.lbl_dati_p1.setWordWrap(True)
        self.layout_dati_p1.addWidget(self.lbl_dati_p1)
        
        self.p1_frames_layout.addWidget(self.frame_img_p1)
        self.p1_frames_layout.addWidget(self.frame_dati_p1)
        
        self.list_widget_p1 = QListWidget()
        
        self.p1_area_layout.addLayout(self.p1_frames_layout)
        self.p1_area_layout.addWidget(self.list_widget_p1)

        # --- Right: Player 2 Area ---
        self.p2_area_layout = QVBoxLayout()
        self.lbl_p2_info = QLabel("P2 Info")
        self.lbl_p2_info.setStyleSheet("font-weight: bold; color: #e74c3c;")
        self.p2_area_layout.addWidget(self.lbl_p2_info)
        
        self.p2_frames_layout = QHBoxLayout()
        
        self.frame_dati_p2 = QFrame()
        self.frame_dati_p2.setFrameShape(QFrame.StyledPanel)
        self.layout_dati_p2 = QVBoxLayout(self.frame_dati_p2)
        self.lbl_dati_p2 = QLabel("Seleziona un Pokémon")
        self.lbl_dati_p2.setWordWrap(True)
        self.layout_dati_p2.addWidget(self.lbl_dati_p2)
        
        self.frame_img_p2 = QLabel()
        self.frame_img_p2.setAlignment(Qt.AlignCenter)
        self.frame_img_p2.setStyleSheet("background-color: #222; border: 1px solid #444; border-radius: 4px;")
        self.frame_img_p2.setFixedSize(120, 120)
        
        self.p2_frames_layout.addWidget(self.frame_dati_p2)
        self.p2_frames_layout.addWidget(self.frame_img_p2)
        
        self.list_widget_p2 = QListWidget()
        
        self.p2_area_layout.addLayout(self.p2_frames_layout)
        self.p2_area_layout.addWidget(self.list_widget_p2)

        self.middle_section_layout.addLayout(self.p1_area_layout)
        self.middle_section_layout.addLayout(self.p2_area_layout)
        self.main_layout.addLayout(self.middle_section_layout)

        # ==========================================
        # BOTTOM SECTION (QSplitter)
        # ==========================================
        self.bottom_splitter = QSplitter(Qt.Horizontal)

        # --- Left Pane (Turns and Actions) ---
        self.left_pane_widget = QWidget()
        self.left_pane_layout = QVBoxLayout(self.left_pane_widget)
        self.left_pane_layout.setContentsMargins(0, 0, 0, 0)
        
        self.left_pane_layout.addWidget(QLabel("Turni:"))
        self.list_widget_turni = QListWidget()
        self.left_pane_layout.addWidget(self.list_widget_turni)
        
        self.left_pane_layout.addWidget(QLabel("Azioni nel Turno:"))
        self.list_widget_azioni = QListWidget()
        self.left_pane_layout.addWidget(self.list_widget_azioni)

        # --- Center Pane (Board State) ---
        self.center_pane_widget = QWidget()
        self.center_pane_layout = QVBoxLayout(self.center_pane_widget)
        self.center_pane_layout.setContentsMargins(0, 0, 0, 0)
        
        self.frame_pokemon_in_campo = QFrame()
        self.frame_pokemon_in_campo.setFrameShape(QFrame.StyledPanel)
        self.pokemon_grid = QGridLayout(self.frame_pokemon_in_campo)
        
        self.lbl_p1a = QLabel("P1a<br>(Vuoto)")
        self.lbl_p1b = QLabel("P1b<br>(Vuoto)")
        self.lbl_p2a = QLabel("P2a<br>(Vuoto)")
        self.lbl_p2b = QLabel("P2b<br>(Vuoto)")
        
        # Stili pastello differenziati e testi centrati (semi-trasparenti per far vedere il meteo)
        p1_style = "background-color: rgba(212, 230, 241, 150); color: #1a5276; border: 2px solid #5499c7; border-radius: 8px; padding: 10px;"
        p2_style = "background-color: rgba(250, 219, 216, 150); color: #78281f; border: 2px solid #cd6155; border-radius: 8px; padding: 10px;"
        
        for lbl in (self.lbl_p1a, self.lbl_p1b):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(p1_style)
            lbl.setTextFormat(Qt.RichText)
            
        for lbl in (self.lbl_p2a, self.lbl_p2b):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(p2_style)
            lbl.setTextFormat(Qt.RichText)
            
        # P1a sopra P1b (Colonna 0) / P2a sopra P2b (Colonna 1)
        self.pokemon_grid.addWidget(self.lbl_p1a, 0, 0)
        self.pokemon_grid.addWidget(self.lbl_p1b, 1, 0)
        self.pokemon_grid.addWidget(self.lbl_p2a, 0, 1)
        self.pokemon_grid.addWidget(self.lbl_p2b, 1, 1)

        self.list_condizioni_p1 = QListWidget()
        self.list_condizioni_generali = QListWidget()
        self.list_condizioni_p2 = QListWidget()
        
        cond_layout = QHBoxLayout()
        
        p1_cond_layout = QVBoxLayout()
        p1_cond_layout.addWidget(QLabel("Cond. P1:"))
        p1_cond_layout.addWidget(self.list_condizioni_p1)
        
        gen_cond_layout = QVBoxLayout()
        gen_cond_layout.addWidget(QLabel("Globali:"))
        gen_cond_layout.addWidget(self.list_condizioni_generali)
        
        p2_cond_layout = QVBoxLayout()
        p2_cond_layout.addWidget(QLabel("Cond. P2:"))
        p2_cond_layout.addWidget(self.list_condizioni_p2)
        
        cond_layout.addLayout(p1_cond_layout)
        cond_layout.addLayout(gen_cond_layout)
        cond_layout.addLayout(p2_cond_layout)
        
        self.center_pane_layout.addWidget(self.frame_pokemon_in_campo)
        self.center_pane_layout.addLayout(cond_layout)

        # --- Right Pane (Action Details) ---
        self.right_pane_widget = QWidget()
        self.right_pane_layout = QVBoxLayout(self.right_pane_widget)
        self.right_pane_layout.setContentsMargins(0, 0, 0, 0)
        
        self.right_pane_layout.addWidget(QLabel("Attributi Azione:"))
        self.txt_attr = QTextBrowser()
        self.txt_attr.setOpenExternalLinks(False)
        self.txt_attr.anchorClicked.connect(self.on_txt_state_anchor_clicked)
        self.right_pane_layout.addWidget(self.txt_attr)
        
        self.right_pane_layout.addWidget(QLabel("Tags (Dati Tecnici):"))
        self.tree_widget_tags = QTreeWidget()
        self.tree_widget_tags.setHeaderHidden(True)
        self.right_pane_layout.addWidget(self.tree_widget_tags)

        self.bottom_splitter.addWidget(self.left_pane_widget)
        self.bottom_splitter.addWidget(self.center_pane_widget)
        self.bottom_splitter.addWidget(self.right_pane_widget)
        self.bottom_splitter.setSizes([250, 350, 250])

        self.main_layout.addWidget(self.bottom_splitter)
        self.main_layout.setStretch(1, 2)
        self.main_layout.setStretch(2, 3)

    # ==========================================
    # DATA BINDING AND EVENTS
    # ==========================================
    
    def setup_connections(self):
        self.list_widget_turni.currentItemChanged.connect(lambda curr, prev: self.on_turn_clicked(curr) if curr else None)
        self.list_widget_azioni.currentItemChanged.connect(lambda curr, prev: self.on_action_clicked(curr) if curr else None)
        self.list_widget_p1.itemClicked.connect(self.on_p1_pokemon_clicked)
        self.list_widget_p2.itemClicked.connect(self.on_p2_pokemon_clicked)
        
        # Also keep itemClicked as fallback for mouse clicks
        self.list_widget_turni.itemClicked.connect(self.on_turn_clicked)
        self.list_widget_azioni.itemClicked.connect(self.on_action_clicked)
        
    def on_txt_state_anchor_clicked(self, url: QUrl):
        self.link_clicked.emit(url.toString())

    def display_match(self, match_id: str):
        self.match_data = get_match_details(match_id)
        
        if not self.match_data:
            return

        fmt = self.match_data.get("format", "Regolamento Sconosciuto")
        self.lbl_nome_battaglia.setText(f"Match: {match_id} | {fmt}")

        self.populate_teams(self.match_data)
        self.populate_turns(self.match_data)
        
        self.list_widget_azioni.clear()
        self.txt_attr.clear()
        self.tree_widget_tags.clear()
        self.lbl_p1a.setText("P1a<br>(Vuoto)")
        self.lbl_p1b.setText("P1b<br>(Vuoto)")
        self.lbl_p2a.setText("P2a<br>(Vuoto)")
        self.lbl_p2b.setText("P2b<br>(Vuoto)")
        self.list_condizioni_p1.clear()
        self.list_condizioni_generali.clear()
        self.list_condizioni_p2.clear()
        self.lbl_dati_p1.setText("Seleziona un Pokémon")
        self.lbl_dati_p2.setText("Seleziona un Pokémon")
        self.frame_img_p1.clear()
        self.frame_img_p2.clear()

    def populate_teams(self, match_data: dict):
        self.list_widget_p1.clear()
        self.list_widget_p2.clear()

        teams = match_data.get("teams", {})
        
        p1_trainer = teams.get("p1", {}).get("trainer", "Sconosciuto")
        p1_rating = teams.get("p1", {}).get("rating", "N/A")
        self.lbl_p1_info.setText(f"Allenatore: {p1_trainer} | Rating: {p1_rating}")
        
        p2_trainer = teams.get("p2", {}).get("trainer", "Sconosciuto")
        p2_rating = teams.get("p2", {}).get("rating", "N/A")
        self.lbl_p2_info.setText(f"Allenatore: {p2_trainer} | Rating: {p2_rating}")
        
        for pokemon in teams.get("p1", {}).get("pokemon", []):
            name = pokemon.get("species", "Unknown") if isinstance(pokemon, dict) else str(pokemon)
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, pokemon)
            self.list_widget_p1.addItem(item)

        for pokemon in teams.get("p2", {}).get("pokemon", []):
            name = pokemon.get("species", "Unknown") if isinstance(pokemon, dict) else str(pokemon)
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, pokemon)
            self.list_widget_p2.addItem(item)

        if self.list_widget_p1.count() > 0:
            self.list_widget_p1.setCurrentRow(0)
            self.on_p1_pokemon_clicked(self.list_widget_p1.item(0))
            
        if self.list_widget_p2.count() > 0:
            self.list_widget_p2.setCurrentRow(0)
            self.on_p2_pokemon_clicked(self.list_widget_p2.item(0))

    def populate_turns(self, match_data: dict):
        self.list_widget_turni.clear()
        self.list_widget_azioni.clear()
        
        self.current_hp = {}
        self.current_status = {}
        current_weather = None
        
        for turn in match_data.get("turns", []):
            turn_num = turn.get("turn_number", "?") if isinstance(turn, dict) else str(turn)
            
            # Condizioni Meteo / Tailwind ecc
            conds = []
            if turn.get("trick_room"): conds.append("Trick Room")
            if turn.get("p1_tailwind"): conds.append("Tailwind P1")
            if turn.get("p2_tailwind"): conds.append("Tailwind P2")
            if turn.get("weather"): conds.append(f"Clima: {turn['weather']}")
            
            cond_str = f" [{', '.join(conds)}]" if conds else ""
            
            item = QListWidgetItem(f"Turno {turn_num}{cond_str}")
            item.setData(Qt.UserRole, turn)
            self.list_widget_turni.addItem(item)
            
            # Simulated state pass for this turn's actions
            actions = turn.get("actions", [])
            for act in actions:
                tags_dict = act.get("tags", {})
                if isinstance(tags_dict, str):
                    try:
                        tags_dict = json.loads(tags_dict)
                    except:
                        tags_dict = {}
                
                try:
                    tags_dict_lower = {}
                    for k, v in tags_dict.items():
                        parsed_v = []
                        if isinstance(v, list):
                            for item in v:
                                if isinstance(item, str) and " | " in item:
                                    parsed_v.append(item.split(" | "))
                                elif isinstance(item, str):
                                    parsed_v.append([item])
                                else:
                                    parsed_v.append(item)
                        elif isinstance(v, str):
                            parsed_v = [v.split(" | ")]
                        else:
                            parsed_v = v
                        tags_dict_lower[str(k).lower()] = parsed_v
    
                    # WEATHER FROM TURN
                    turn_weather = turn.get("weather")
                    if turn_weather and turn_weather != "none":
                        current_weather = turn_weather
                    elif turn_weather == "none":
                        current_weather = None
                    elif "weather" in tags_dict_lower:
                        w_list = tags_dict_lower["weather"]
                        if w_list and isinstance(w_list, list):
                            w_event = w_list[0] if isinstance(w_list[0], list) else w_list
                            if len(w_event) > 0:
                                weather_val = str(w_event[0]).strip()
                                if weather_val != "none" and not weather_val.startswith("["):
                                    current_weather = weather_val
                                elif weather_val == "none":
                                    current_weather = None
    
                    for dmg_key in ["damage", "heal"]:
                        if dmg_key in tags_dict_lower:
                            dmg_list = tags_dict_lower[dmg_key]
                            if not dmg_list or not isinstance(dmg_list, list): continue
                            if not isinstance(dmg_list[0], list): dmg_list = [dmg_list]
                            for event in dmg_list:
                                if len(event) >= 2:
                                    slot_str = str(event[0]).split(":")[0].strip()
                                    hp_val = str(event[1]).strip()
                                    b_id = act.get("board_state", {}).get(slot_str, {}).get("id")
                                    if b_id is not None:
                                        self.current_hp[b_id] = hp_val
    
                    if "status" in tags_dict_lower:
                        st_list = tags_dict_lower["status"]
                        if st_list and isinstance(st_list, list):
                            if not isinstance(st_list[0], list): st_list = [st_list]
                            for event in st_list:
                                if len(event) >= 2:
                                    slot_str = str(event[0]).split(":")[0].strip()
                                    st_val = str(event[1]).strip()
                                    b_id = act.get("board_state", {}).get(slot_str, {}).get("id")
                                    if b_id is not None:
                                        self.current_status[b_id] = st_val
                                    
                    if "curestatus" in tags_dict_lower:
                        cst_list = tags_dict_lower["curestatus"]
                        if cst_list and isinstance(cst_list, list):
                            if not isinstance(cst_list[0], list): cst_list = [cst_list]
                            for event in cst_list:
                                if len(event) >= 1:
                                    slot_str = str(event[0]).split(":")[0].strip()
                                    b_id = act.get("board_state", {}).get(slot_str, {}).get("id")
                                    if b_id is not None:
                                        self.current_status[b_id] = ""
    
                    if "faint" in tags_dict_lower:
                        fnt_list = tags_dict_lower["faint"]
                        if fnt_list and isinstance(fnt_list, list):
                            if not isinstance(fnt_list[0], list): fnt_list = [fnt_list]
                            for event in fnt_list:
                                if len(event) >= 1:
                                    slot_str = str(event[0]).split(":")[0].strip()
                                    b_id = act.get("board_state", {}).get(slot_str, {}).get("id")
                                    if b_id is not None:
                                        self.current_hp[b_id] = "0 fnt"
                                        self.current_status[b_id] = ""
                except Exception as e:
                    print(f"Error parsing tags in populate_turns: {e}")
                
                act["simulated_state"] = {
                    "hp": copy.deepcopy(self.current_hp),
                    "status": copy.deepcopy(self.current_status),
                    "weather": current_weather
                }

        if self.list_widget_turni.count() > 0:
            self.list_widget_turni.setCurrentRow(0)
            self.on_turn_clicked(self.list_widget_turni.item(0))
            
            if self.list_widget_azioni.count() > 0:
                self.list_widget_azioni.setCurrentRow(0)
                self.on_action_clicked(self.list_widget_azioni.item(0))

    # ==========================================
    # CLICK EVENT HANDLERS
    # ==========================================

    def on_turn_clicked(self, item: QListWidgetItem):
        self.list_widget_azioni.clear()
        
        turn_data = item.data(Qt.UserRole)
        if not turn_data or not isinstance(turn_data, dict):
            return
            
        actions = turn_data.get("actions", [])
        for act in actions:
            action_desc = f"#{act.get('order', 0) + 1} {act.get('type', '?').upper()}"
            act_item = QListWidgetItem(action_desc)
            act_item.setData(Qt.UserRole, act)
            self.list_widget_azioni.addItem(act_item)

    def on_action_clicked(self, item: QListWidgetItem):
        action_data = item.data(Qt.UserRole)
        if not action_data or not isinstance(action_data, dict):
            return
            
        # 1. Update Pokemon In Campo
        board_state = action_data.get("board_state", {})
        sim_state = action_data.get("simulated_state", {"hp": {}, "status": {}, "weather": None})
        
        def format_board_slot(label_prefix, species_data, sim):
            species = species_data.get("name", "Vuoto") if isinstance(species_data, dict) else species_data
            if not species or species == "Vuoto":
                return f"<b>{label_prefix}</b><br>(Vuoto)"
            
            b_id = species_data.get("id") if isinstance(species_data, dict) else None
            
            hp_val = sim["hp"].get(b_id, "100/100")
            st_val = sim["status"].get(b_id, "")
            
            hp_pct = 100
            try:
                if hp_val.startswith("0 fnt") or "fnt" in hp_val:
                    hp_pct = 0
                else:
                    parts = hp_val.split()[0].split('/')
                    if len(parts) == 2:
                        hp_pct = int(float(parts[0]) / float(parts[1]) * 100)
            except:
                pass
                
            color = "#00ff00"
            if hp_pct < 50: color = "#ffff00"
            if hp_pct < 20: color = "#ff0000"
            if hp_pct == 0: color = "#555555"
            
            st_badge = f'<span style="background-color:#9900cc; padding: 1px 4px; border-radius: 3px; font-size:10px; font-weight:bold; color:white;">{st_val.upper()}</span>' if st_val else ''
            
            # Use an HTML table for the HP bar because QLabel RichText does not support CSS width/height on div
            bar = f'<table width="100%" height="8" cellspacing="0" cellpadding="0" style="margin-top:4px;"><tr><td width="{hp_pct}%" bgcolor="{color}"></td><td width="{100-hp_pct}%" bgcolor="#444444"></td></tr></table>'
            info = f'<div style="font-size:11px; margin-top:2px; color:#333;">{hp_val} {st_badge}</div>'
            
            icon_path = get_pokemon_icon_path(species)
            img_html = f"<img src='{icon_path}' width='64'><br>" if icon_path else ""
            
            return f"<b>{label_prefix}</b><br>{img_html}{species}<br>{bar}{info}"

        self.lbl_p1a.setText(format_board_slot("P1a", board_state.get("p1a", "Vuoto"), sim_state))
        self.lbl_p1b.setText(format_board_slot("P1b", board_state.get("p1b", "Vuoto"), sim_state))
        self.lbl_p2a.setText(format_board_slot("P2a", board_state.get("p2a", "Vuoto"), sim_state))
        self.lbl_p2b.setText(format_board_slot("P2b", board_state.get("p2b", "Vuoto"), sim_state))
        
        self.list_condizioni_p1.clear()
        self.list_condizioni_generali.clear()
        self.list_condizioni_p2.clear()

        weather_event = sim_state.get("weather")
        if weather_event:
            # Se è una lista (da tags), prendiamo il primo elemento
            if isinstance(weather_event, list):
                weather_name = weather_event[0]
                extra_info = weather_event[1:] if len(weather_event) > 1 else []
            else:
                # Se è una stringa (da turn.weather)
                weather_name = weather_event
                extra_info = []

            bg_colors = {
                "SunnyDay": "#ffcccc", 
                "RainDance": "#cce5ff", 
                "Snow": "#e6f2ff", 
                "Sandstorm": "#ffe6cc" 
            }
            board_bg = bg_colors.get(weather_name, "#222222") # scuro di default
            self.frame_pokemon_in_campo.setStyleSheet(f"background-color: {board_bg}; border: 1px solid #ccc; border-radius: 8px;")
            
            ui_str = f"Meteo: {weather_name}"
            
            from_str = ""
            of_str = ""
            for tag_part in extra_info:
                if tag_part.startswith("[from]"):
                    from_str = tag_part.replace("[from]", "").strip()
                elif tag_part.startswith("[of]"):
                    of_str = tag_part.replace("[of]", "").strip()
            
            if from_str or of_str:
                ui_str += " (Evocato da:"
                if from_str:
                    ui_str += f" {from_str}"
                if of_str:
                    ui_str += f" [{of_str}]"
                ui_str += ")"
            
            self.list_condizioni_generali.addItem(ui_str)
        else:
            self.frame_pokemon_in_campo.setStyleSheet("background-color: #222222; border: 1px solid #ccc; border-radius: 8px;")
        
        # 2. Update Attributes
        act_type = action_data.get('type', '')
        details_text = action_data.get('details', 'N/A')
        
        if act_type == 'move':
            details_text = f'<a href="move:{details_text}" style="color:#0055ff; text-decoration:none;">{details_text}</a>'
        elif act_type == 'ability':
            details_text = f'<a href="ability:{details_text}" style="color:#0055ff; text-decoration:none;">{details_text}</a>'
        elif act_type == 'item':
            details_text = f'<a href="item:{details_text}" style="color:#0055ff; text-decoration:none;">{details_text}</a>'
            
        html = f"""
        <b style="color: #444;">Attore:</b> <span>{action_data.get('actor', 'N/A')}</span><br>
        <b style="color: #444;">Bersaglio:</b> <span>{action_data.get('target', 'N/A')}</span><br>
        <b style="color: #444;">Dettagli:</b> <span>{details_text}</span>
        """
        self.txt_attr.setHtml(html)
        
        # 3. Update Tags
        self.tree_widget_tags.clear()
        tags = action_data.get("tags", {})
        
        from PySide6.QtWidgets import QTreeWidgetItem
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = {"raw": tags}
                
        for key, val in tags.items():
            tag_item = QTreeWidgetItem(self.tree_widget_tags, [str(key).upper()])
            if isinstance(val, list):
                for ev in val:
                    if isinstance(ev, list):
                        QTreeWidgetItem(tag_item, [" | ".join(ev)])
                    else:
                        QTreeWidgetItem(tag_item, [str(ev)])
            else:
                QTreeWidgetItem(tag_item, [str(val)])
            tag_item.setExpanded(True)

    def on_p1_pokemon_clicked(self, item: QListWidgetItem):
        self._update_pokemon_dati(self.lbl_dati_p1, self.frame_img_p1, item.data(Qt.UserRole))
        
    def on_p2_pokemon_clicked(self, item: QListWidgetItem):
        self._update_pokemon_dati(self.lbl_dati_p2, self.frame_img_p2, item.data(Qt.UserRole))
        
    def _update_pokemon_dati(self, label_widget: QLabel, img_widget: QLabel, poke_data):
        if not isinstance(poke_data, dict):
            label_widget.setText("Dati non disponibili")
            img_widget.clear()
            return
            
        species = poke_data.get("species") or "N/A"
        item_held = poke_data.get("item") or "N/A"
        ability = poke_data.get("ability") or "N/A"
        tera_type = poke_data.get("tera_type") or "N/A"
        nature = poke_data.get("nature") or "N/A"
        base_stats = poke_data.get("base_stats", {})
        moves = poke_data.get("moves", [])
        
        # Set Image
        icon_path = get_pokemon_icon_path(species)
        if icon_path:
            img_widget.setPixmap(QPixmap(icon_path).scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            img_widget.setText("(Nessuna Immagine)")
        
        # Set Stats and Moves
        stats_str = ", ".join([f"{k}: {v}" for k, v in base_stats.items()]) if base_stats else "N/A"
        moves_str = "<br>&nbsp;&nbsp;&bull; ".join(moves) if moves else "N/A"
        if moves_str != "N/A":
            moves_str = "<br>&nbsp;&nbsp;&bull; " + moves_str
            
        info = (
            f"<b>Specie:</b> {species}<br>"
            f"<b>Strumento:</b> {item_held}<br>"
            f"<b>Abilità:</b> {ability}<br>"
            f"<b>Teratipo:</b> {tera_type}<br>"
            f"<b>Natura:</b> {nature}<br>"
            f"<b>Statistiche Base:</b><br>{stats_str}<br>"
            f"<b>Mosse:</b>{moves_str}"
        )
        label_widget.setText(info)
