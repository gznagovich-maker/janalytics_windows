import os
import json
import urllib.request
import copy
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSplitter, QFrame, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QTextBrowser, QTreeWidget, QTreeWidgetItem,
    QTabWidget, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QColor, QPixmap
from database.repository_v2 import get_match_details_v2

import matplotlib
matplotlib.use('qtagg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from src.domain.replay_analytics_service import ReplayAnalyticsService

# ──────────────────────────────────────────────────────────────────────────────
# COSTANTI TAG → UI
# ──────────────────────────────────────────────────────────────────────────────

WEATHER_BG = {
    "SunnyDay":   "#3d1a00",
    "RainDance":  "#001933",
    "Snow":       "#1a2a3d",
    "Snowscape":  "#1a2a3d",
    "Hail":       "#1a2a3d",
    "Sandstorm":  "#3d2800",
    "PrimordialSea":    "#001440",
    "DesolateLand":     "#4d1f00",
    "StrongWinds":      "#1a1a2e",
}
WEATHER_ICON = {
    "SunnyDay":   "☀️ Sole",
    "RainDance":  "🌧️ Pioggia",
    "Snow":       "❄️ Neve",
    "Snowscape":  "❄️ Bufera di neve",
    "Hail":       "🧊 Grandine",
    "Sandstorm":  "🌪️ Tempesta di Sabbia",
    "PrimordialSea":   "🌊 Mare Primordiale",
    "DesolateLand":    "🌋 Terra Desolata",
    "StrongWinds":     "💨 Turbolenza",
}
TERRAIN_BG = {
    "electricterrain": "#1a1a00",
    "grassyterrain":   "#001a00",
    "mistyterrain":    "#1a001a",
    "psychicterrain":  "#0d000d",
}
TERRAIN_ICON = {
    "electricterrain": "⚡ Terreno Elettrico",
    "grassyterrain":   "🌿 Terreno Erboso",
    "mistyterrain":    "🌸 Terreno Nibbioso",
    "psychicterrain":  "🔮 Terreno Psichico",
}
STATUS_COLORS = {
    "brn": "#c0392b", "par": "#f1c40f", "slp": "#7f8c8d",
    "frz": "#2980b9", "psn": "#8e44ad", "tox": "#6c3483",
}
STATUS_LABELS = {
    "brn": "BRN 🔥", "par": "PAR ⚡", "slp": "SLP 💤",
    "frz": "FRZ 🧊", "psn": "PSN ☠️", "tox": "TOX ☠️",
}
STAT_NAMES = {
    "atk": "Attacco", "def": "Difesa", "spa": "Att.Sp.",
    "spd": "Dif.Sp.", "spe": "Velocità", "acc": "Precisione", "eva": "Elusione",
}
ACTION_ICONS = {
    "move":   "⚔️",
    "switch": "🔄",
    "cant":   "🚫",
    "faint":  "💀",
}


from src.utils.icon_utils import get_pokemon_icon_path


# ──────────────────────────────────────────────────────────────────────────────
class ReplayAnalyzerUI(QWidget):
    back_requested = Signal()
    link_clicked = Signal(str)
    title_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Replay Analyzer")
        self.match_data = {}
        self._sim_states = {}  # (turn_num, action_order) -> simulated state dict
        self.setup_ui()
        self.setup_connections()

    # ── SETUP UI ──────────────────────────────────────────────────────────────

    def setup_ui(self):
        self.base_layout = QVBoxLayout(self)
        self.base_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.scroll_widget = QWidget()
        self.main_layout = QVBoxLayout(self.scroll_widget)
        self.main_layout.setSpacing(4)
        self.main_layout.setContentsMargins(6, 6, 6, 6)
        
        self.scroll_area.setWidget(self.scroll_widget)
        self.base_layout.addWidget(self.scroll_area)

        # Top bar
        top = QHBoxLayout()
        self.btn_back = QPushButton("🔙 Indietro")
        self.btn_back.clicked.connect(self.back_requested.emit)
        top.addWidget(self.btn_back)
        top.addStretch()
        self.main_layout.addLayout(top)

        # Middle (team panels)
        mid = QHBoxLayout()
        self.p1_area_layout = QVBoxLayout()
        self.lbl_p1_info = QLabel("Giocatore 1")
        self.lbl_p1_info.setStyleSheet("font-size: 16px; font-weight: bold; color: #B8A9B7;")
        self.p1_area_layout.addWidget(self.lbl_p1_info)
        p1_frames = QHBoxLayout()
        self.frame_img_p1 = QLabel()
        self.frame_img_p1.setAlignment(Qt.AlignCenter)
        self.frame_img_p1.setStyleSheet("background:transparent; border:none;")
        self.frame_img_p1.setFixedSize(100, 100)
        self.frame_dati_p1 = QFrame()
        self.frame_dati_p1.setFrameShape(QFrame.StyledPanel)
        self.lbl_dati_p1 = QLabel("Seleziona un Pokémon")
        self.lbl_dati_p1.setWordWrap(True)
        self.lbl_dati_p1.setTextFormat(Qt.RichText)
        QVBoxLayout(self.frame_dati_p1).addWidget(self.lbl_dati_p1)
        p1_frames.addWidget(self.frame_img_p1)
        p1_frames.addWidget(self.frame_dati_p1)
        self.list_widget_p1 = QListWidget()
        self.list_widget_p1.setMaximumHeight(100)
        self.p1_area_layout.addLayout(p1_frames)
        self.p1_area_layout.addWidget(self.list_widget_p1)

        self.p2_area_layout = QVBoxLayout()
        self.lbl_p2_info = QLabel("Giocatore 2")
        self.lbl_p2_info.setStyleSheet("font-size: 16px; font-weight: bold; color: #C2BFBC;")
        self.p2_area_layout.addWidget(self.lbl_p2_info)
        p2_frames = QHBoxLayout()
        self.frame_dati_p2 = QFrame()
        self.frame_dati_p2.setFrameShape(QFrame.StyledPanel)
        self.lbl_dati_p2 = QLabel("Seleziona un Pokémon")
        self.lbl_dati_p2.setWordWrap(True)
        self.lbl_dati_p2.setTextFormat(Qt.RichText)
        QVBoxLayout(self.frame_dati_p2).addWidget(self.lbl_dati_p2)
        self.frame_img_p2 = QLabel()
        self.frame_img_p2.setAlignment(Qt.AlignCenter)
        self.frame_img_p2.setStyleSheet("background:transparent; border:none;")
        self.frame_img_p2.setFixedSize(100, 100)
        p2_frames.addWidget(self.frame_dati_p2)
        p2_frames.addWidget(self.frame_img_p2)
        self.list_widget_p2 = QListWidget()
        self.list_widget_p2.setMaximumHeight(100)
        self.p2_area_layout.addLayout(p2_frames)
        self.p2_area_layout.addWidget(self.list_widget_p2)

        mid.addLayout(self.p1_area_layout)
        mid.addLayout(self.p2_area_layout)
        self.main_layout.addLayout(mid)

        # Bottom tabs
        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.setMinimumHeight(500)
        self.main_layout.addWidget(self.bottom_tabs, 1)

        # Prima tab: Event Log e Board
        self.tab_log = QWidget()
        tab_log_lay = QVBoxLayout(self.tab_log)
        tab_log_lay.setContentsMargins(0,0,0,0)

        # Bottom splitter (dentro tab 1)
        self.bottom_splitter = QSplitter(Qt.Horizontal)

        # Left pane: Turns + Actions
        left_w = QWidget()
        left_lay = QVBoxLayout(left_w)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(QLabel("Turni:"))
        self.list_widget_turni = QListWidget()
        left_lay.addWidget(self.list_widget_turni)
        left_lay.addWidget(QLabel("Azioni nel Turno:"))
        self.list_widget_azioni = QListWidget()
        left_lay.addWidget(self.list_widget_azioni)

        # Center pane: Board + Conditions
        center_w = QWidget()
        center_lay = QVBoxLayout(center_w)
        center_lay.setContentsMargins(0, 0, 0, 0)
        self.frame_pokemon_in_campo = QFrame()
        self.frame_pokemon_in_campo.setFrameShape(QFrame.StyledPanel)
        self.frame_pokemon_in_campo.setStyleSheet(
            "background:#211924; border:none; border-radius:12px; padding: 8px;")
        self.pokemon_grid = QGridLayout(self.frame_pokemon_in_campo)
        self.pokemon_grid.setSpacing(12)
        self.lbl_p1a = QLabel("P1a<br><i>(Vuoto)</i>")
        self.lbl_p1b = QLabel("P1b<br><i>(Vuoto)</i>")
        self.lbl_p2a = QLabel("P2a<br><i>(Vuoto)</i>")
        self.lbl_p2b = QLabel("P2b<br><i>(Vuoto)</i>")
        p1_style = ("background:rgba(182,250,245,0.1);color:#B8A9B7;"
                    "border:none;border-radius:8px;padding:12px;")
        p2_style = ("background:rgba(250,183,240,0.1);color:#C2BFBC;"
                    "border:none;border-radius:8px;padding:12px;")
        for lbl in (self.lbl_p1a, self.lbl_p1b):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(p1_style)
            lbl.setTextFormat(Qt.RichText)
        for lbl in (self.lbl_p2a, self.lbl_p2b):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(p2_style)
            lbl.setTextFormat(Qt.RichText)
        # P2 on top (opponent), P1 on bottom (player)
        self.pokemon_grid.addWidget(self.lbl_p2a, 0, 0)
        self.pokemon_grid.addWidget(self.lbl_p2b, 0, 1)
        self.pokemon_grid.addWidget(self.lbl_p1a, 1, 0)
        self.pokemon_grid.addWidget(self.lbl_p1b, 1, 1)
        center_lay.addWidget(self.frame_pokemon_in_campo, 3)

        cond_lay = QHBoxLayout()
        p1c = QVBoxLayout()
        p1c.addWidget(QLabel("Cond. P1:"))
        self.list_condizioni_p1 = QListWidget()
        self.list_condizioni_p1.setMinimumHeight(120)
        p1c.addWidget(self.list_condizioni_p1)
        gc = QVBoxLayout()
        gc.addWidget(QLabel("Globali:"))
        self.list_condizioni_generali = QListWidget()
        self.list_condizioni_generali.setMinimumHeight(120)
        gc.addWidget(self.list_condizioni_generali)
        p2c = QVBoxLayout()
        p2c.addWidget(QLabel("Cond. P2:"))
        self.list_condizioni_p2 = QListWidget()
        self.list_condizioni_p2.setMinimumHeight(120)
        p2c.addWidget(self.list_condizioni_p2)
        cond_lay.addLayout(p1c)
        cond_lay.addLayout(gc)
        cond_lay.addLayout(p2c)
        center_lay.addLayout(cond_lay, 1)

        # Right pane
        right_w = QWidget()
        right_lay = QVBoxLayout(right_w)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.addWidget(QLabel("Attributi Azione:"))
        self.txt_attr = QTextBrowser()
        self.txt_attr.setOpenExternalLinks(False)
        self.txt_attr.anchorClicked.connect(self.on_txt_state_anchor_clicked)
        right_lay.addWidget(self.txt_attr, 2)
        right_lay.addWidget(QLabel("Tags (Dati Tecnici):"))
        self.tree_widget_tags = QTreeWidget()
        self.tree_widget_tags.setHeaderHidden(True)
        right_lay.addWidget(self.tree_widget_tags, 3)

        self.bottom_splitter.addWidget(left_w)
        self.bottom_splitter.addWidget(center_w)
        self.bottom_splitter.addWidget(right_w)
        self.bottom_splitter.setSizes([260, 380, 300])
        tab_log_lay.addWidget(self.bottom_splitter)
        self.bottom_tabs.addTab(self.tab_log, "Log / Eventi")

        # Seconda tab: Grafici & Metriche
        self.tab_grafici = QWidget()
        tab_grafici_lay = QVBoxLayout(self.tab_grafici)
        
        lbl_spiegazione = QLabel(
            "<b>Snapshot di Stato (Differenziale HP Ponderato)</b>: Indica il vantaggio in salute pesato per i boost.<br>"
            "<i>Esempio</i>: Un Pokémon a 50% HP con +2 in Attacco conta di più di uno a 50% senza boost, riflettendo la pericolosità.<br><br>"
            "<b>Indice di Vantaggio (Momentum)</b>: Funzione euristica che somma Differenziale HP, vantaggio velocità e posizionamento.<br>"
            "<i>Esempio</i>: Un valore positivo indica che il Giocatore 1 ha il controllo tattico della scacchiera."
        )
        lbl_spiegazione.setWordWrap(True)
        lbl_spiegazione.setStyleSheet("background-color: transparent; border: none; padding: 0px;")
        tab_grafici_lay.addWidget(lbl_spiegazione)

        self.figure = Figure(figsize=(8, 4), facecolor='#121212')
        self.canvas = FigureCanvas(self.figure)
        tab_grafici_lay.addWidget(self.canvas)
        self.bottom_tabs.addTab(self.tab_grafici, "Grafici & Metriche")

    # ── CONNECTIONS ───────────────────────────────────────────────────────────

    def setup_connections(self):
        self.list_widget_turni.currentItemChanged.connect(
            lambda curr, prev: self.on_turn_clicked(curr) if curr else None)
        self.list_widget_azioni.currentItemChanged.connect(
            lambda curr, prev: self.on_action_clicked(curr) if curr else None)
        self.list_widget_turni.itemClicked.connect(self.on_turn_clicked)
        self.list_widget_azioni.itemClicked.connect(self.on_action_clicked)
        self.list_widget_p1.itemClicked.connect(self.on_p1_pokemon_clicked)
        self.list_widget_p2.itemClicked.connect(self.on_p2_pokemon_clicked)

    def on_txt_state_anchor_clicked(self, url: QUrl):
        self.link_clicked.emit(url.toString())

    # ── DISPLAY MATCH ─────────────────────────────────────────────────────────

    def display_match(self, match_id: str):
        self.match_data = get_match_details_v2(match_id)
        if not self.match_data:
            return
        fmt = self.match_data.get("format", "Regolamento Sconosciuto")
        self.title_changed.emit(f"Match: {match_id} | {fmt}")
        # Reset BEFORE populating so auto-select in populate_turns is not wiped
        self._reset_panels()
        self.populate_teams(self.match_data)
        self.populate_turns(self.match_data)
        self.update_graphs(self.match_data)

    def update_graphs(self, match_data: dict):
        service = ReplayAnalyticsService(match_data)
        series = service.generate_turn_series()
        
        self.figure.clear()
        
        ax1 = self.figure.add_subplot(211)
        ax1.set_facecolor('#121212')
        ax1.tick_params(colors='white')
        for spine in ax1.spines.values(): spine.set_color('#333333')
        
        ax1.plot(series["turns"], series["delta_hp"], marker='o', color='#B8A9B7', label='ΔHP Ponderato')
        ax1.set_title("Snapshot di Stato (Vantaggio HP P1)", color='white')
        ax1.axhline(0, color='gray', linestyle='--')
        ax1.legend(loc='best', facecolor='#121212', edgecolor='#333333', labelcolor='white')
        
        ax2 = self.figure.add_subplot(212)
        ax2.set_facecolor('#121212')
        ax2.tick_params(colors='white')
        for spine in ax2.spines.values(): spine.set_color('#333333')
        
        ax2.bar(series["turns"], series["momentum"], color=['#8A7D89' if m > 0 else '#8c3b3b' for m in series["momentum"]])
        ax2.set_title("Indice di Vantaggio (Momentum P1)", color='white')
        ax2.axhline(0, color='gray', linestyle='--')
        
        self.figure.tight_layout()
        self.canvas.draw()

    def _reset_panels(self):
        self.list_widget_azioni.clear()
        self.txt_attr.clear()
        self.tree_widget_tags.clear()
        for lbl, txt in ((self.lbl_p1a, "P1a"), (self.lbl_p1b, "P1b"),
                         (self.lbl_p2a, "P2a"), (self.lbl_p2b, "P2b")):
            lbl.setText(f"<b>{txt}</b><br><i>(Vuoto)</i>")
        self.list_condizioni_p1.clear()
        self.list_condizioni_generali.clear()
        self.list_condizioni_p2.clear()

    # ── TEAM ──────────────────────────────────────────────────────────────────

    def populate_teams(self, match_data: dict):
        self.list_widget_p1.clear()
        self.list_widget_p2.clear()
        teams = match_data.get("teams", {})
        p1 = teams.get("p1", {})
        p2 = teams.get("p2", {})
        self.lbl_p1_info.setText(
            f"Allenatore: {p1.get('trainer','?')} | ELO: {p1.get('rating','N/A')}")
        self.lbl_p2_info.setText(
            f"Allenatore: {p2.get('trainer','?')} | ELO: {p2.get('rating','N/A')}")
        for poke in p1.get("pokemon", []):
            it = QListWidgetItem(poke.get("species", "?") if isinstance(poke, dict) else str(poke))
            it.setData(Qt.UserRole, poke)
            self.list_widget_p1.addItem(it)
        for poke in p2.get("pokemon", []):
            it = QListWidgetItem(poke.get("species", "?") if isinstance(poke, dict) else str(poke))
            it.setData(Qt.UserRole, poke)
            self.list_widget_p2.addItem(it)
        if self.list_widget_p1.count():
            self.list_widget_p1.setCurrentRow(0)
            self.on_p1_pokemon_clicked(self.list_widget_p1.item(0))
        if self.list_widget_p2.count():
            self.list_widget_p2.setCurrentRow(0)
            self.on_p2_pokemon_clicked(self.list_widget_p2.item(0))

    # ── TAG HELPERS ───────────────────────────────────────────────────────────

    def _get_tags(self, act: dict) -> dict:
        """Return tags dict from action, keys lowercased.
        DB stores: {"damage": [["p1a: Ttar", "200/350"], ...], "weather": [["SunnyDay", "[from] ability: Drought", "[of] p1a: Char"]]}
        No re-splitting needed."""
        tags = act.get("raw_tags", {})
        if not tags:
            return {}
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                return {}
        if not isinstance(tags, dict):
            return {}
        return {str(k).lower(): v for k, v in tags.items()}

    def _get_events(self, tags: dict, key: str) -> list:
        """Return list of events for a tag key. Each event is a list[str].
        DB format already has nested lists, e.g. [["p1a: Ttar", "200/350"], ...]"""
        raw = tags.get(key, [])
        if not raw or not isinstance(raw, list):
            return []
        result = []
        for ev in raw:
            if isinstance(ev, list):
                result.append([str(x) for x in ev])
            elif isinstance(ev, str):
                result.append([ev])
        return result

    def _slot_key(self, ev_field: str) -> str:
        """Extract 'p1a' from 'p1a: Tyranitar'."""
        return ev_field.split(":")[0].strip()

    def _b_id(self, slot_key: str, board: dict):
        """Return build_id from board_state given slot key like 'p1a'."""
        slot_info = board.get(slot_key, {})
        return slot_info.get("id") if isinstance(slot_info, dict) else None

    # ── POPULATE TURNS (EVENT SOURCING) ───────────────────────────────────────

    def populate_turns(self, match_data: dict):
        self.list_widget_turni.clear()
        self.list_widget_azioni.clear()
        self._sim_states = {}   # Reset: (turn_num, action_order) -> sim dict

        # Running simulated state across ALL turns/actions in chronological order
        sim = {
            "hp":             {},     # {build_id: "cur/max"}
            "status":         {},     # {build_id: "brn"|"par"|...}
            "boosts":         {},     # {build_id: {"atk": +1, "spe": -1, ...}}
            "weather":        None,   # list e.g. ["SunnyDay","[from] ability:...","[of] p1a:..."] or None
            "terrain":        None,   # list or None
            "p1_tailwind":    False,
            "p2_tailwind":    False,
            "trick_room":     False,
            "p1_reflect":     False,
            "p1_lightscreen": False,
            "p1_auroraveil":  False,
            "p2_reflect":     False,
            "p2_lightscreen": False,
            "p2_auroraveil":  False,
            "mega":           {},     # {build_id: True}
            "tera":           {},     # {build_id: type_str}
            "enditem":        {},     # {build_id: item_str}
        }

        for turn in match_data.get("turns", []):
            turn_num = turn.get("turn_number", 0)
            conds = []
            if sim["weather"]:
                wn = sim["weather"][0] if isinstance(sim["weather"], list) else sim["weather"]
                conds.append(WEATHER_ICON.get(wn, wn))
            if sim["terrain"]:
                tn = sim["terrain"][0] if isinstance(sim["terrain"], list) else sim["terrain"]
                conds.append(TERRAIN_ICON.get(tn.lower(), tn))
            if sim["trick_room"]:    conds.append("🔁 Trick Room")
            if sim["p1_tailwind"]:   conds.append("💨 Tailwind P1")
            if sim["p2_tailwind"]:   conds.append("💨 Tailwind P2")
            cond_str = f"  [{', '.join(conds)}]" if conds else ""
            turn_item = QListWidgetItem(f"Turno {turn_num}{cond_str}")
            turn_item.setData(Qt.UserRole, turn)
            self.list_widget_turni.addItem(turn_item)

            # board_state is at turn level (also injected into actions by repo)
            board = turn.get("board_state", {})
            for act in turn.get("actions", []):
                action_order = act.get("order", 0)
                tags = self._get_tags(act)
                try:
                    # Weather
                    for ev in self._get_events(tags, "weather"):
                        if ev:
                            wname = ev[0].strip()
                            if wname.lower() == "none":
                                sim["weather"] = None
                            elif not wname.startswith("["):
                                sim["weather"] = ev

                    # Fieldstart / Fieldend (Terrain, Trick Room)
                    for ev in self._get_events(tags, "fieldstart"):
                        if ev:
                            field = ev[0].lower()
                            if "trickroom" in field or "trick room" in field:
                                sim["trick_room"] = True
                            for tk in TERRAIN_ICON:
                                if tk in field:
                                    sim["terrain"] = ev

                    for ev in self._get_events(tags, "fieldend"):
                        if ev:
                            field = ev[0].lower()
                            if "trickroom" in field or "trick room" in field:
                                sim["trick_room"] = False
                            for tk in TERRAIN_ICON:
                                if tk in field:
                                    sim["terrain"] = None

                    # Sidestart / Sideend (Tailwind, Reflect, Light Screen)
                    for ev in self._get_events(tags, "sidestart"):
                        if len(ev) >= 2:
                            p = "p1" if ev[0].strip().startswith("p1") else "p2"
                            effect = ev[1].lower().split(":")[-1].strip()
                            if "tailwind" in effect:         sim[f"{p}_tailwind"] = True
                            elif "reflect" in effect:        sim[f"{p}_reflect"] = True
                            elif "lightscreen" in effect or "light screen" in effect:
                                sim[f"{p}_lightscreen"] = True
                            elif "auroraveil" in effect or "aurora veil" in effect:
                                sim[f"{p}_auroraveil"] = True

                    for ev in self._get_events(tags, "sideend"):
                        if len(ev) >= 2:
                            p = "p1" if ev[0].strip().startswith("p1") else "p2"
                            effect = ev[1].lower().split(":")[-1].strip()
                            if "tailwind" in effect:         sim[f"{p}_tailwind"] = False
                            elif "reflect" in effect:        sim[f"{p}_reflect"] = False
                            elif "lightscreen" in effect or "light screen" in effect:
                                sim[f"{p}_lightscreen"] = False
                            elif "auroraveil" in effect or "aurora veil" in effect:
                                sim[f"{p}_auroraveil"] = False

                    # HP (damage / heal)
                    for key in ("damage", "heal"):
                        for ev in self._get_events(tags, key):
                            if len(ev) >= 2:
                                sk = self._slot_key(ev[0])
                                bid = self._b_id(sk, board)
                                if bid is not None:
                                    sim["hp"][bid] = ev[1].strip()

                    # Status / Curestatus
                    for ev in self._get_events(tags, "status"):
                        if len(ev) >= 2:
                            bid = self._b_id(self._slot_key(ev[0]), board)
                            if bid is not None:
                                sim["status"][bid] = ev[1].strip()

                    for ev in self._get_events(tags, "curestatus"):
                        if ev:
                            bid = self._b_id(self._slot_key(ev[0]), board)
                            if bid is not None:
                                sim["status"].pop(bid, None)

                    # Faint
                    for ev in self._get_events(tags, "faint"):
                        if ev:
                            bid = self._b_id(self._slot_key(ev[0]), board)
                            if bid is not None:
                                sim["hp"][bid] = "0 fnt"
                                sim["status"].pop(bid, None)
                                sim["boosts"].pop(bid, None)

                    # Boost / Unboost
                    for key, sign in (("boost", 1), ("unboost", -1)):
                        for ev in self._get_events(tags, key):
                            if len(ev) >= 3:
                                bid = self._b_id(self._slot_key(ev[0]), board)
                                stat = ev[1].lower()
                                try:
                                    stages = int(ev[2]) * sign
                                except ValueError:
                                    stages = sign
                                if bid is not None:
                                    if bid not in sim["boosts"]:
                                        sim["boosts"][bid] = {}
                                    sim["boosts"][bid][stat] = (
                                        sim["boosts"][bid].get(stat, 0) + stages)

                    for ev in self._get_events(tags, "clearallboost"):
                        sim["boosts"] = {}

                    # Mega / Tera
                    for ev in self._get_events(tags, "mega"):
                        if ev:
                            bid = self._b_id(self._slot_key(ev[0]), board)
                            if bid is not None:
                                sim["mega"][bid] = True

                    for ev in self._get_events(tags, "terastallize"):
                        if len(ev) >= 2:
                            bid = self._b_id(self._slot_key(ev[0]), board)
                            if bid is not None:
                                sim["tera"][bid] = ev[1].strip()

                    # Enditem
                    for ev in self._get_events(tags, "enditem"):
                        if len(ev) >= 2:
                            bid = self._b_id(self._slot_key(ev[0]), board)
                            if bid is not None:
                                sim["enditem"][bid] = ev[1].strip()

                except Exception as e:
                    print(f"[populate_turns] {act.get('type','?')}: {e}")

                # Store simulated state in class-level dict — avoids Qt setData/data reference issues
                self._sim_states[(turn_num, action_order)] = copy.deepcopy(sim)

        if self.list_widget_turni.count():
            self.list_widget_turni.setCurrentRow(0)
            self.on_turn_clicked(self.list_widget_turni.item(0))
            if self.list_widget_azioni.count():
                self.list_widget_azioni.setCurrentRow(0)
                self.on_action_clicked(self.list_widget_azioni.item(0))

    # ── ON TURN CLICKED ───────────────────────────────────────────────────────

    def on_turn_clicked(self, item: QListWidgetItem):
        self.list_widget_azioni.clear()
        turn_data = item.data(Qt.UserRole)
        if not turn_data or not isinstance(turn_data, dict):
            return
        turn_num = turn_data.get("turn_number", 0)
        for act in turn_data.get("actions", []):
            act_type = act.get("type", "?")
            details = act.get("details", "")
            icon = ACTION_ICONS.get(act_type, "▪️")
            order = act.get("order", 0) + 1
            label = f"{icon} #{order} {act_type.upper()}"
            if details:
                label += f" — {details}"
            act_item = QListWidgetItem(label)
            # Store (action_dict, turn_num, action_order) so on_action_clicked
            # can read board from action_dict AND look up sim from self._sim_states
            act_item.setData(Qt.UserRole, (act, turn_num, act.get("order", 0)))
            colors = {"move": "#141414", "switch": "#1a1a1a",
                      "cant": "#0a0a0a", "faint": "#2a1414"}
            act_item.setBackground(QColor(colors.get(act_type, "#1A1A1A")))
            self.list_widget_azioni.addItem(act_item)

    # ── ON ACTION CLICKED ─────────────────────────────────────────────────────

    def on_action_clicked(self, item: QListWidgetItem):
        raw = item.data(Qt.UserRole)
        if not raw:
            return
        # Support both old plain-dict format and new (action_dict, turn_num, action_order) tuple
        if isinstance(raw, tuple):
            action_data, turn_num, action_order = raw
        else:
            action_data = raw
            turn_num = action_data.get("turn_number", 0)
            action_order = action_data.get("order", 0)

        if not isinstance(action_data, dict):
            return

        # board_state is baked into action at repository level
        board = action_data.get("board_state", {})
        # sim state is stored in class-level dict — immune to Qt setData reference issues
        sim = self._sim_states.get((turn_num, action_order), {})
        hp_map     = sim.get("hp", {})
        status_map = sim.get("status", {})
        boost_map  = sim.get("boosts", {})
        mega_map   = sim.get("mega", {})
        tera_map   = sim.get("tera", {})
        enditem_map = sim.get("enditem", {})

        # ── 1. Board slots ────────────────────────────────────────────────────
        def format_slot(prefix, slot_data):
            if not isinstance(slot_data, dict):
                return f"<b>{prefix}</b><br><i style='color:#666'>(Vuoto)</i>"
            species = slot_data.get("species", "")
            if not species or species == "Vuoto":
                return f"<b>{prefix}</b><br><i style='color:#666'>(Vuoto)</i>"
            bid = slot_data.get("id")
            hp_raw  = hp_map.get(bid, "")
            st_val  = status_map.get(bid, "")
            boosts  = boost_map.get(bid, {})
            is_mega = mega_map.get(bid, False)
            tera    = tera_map.get(bid, "")
            no_item = bid in enditem_map

            hp_pct = 100
            hp_display = hp_raw if hp_raw else "100%"
            try:
                if "fnt" in hp_raw:
                    hp_pct, hp_display = 0, "💀 KO"
                elif "/" in hp_raw:
                    a, b = hp_raw.split()[0].split("/")
                    hp_pct = max(0, min(100,
                                        int(round(float(a) / float(b) * 100))))
                    hp_display = hp_raw.split()[0]
            except Exception:
                hp_pct = 100

            bar_color = ("#27ae60" if hp_pct > 50
                         else "#f39c12" if hp_pct > 20
                         else "#e74c3c")
            if hp_pct == 0:
                bar_color = "#555"

            bar = (f'<table width="100%" height="6" cellspacing="0" cellpadding="0"'
                   f' style="margin:2px 0;">'
                   f'<tr><td width="{hp_pct}%" bgcolor="{bar_color}"></td>'
                   f'<td width="{100 - hp_pct}%" bgcolor="#333"></td></tr></table>')

            st_html = ""
            if st_val:
                bg = STATUS_COLORS.get(st_val.lower(), "#555")
                lb = STATUS_LABELS.get(st_val.lower(), st_val.upper())
                st_html = (f' <span style="background:{bg};color:white;font-size:9px;'
                           f'padding:1px 3px;border-radius:3px;">{lb}</span>')

            boost_html = ""
            for stat, stages in boosts.items():
                if stages == 0:
                    continue
                arrow = "▲" if stages > 0 else "▼"
                col = "#4fc3f7" if stages > 0 else "#ef9a9a"
                sname = STAT_NAMES.get(stat, stat.upper())
                boost_html += (f'<span style="color:{col};font-size:9px;margin-right:2px;">'
                               f'{arrow}{abs(stages)} {sname}</span>')

            badge_html = ""
            if is_mega:
                badge_html += ('<span style="background:#ff6f00;color:white;font-size:9px;'
                               'padding:1px 3px;border-radius:3px;margin-right:2px;">MEGA</span>')
            if tera:
                badge_html += (f'<span style="background:#7b1fa2;color:white;font-size:9px;'
                               f'padding:1px 3px;border-radius:3px;">TERA:{tera}</span>')
            if no_item:
                badge_html += ('<span style="background:#555;color:#888;font-size:9px;'
                               'padding:1px 3px;border-radius:3px;text-decoration:line-through;">'
                               'Item</span>')

            icon_path = get_pokemon_icon_path(species)
            img_html = f"<img src='{icon_path}' width='40'><br>" if icon_path else ""
            name_style = "text-decoration:line-through;color:#888;" if hp_pct == 0 else ""

            return (f"<b>{prefix}</b><br>{img_html}"
                    f"<span style='{name_style}'>{species}</span> {badge_html}<br>"
                    f"{bar}"
                    f"<span style='font-size:10px;'>{hp_display}{st_html}</span><br>"
                    f"<span style='font-size:9px;'>{boost_html}</span>")

        self.lbl_p1a.setText(format_slot("P1a", board.get("p1a", {})))
        self.lbl_p1b.setText(format_slot("P1b", board.get("p1b", {})))
        self.lbl_p2a.setText(format_slot("P2a", board.get("p2a", {})))
        self.lbl_p2b.setText(format_slot("P2b", board.get("p2b", {})))

        # ── 2. Conditions ─────────────────────────────────────────────────────
        self.list_condizioni_p1.clear()
        self.list_condizioni_generali.clear()
        self.list_condizioni_p2.clear()

        weather = sim.get("weather")
        terrain = sim.get("terrain")
        board_bg = "#1a1a1a"

        if weather:
            wname = weather[0] if isinstance(weather, list) else str(weather)
            extra = weather[1:] if isinstance(weather, list) else []
            from_s = next((p.replace("[from]", "").strip()
                           for p in extra if p.startswith("[from]")), "")
            of_s   = next((p.replace("[of]", "").strip()
                           for p in extra if p.startswith("[of]")), "")
            lbl = WEATHER_ICON.get(wname, f"🌫️ {wname}")
            if from_s: lbl += f" · {from_s}"
            if of_s:   lbl += f" [{of_s}]"
            self.list_condizioni_generali.addItem(lbl)
            board_bg = WEATHER_BG.get(wname, "#1a1a2e")

        if terrain:
            tname = terrain[0] if isinstance(terrain, list) else str(terrain)
            extra = terrain[1:] if isinstance(terrain, list) else []
            from_s = next((p.replace("[from]", "").strip()
                           for p in extra if p.startswith("[from]")), "")
            tlbl = TERRAIN_ICON.get(tname.lower(), f"🌐 {tname}")
            if from_s: tlbl += f" · {from_s}"
            self.list_condizioni_generali.addItem(tlbl)
            if not weather:
                board_bg = TERRAIN_BG.get(tname.lower(), "#1a1a1a")

        if sim.get("trick_room"):
            self.list_condizioni_generali.addItem("🔁 Trick Room attivo")

        if sim.get("p1_tailwind"):    self.list_condizioni_p1.addItem("💨 Tailwind")
        if sim.get("p1_reflect"):     self.list_condizioni_p1.addItem("🛡️ Reflect")
        if sim.get("p1_lightscreen"): self.list_condizioni_p1.addItem("✨ Light Screen")
        if sim.get("p1_auroraveil"):  self.list_condizioni_p1.addItem("🌈 Aurora Veil")
        if sim.get("p2_tailwind"):    self.list_condizioni_p2.addItem("💨 Tailwind")
        if sim.get("p2_reflect"):     self.list_condizioni_p2.addItem("🛡️ Reflect")
        if sim.get("p2_lightscreen"): self.list_condizioni_p2.addItem("✨ Light Screen")
        if sim.get("p2_auroraveil"):  self.list_condizioni_p2.addItem("🌈 Aurora Veil")

        self.frame_pokemon_in_campo.setStyleSheet(
            f"background:{board_bg}; border:none; border-radius:12px; padding: 8px;")

        # ── 3. Action attributes ──────────────────────────────────────────────
        act_type   = action_data.get("type", "")
        details    = action_data.get("details", "N/A")
        actor      = action_data.get("actor", "N/A")
        target_str = action_data.get("target", "N/A")

        detail_link = details
        if act_type == "move":
            detail_link = (f'<a href="move:{details}" style="color:#8A7D89;">'
                           f'{details}</a>')
        elif act_type == "ability":
            detail_link = (f'<a href="ability:{details}" style="color:#B8A9B7;">'
                           f'{details}</a>')
        elif act_type == "item":
            detail_link = (f'<a href="item:{details}" style="color:#C2BFBC;">'
                           f'{details}</a>')

        icon = ACTION_ICONS.get(act_type, "▪️")
        self.txt_attr.setHtml(
            f'<h3 style="margin:0 0 4px 0;color:#FFFFFF;">{icon} {act_type.upper()}</h3>'
            f'<b style="color:#AAAAAA;">Attore:</b> '
            f'<span style="color:#C2BFBC;">{actor}</span><br>'
            f'<b style="color:#AAAAAA;">Bersaglio:</b> '
            f'<span style="color:#B8A9B7;">{target_str}</span><br>'
            f'<b style="color:#AAAAAA;">Dettagli:</b> {detail_link}'
        )

        # ── 4. Tag inspector (semantic) ───────────────────────────────────────
        self._populate_tag_tree(action_data)

    # ── TAG TREE ──────────────────────────────────────────────────────────────

    TAG_META = {
        "damage":         ("💥", "Danno subito"),
        "heal":           ("💚", "Cura ricevuta"),
        "boost":          ("📈", "Statistiche aumentate"),
        "unboost":        ("📉", "Statistiche ridotte"),
        "status":         ("⚠️", "Stato alterato"),
        "curestatus":     ("✅", "Guarigione stato"),
        "faint":          ("💀", "Sconfitta"),
        "weather":        ("🌦️", "Meteo"),
        "fieldstart":     ("🌐", "Campo attivato"),
        "fieldend":       ("🌐", "Campo terminato"),
        "sidestart":      ("🛡️", "Effetto lato attivato"),
        "sideend":        ("🛡️", "Effetto lato terminato"),
        "ability":        ("✨", "Abilità attivata"),
        "enditem":        ("🎒", "Strumento consumato"),
        "mega":           ("💎", "Megaevoluzione"),
        "terastallize":   ("🔮", "Teracristallizzazione"),
        "miss":           ("❌", "Mossa mancata"),
        "immune":         ("🛡️", "Immunità"),
        "fail":           ("🚫", "Mossa fallita"),
        "crit":           ("⚡", "Colpo critico"),
        "supereffective": ("🔥", "Super efficace"),
        "resisted":       ("🔵", "Non molto efficace"),
        "activate":       ("⚙️", "Effetto attivato"),
        "start":          ("▶️", "Effetto iniziato"),
        "end":            ("⏹️", "Effetto terminato"),
        "singleturn":     ("🔒", "Protezione turno singolo"),
        "mustrecharge":   ("⏳", "Ricarica necessaria"),
        "hint":           ("💬", "Suggerimento"),
        "hitcount":       ("🔢", "Numero colpi"),
        "prepare":        ("⚙️", "Preparazione mossa"),
        "clearallboost":  ("🔄", "Reset tutti i boost"),
        "clearnegativeboost": ("🔄", "Reset boost negativi"),
        "anim":           ("🎬", "Animazione"),
    }

    def _populate_tag_tree(self, action_data: dict):
        self.tree_widget_tags.clear()
        tags = action_data.get("raw_tags", {})
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = {"raw": tags}
        if not isinstance(tags, dict) or not tags:
            return

        board = action_data.get("board_state", {})
        for key, val in tags.items():
            icon, desc = self.TAG_META.get(key.lower(), ("▪️", key.upper()))
            root = QTreeWidgetItem(self.tree_widget_tags, [f"{icon} {desc}"])
            root.setForeground(0, QColor("#e0e0e0"))
            for ev in self._get_events({key: val}, key):
                label = self._format_event_label(key.lower(), ev, board)
                child = QTreeWidgetItem(root, [label])
                child.setForeground(0, QColor("#aaaaaa"))
            root.setExpanded(True)

    def _format_event_label(self, tag: str, ev: list, board: dict) -> str:
        if not ev:
            return "(vuoto)"
        target = ev[0]
        from_s = next((p.replace("[from]", "").strip()
                       for p in ev if p.startswith("[from]")), "")
        of_s   = next((p.replace("[of]", "").strip()
                       for p in ev if p.startswith("[of]")), "")
        upkeep = any("[upkeep]" in p for p in ev)

        if tag == "damage":
            hp = ev[1] if len(ev) > 1 else "?"
            cause = f" (da {from_s})" if from_s else ""
            return f"{target} → {hp}{cause}"

        if tag == "heal":
            hp = ev[1] if len(ev) > 1 else "?"
            cause = ""
            if from_s:
                cause = f" (da {from_s}" + (f" di {of_s})" if of_s else ")")
            return f"{target} → {hp}{cause}"

        if tag in ("boost", "unboost"):
            stat = STAT_NAMES.get(ev[1].lower(), ev[1]) if len(ev) > 1 else "?"
            stages = ev[2] if len(ev) > 2 else "?"
            arrow = "▲" if tag == "boost" else "▼"
            return f"{target}: {arrow}{stages} {stat}"

        if tag == "status":
            st = STATUS_LABELS.get(ev[1].lower(), ev[1]) if len(ev) > 1 else "?"
            return f"{target} → {st}"

        if tag == "curestatus":
            st = ev[1] if len(ev) > 1 else "?"
            return f"{target} guarisce da {st}"

        if tag == "faint":
            return f"💀 {target} è sconfitto"

        if tag == "weather":
            wname = target
            suffix = " (continua)" if upkeep else ""
            if from_s: suffix += f" · da {from_s}"
            if of_s:   suffix += f" [{of_s}]"
            return f"{WEATHER_ICON.get(wname, wname)}{suffix}"

        if tag in ("fieldstart", "fieldend"):
            action = "attivato" if "start" in tag else "terminato"
            return f"{target} {action}"

        if tag in ("sidestart", "sideend"):
            effect = ev[1] if len(ev) > 1 else "?"
            action = "attivato" if "start" in tag else "terminato"
            return f"{target} → {effect} {action}"

        if tag == "ability":
            abil = ev[1] if len(ev) > 1 else "?"
            cause = f" [{from_s}]" if from_s else ""
            return f"{target}: {abil}{cause}"

        if tag == "enditem":
            item_name = ev[1] if len(ev) > 1 else "?"
            return f"{target} usa/perde: {item_name}"

        if tag == "mega":
            stone = ev[2] if len(ev) > 2 else ""
            return f"💎 {target} Megaevolve{' con ' + stone if stone else ''}"

        if tag == "terastallize":
            t_type = ev[1] if len(ev) > 1 else "?"
            return f"🔮 {target} → Tera {t_type}"

        if tag == "miss":
            return f"❌ {target} manca il bersaglio"

        if tag == "immune":
            return f"🛡️ {target} è immune"

        if tag == "crit":
            return f"⚡ Colpo critico su {target}"

        if tag == "supereffective":
            return f"🔥 Super efficace su {target}"

        if tag == "resisted":
            return f"🔵 Non molto efficace su {target}"

        if tag == "fail":
            return f"🚫 Mossa fallita su {target}"

        if tag == "singleturn":
            effect = ev[1] if len(ev) > 1 else "?"
            return f"🔒 {target}: {effect}"

        if tag == "activate":
            effect = ev[1] if len(ev) > 1 else "?"
            return f"⚙️ {target} attiva: {effect}"

        # Generic fallback
        return " · ".join(ev)

    # ── POKEMON PANEL ─────────────────────────────────────────────────────────

    def on_p1_pokemon_clicked(self, item: QListWidgetItem):
        self._update_pokemon_dati(
            self.lbl_dati_p1, self.frame_img_p1, item.data(Qt.UserRole))

    def on_p2_pokemon_clicked(self, item: QListWidgetItem):
        self._update_pokemon_dati(
            self.lbl_dati_p2, self.frame_img_p2, item.data(Qt.UserRole))

    def _update_pokemon_dati(self, lbl: QLabel, img: QLabel, poke_data):
        if not isinstance(poke_data, dict):
            lbl.setText("Dati non disponibili")
            img.clear()
            return
        species   = poke_data.get("species")  or "N/A"
        item_held = poke_data.get("item")      or "N/A"
        ability   = poke_data.get("ability")   or "N/A"
        tera_type = poke_data.get("tera_type") or "N/A"
        nature    = poke_data.get("nature")    or "N/A"
        base_stats = poke_data.get("base_stats", {})
        moves     = poke_data.get("moves", [])

        icon_path = get_pokemon_icon_path(species)
        if icon_path:
            img.setPixmap(QPixmap(icon_path).scaled(
                96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            img.setText("(No img)")

        stats_str = " | ".join(
            f"{k}: {v}" for k, v in base_stats.items()) if base_stats else "N/A"
        moves_html = "".join(
            f'<br>&nbsp;&nbsp;• {m}' for m in moves) if moves else "<br>N/A"

        lbl.setTextFormat(Qt.RichText)
        lbl.setText(
            f"<b>Specie:</b> {species}<br>"
            f"<b>Strumento:</b> {item_held}<br>"
            f"<b>Abilità:</b> {ability}<br>"
            f"<b>Tera:</b> {tera_type}<br>"
            f"<b>Natura:</b> {nature}<br>"
            f'<b>Stat Base:</b> <span style="color:#aaa;font-size:11px;">'
            f'{stats_str}</span><br>'
            f"<b>Mosse:</b>{moves_html}"
        )
