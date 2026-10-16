"""
slot_analysis_tab.py
====================
Tab "Analisi Sostituzione" della Sheet Dashboard: 5 analisi per individuare
lo slot da liberare e verificare che il sostituto non apra nuovi buchi.

  1. Dead Weight Index        4. Switch-in e danni in entrata
  2. KO subiti per tipo       5. Trade-off dei KO
  3. Matchup negativi         + Valutazione candidato (Pokepaste)

I dati arrivano da `slot_analysis` (funzioni pure); qui solo presentazione.
Identità Pokémon sempre "Specie + Forma".
"""

from typing import List, Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QProgressBar, QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from config.theme import Fonts, Palette, Spacing
from src.domain.sheet_dashboard import slot_analysis as sa
from src.domain.sheet_dashboard.models import DashboardGame
from views.sheet_dashboard_view import (
    _BTN_QSS, _COMBO_QSS, _MUTED_QSS, _TABLE_QSS, _TITLE_QSS, PokemonSprite, _card, _label,
    _make_table, _pct_color, pokemon_with_name,
)

NONE_CORE = "— Nessuno —"
_ALERT_QSS = (
    f"color: {Palette.DANGER_BRIGHT}; font-size: {Fonts.SIZE_BASE}; background: rgba(200,60,60,0.12);"
    f" border: 1px solid {Palette.DANGER}; border-radius: 6px; padding: 6px 8px;"
)
_OK_QSS = (
    f"color: {Palette.SUCCESS_BRIGHT}; font-size: {Fonts.SIZE_BASE}; background: rgba(60,160,90,0.12);"
    f" border: 1px solid {Palette.SUCCESS}; border-radius: 6px; padding: 6px 8px;"
)


# ── helper celle ──────────────────────────────────────────────────

def _item(text, color: Optional[str] = None, center: bool = True, bold: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    if center:
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    if color:
        it.setForeground(QColor(color))
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    return it


def _pct_text(p: Optional[float]) -> str:
    return "—" if p is None else f"{p * 100:.0f}%"


def _bar(value: float, color: str, text: str) -> QWidget:
    """Barra percentuale (0..1) con testo, per celle di tabella."""
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(6, 0, 6, 0)
    pb = QProgressBar()
    pb.setRange(0, 1000)
    pb.setValue(int(max(0.0, min(1.0, value)) * 1000))
    pb.setTextVisible(True)
    pb.setFormat(text)
    pb.setFixedHeight(18)
    pb.setStyleSheet(
        f"QProgressBar {{ background: {Palette.BG_SURFACE}; border: 1px solid {Palette.BORDER_LIGHT};"
        f" border-radius: 4px; color: {Palette.TEXT_PRIMARY}; font-size: 11px; text-align: center; }}"
        f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
    )
    lay.addWidget(pb)
    return w


def _badge(text: str, color: str) -> QWidget:
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(4, 0, 4, 0)
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {color}; border: 1px solid {color}; border-radius: 4px; padding: 1px 6px;"
        f" font-size: 10px; font-weight: 700; background: transparent;"
    )
    lay.addStretch()
    lay.addWidget(lbl)
    lay.addStretch()
    return w


def _table(headers: List[str], stretch_col: int = 0, height: int = 260) -> QTableWidget:
    t = _make_table(headers)
    t.verticalHeader().setDefaultSectionSize(40)
    hh = t.horizontalHeader()
    for c in range(len(headers)):
        hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch if c == stretch_col
                                else QHeaderView.ResizeMode.ResizeToContents)
    t.setMinimumHeight(height)
    t.setMaximumHeight(height + 120)
    return t


class _Box(QFrame):
    """Box contestuale con titolo, sottotitolo, indicatore di caricamento e corpo."""

    def __init__(self, title: str, goal: str):
        super().__init__()
        self.setObjectName("dashCard")
        from views.sheet_dashboard_view import _CARD_QSS
        self.setStyleSheet(_CARD_QSS)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.MD)
        lay.setSpacing(Spacing.SM)
        head = QHBoxLayout()
        head.addWidget(_label(title, _TITLE_QSS))
        head.addStretch()
        self.loading = QProgressBar()
        self.loading.setRange(0, 0)
        self.loading.setFixedSize(110, 6)
        self.loading.setTextVisible(False)
        self.loading.hide()
        head.addWidget(self.loading)
        lay.addLayout(head)
        g = _label(goal, _MUTED_QSS)
        g.setWordWrap(True)
        lay.addWidget(g)
        self.summary = _label("", f"color: {Palette.TEXT_PRIMARY}; background: transparent; border: none;")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        self.body = QVBoxLayout()
        self.body.setSpacing(Spacing.SM)
        lay.addLayout(self.body)


# ── Dialog drill-down switch-in ───────────────────────────────────

class SwitchDetailDialog(QDialog):
    replay_requested = Signal(object)

    def __init__(self, row: sa.SwitchRow, hp_threshold: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Ingressi in campo — {row.pokemon}")
        self.resize(900, 520)
        self.setStyleSheet(f"QDialog {{ background-color: {Palette.BG_APP}; }}" + _BTN_QSS)
        lay = QVBoxLayout(self)
        lay.addWidget(pokemon_with_name(row.pokemon, 40))
        t = _table(["Game", "Turno", "Tipo", "Uscito dallo slot", "HP ingresso", "HP minimo", "HP persi",
                    "Colpito da", "Replay"], stretch_col=7, height=380)
        for rec in sorted(row.records, key=lambda r: (r.game.game_no, r.event.turn)):
            ev = rec.event
            r = t.rowCount()
            t.insertRow(r)
            t.setItem(r, 0, _item(rec.game.game_no))
            t.setItem(r, 1, _item(ev.turn))
            t.setItem(r, 2, _item("Hard switch" if ev.kind == "hard" else "Pivot"))
            t.setItem(r, 3, _item(ev.replaced or "—"))
            t.setItem(r, 4, _item(f"{ev.hp_before:.0f}%"))
            t.setItem(r, 5, _item(f"{ev.hp_end:.0f}%"))
            t.setItem(r, 6, _item(f"{ev.hp_lost:.0f}%",
                                  Palette.DANGER_BRIGHT if ev.hp_lost > hp_threshold else Palette.SUCCESS_BRIGHT, bold=True))
            hits = ", ".join(f"{a}: {m} ({sa.move_type(m)})" for a, m in ev.hits) or "nessun attacco diretto"
            t.setItem(r, 7, _item(hits, center=False))
            btn = QPushButton("Replay")
            btn.setStyleSheet(_BTN_QSS)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, g=rec.game: self.replay_requested.emit(g))
            t.setCellWidget(r, 8, btn)
        lay.addWidget(t, 1)


# ── Worker valutazione candidato (usa il bridge Node.js) ──────────

class _CandidateWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, paste: str, weak: List[str], counters: List[str], targets: List[str], parent=None):
        super().__init__(parent)
        self.args = (paste, weak, counters, targets)

    def run(self):
        try:
            self.finished_ok.emit(sa.evaluate_candidate(*self.args))
        except Exception as e:
            self.failed.emit(str(e))


# ── Tab principale ────────────────────────────────────────────────

class SlotAnalysisTab(QWidget):
    replay_requested = Signal(object)

    def __init__(self):
        super().__init__()
        self._games: List[DashboardGame] = []
        self._switch_rows: List[sa.SwitchRow] = []
        self._weak: List[str] = []
        self._counters: List[str] = []
        self._targets: List[str] = []
        self._cand_worker: Optional[_CandidateWorker] = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._do_calc)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, Spacing.SM, 0, 0)
        root.setSpacing(Spacing.SM)

        # Barra controlli (riga 1: soglie · riga 2: selezione Pokémon)
        bar = _card()
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        outer.setSpacing(Spacing.SM)
        bl = QHBoxLayout()
        bl2 = QHBoxLayout()
        outer.addLayout(bl)
        outer.addLayout(bl2)

        def _spin(lo, hi, val, suffix=""):
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setValue(val)
            s.setSuffix(suffix)
            s.setStyleSheet(_COMBO_QSS)
            s.valueChanged.connect(self._schedule)
            return s

        self.spin_pick = _spin(5, 60, 25, "%")
        self.spin_wr = _spin(10, 60, 40, "%")
        self.spin_hp = _spin(10, 90, 50, "%")
        self.spin_min = _spin(1, 50, 3)
        self.spin_struct = _spin(10, 80, 40, "%")
        for lbl, w in (("Pick Rate <", self.spin_pick), ("WR matchup <", self.spin_wr),
                       ("HP persi all'ingresso >", self.spin_hp), ("Min game matchup", self.spin_min),
                       ("Debolezza strutturale ≥", self.spin_struct)):
            bl.addWidget(_label(lbl, _MUTED_QSS))
            bl.addWidget(w)
            bl.addSpacing(Spacing.MD)
        bl.addStretch()
        bl2.addWidget(_label("Pokémon da sostituire:", _MUTED_QSS))
        self.cmb_drop = QComboBox()
        self.cmb_drop.setStyleSheet(_COMBO_QSS)
        self.cmb_drop.setMinimumWidth(200)
        self.cmb_drop.currentIndexChanged.connect(self._schedule)
        bl2.addWidget(self.cmb_drop)
        bl2.addSpacing(Spacing.LG)
        bl2.addWidget(_label("Core da proteggere (box 4):", _MUTED_QSS))
        self.cmb_core = QComboBox()
        self.cmb_core.setStyleSheet(_COMBO_QSS)
        self.cmb_core.setMinimumWidth(200)
        self.cmb_core.currentIndexChanged.connect(self._schedule)
        bl2.addWidget(self.cmb_core)
        bl2.addStretch()
        root.addWidget(bar)

        # Area boxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        cont = QWidget()
        grid = QGridLayout(cont)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(Spacing.MD)

        self.box1 = _Box("1 · Tasso di Panchina (Dead Weight Index)",
                         "Pick Rate = volte portato (Lead + Back) / volte nel team. Chi è sotto soglia occupa uno slot senza fornire coperture utili.")
        self.tbl_dw = _table(["Pokémon", "Nel team", "Portato", "Pick Rate", "WR quando portato", "Stato"])
        self.box1.body.addWidget(self.tbl_dw)

        self.box2 = _Box("2 · KO subiti (identificazione della falla)",
                         "Ogni |faint| a tuo sfavore: Pokémon avversario che ha inflitto il KO e tipo della mossa.")
        self.lbl_struct = _label("", _ALERT_QSS)
        self.lbl_struct.setWordWrap(True)
        self.box2.body.addWidget(self.lbl_struct)
        h2 = QHBoxLayout()
        self.tbl_ko_type = _table(["Tipo mossa", "KO", "% sul totale"], stretch_col=2, height=220)
        self.tbl_ko_killer = _table(["Killer avversario", "KO", "Mosse"], stretch_col=2, height=220)
        h2.addWidget(self.tbl_ko_type)
        h2.addWidget(self.tbl_ko_killer)
        self.box2.body.addLayout(h2)

        self.box3 = _Box("3 · Matrice dei Matchup Negativi",
                         "Win Rate condizionato alla presenza del Pokémon nel team avversario (preview) e quando viene effettivamente portato.")
        self.tbl_mu = _table(["Pokémon avversario", "Game", "WR (in preview)", "WR (portato)", "Stato"])
        self.box3.body.addWidget(self.tbl_mu)

        self.box4 = _Box("4 · Switch-in e danni in entrata",
                         "HP persi nel turno di ingresso (hard switch o pivot). Le sostituzioni dopo un KO non contano. Doppio click su una riga per il dettaglio.")
        self.tbl_sw = _table(["Pokémon", "Ingressi", "HP persi medi", "Ingressi oltre soglia", "Tipi che lo colpiscono entrando"], stretch_col=4)
        self.tbl_sw.cellDoubleClicked.connect(self._open_switch_detail)
        self.box4.body.addWidget(self.tbl_sw)

        self.box5 = _Box("5 · Trade-off dei KO",
                         "KO a tuo favore causati dal Pokémon da sostituire. Le coperture esclusive sono i buchi offensivi che si aprirebbero.")
        self.tbl_tr = _table(["Bersaglio", "KO", "Mosse", "Copertura"], stretch_col=2)
        self.box5.body.addWidget(self.tbl_tr)

        self.box6 = _Box("+ · Valutazione candidato",
                         "Incolla il Pokepaste (o l'URL) del sostituto: resistenze ai tipi deboli, danni ai counter (box 3) e ai bersagli del Pokémon scartato (box 5).")
        self.edit_cand = QTextEdit()
        self.edit_cand.setPlaceholderText("Goodra-Hisui @ Assault Vest\nAbility: Sap Sipper\n...")
        self.edit_cand.setFixedHeight(110)
        self.edit_cand.setStyleSheet(
            f"QTextEdit {{ background: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY};"
            f" border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 6px; }}")
        self.box6.body.addWidget(self.edit_cand)
        self.btn_cand = QPushButton("Valuta candidato")
        self.btn_cand.setStyleSheet(_BTN_QSS)
        self.btn_cand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cand.clicked.connect(self._eval_candidate)
        self.box6.body.addWidget(self.btn_cand, 0, Qt.AlignmentFlag.AlignLeft)
        self.tbl_cand = _table(["Candidato", "Verifica", "Bersaglio / Tipo", "Esito"], stretch_col=3, height=220)
        self.box6.body.addWidget(self.tbl_cand)

        for i, b in enumerate((self.box1, self.box2, self.box3, self.box4, self.box5, self.box6)):
            grid.addWidget(b, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)

    # ---- API ----
    def set_games(self, games: List[DashboardGame]):
        self._games = games
        rows, cand = sa.dead_weight_index(games, self.spin_pick.value() / 100)
        team = [r.pokemon for r in sorted(rows, key=lambda r: (-r.in_team, r.pokemon))]
        prev_drop, prev_core = self.cmb_drop.currentText(), self.cmb_core.currentText()
        for cmb in (self.cmb_drop, self.cmb_core):
            cmb.blockSignals(True)
            cmb.clear()
        self.cmb_core.addItem(NONE_CORE)
        for p in team:
            self.cmb_drop.addItem(p)
            self.cmb_core.addItem(p)
        self.cmb_drop.setCurrentText(prev_drop if prev_drop in team else (cand or ""))
        self.cmb_core.setCurrentText(prev_core if prev_core in team else NONE_CORE)
        for cmb in (self.cmb_drop, self.cmb_core):
            cmb.blockSignals(False)
        self._schedule()

    # ---- calcolo ----
    def _boxes(self):
        return (self.box1, self.box2, self.box3, self.box4, self.box5)

    def _schedule(self, *_):
        for b in self._boxes():
            b.loading.show()
        self._timer.start(60)

    def _do_calc(self):
        g = self._games
        pick, wr, hp = self.spin_pick.value() / 100, self.spin_wr.value() / 100, float(self.spin_hp.value())
        drop = self.cmb_drop.currentText() or None
        core = self.cmb_core.currentText()
        core = None if core in ("", NONE_CORE) else core

        self._fill_dead_weight(*sa.dead_weight_index(g, pick), drop)
        self._fill_ko_suffered(sa.ko_suffered_analysis(g, self.spin_struct.value() / 100))
        self._fill_matchups(*sa.negative_matchup_matrix(g, wr, self.spin_min.value()))
        self._switch_rows = sa.switch_in_damage(g, hp, core)
        self._fill_switch(self._switch_rows, hp, core)
        if drop:
            self._fill_tradeoff(drop, *sa.ko_tradeoff(g, drop))
        for b in self._boxes():
            b.loading.hide()

    # ---- render ----
    def _fill_dead_weight(self, rows: List[sa.DeadWeightRow], cand: Optional[str], drop: Optional[str]):
        t = self.tbl_dw
        t.setRowCount(0)
        for r in rows:
            i = t.rowCount()
            t.insertRow(i)
            t.setCellWidget(i, 0, pokemon_with_name(r.pokemon, 30))
            t.setItem(i, 1, _item(r.in_team))
            t.setItem(i, 2, _item(r.brought))
            col = Palette.DANGER if r.below_threshold else (Palette.WARNING if r.pick_rate < 0.5 else Palette.SUCCESS)
            t.setCellWidget(i, 3, _bar(r.pick_rate, col, f"{r.pick_rate * 100:.0f}%"))
            t.setItem(i, 4, _item(_pct_text(r.win_pct_brought), _pct_color(r.win_pct_brought)))
            if r.pokemon == cand:
                t.setCellWidget(i, 5, _badge("DA SOSTITUIRE", Palette.DANGER_BRIGHT))
            elif r.below_threshold:
                t.setCellWidget(i, 5, _badge("SOTTO SOGLIA", Palette.WARNING))
            else:
                t.setItem(i, 5, _item("OK", Palette.TEXT_MUTED))
        under = [r.pokemon for r in rows if r.below_threshold]
        self.box1.summary.setText(
            f"Anello debole: <b>{cand}</b>" + (f" · sotto soglia: {', '.join(under)}" if under else " · nessuno sotto soglia")
            if cand else "Nessun dato sul team.")

    def _fill_ko_suffered(self, st: sa.KoSufferedStats):
        self.box2.summary.setText(
            f"<b>{st.total}</b> KO subiti · {st.direct} da attacco diretto · {st.indirect} da danno indiretto")
        self._weak = sa.weak_types(st)
        if self._weak:
            lines = []
            for t, (res, imm) in st.required_resistances.items():
                share = next((p for tt, _, p in st.by_type if tt == t), 0.0)
                lines.append(f"<b>{t}</b> ({share * 100:.0f}% dei KO) → serve un tipo che resista: "
                             f"{', '.join(res) or '—'}" + (f" · immune: {', '.join(imm)}" if imm else ""))
            head = ("Debolezza strutturale" if st.structural_types else
                    f"Debolezza strutturale combinata ({st.structural_pair[2] * 100:.0f}% dei KO)")
            self.lbl_struct.setText(f"⚠ {head}:<br>" + "<br>".join(lines))
            self.lbl_struct.setStyleSheet(_ALERT_QSS)
        else:
            self.lbl_struct.setText("Nessun tipo supera la soglia di debolezza strutturale.")
            self.lbl_struct.setStyleSheet(_OK_QSS)
        self.lbl_struct.setVisible(st.total > 0)

        t = self.tbl_ko_type
        t.setRowCount(0)
        for typ, n, p in st.by_type:
            i = t.rowCount()
            t.insertRow(i)
            weak = typ in self._weak
            t.setItem(i, 0, _item(typ, Palette.DANGER_BRIGHT if weak else None, center=False, bold=weak))
            t.setItem(i, 1, _item(n))
            t.setCellWidget(i, 2, _bar(p, Palette.DANGER if weak else Palette.SECONDARY, f"{p * 100:.0f}%"))
        t = self.tbl_ko_killer
        t.setRowCount(0)
        for killer, n, moves in st.by_killer:
            i = t.rowCount()
            t.insertRow(i)
            t.setCellWidget(i, 0, pokemon_with_name(killer, 28))
            t.setItem(i, 1, _item(n))
            t.setItem(i, 2, _item(", ".join(f"{m} ({sa.move_type(m)})" for m in moves), center=False))

    def _fill_matchups(self, rows: List[sa.MatchupRow], overall: Optional[float]):
        self._counters = [r.pokemon for r in rows if r.flagged]
        self.box3.summary.setText(
            f"WR complessivo: <b>{_pct_text(overall)}</b> · counter del core (WR sotto soglia): "
            f"<b>{', '.join(self._counters) or 'nessuno'}</b>")
        t = self.tbl_mu
        t.setRowCount(0)
        for r in rows:
            i = t.rowCount()
            t.insertRow(i)
            t.setCellWidget(i, 0, pokemon_with_name(r.pokemon, 30))
            t.setItem(i, 1, _item(r.preview_games))
            t.setItem(i, 2, _item(f"{_pct_text(r.preview_wr)}  ({r.preview_wins}/{r.preview_games})",
                                  _pct_color(r.preview_wr), bold=r.flagged))
            t.setItem(i, 3, _item(f"{_pct_text(r.brought_wr)}  ({r.brought_wins}/{r.brought_games})"
                                  if r.brought_games else "—", _pct_color(r.brought_wr)))
            if r.flagged:
                t.setCellWidget(i, 4, _badge("COUNTER", Palette.DANGER_BRIGHT))
            else:
                t.setItem(i, 4, _item(""))

    def _fill_switch(self, rows: List[sa.SwitchRow], hp: float, core: Optional[str]):
        failing = [r.pokemon for r in rows if r.count and r.avg_lost > hp]
        scope = f"solo ingressi al posto di <b>{core}</b>" if core else "tutti gli ingressi volontari"
        self.box4.summary.setText(
            f"Ambito: {scope} · sinergia fallita (perdita media &gt; {hp:.0f}%): "
            f"<b>{', '.join(failing) or 'nessuno'}</b>")
        t = self.tbl_sw
        t.setRowCount(0)
        for r in rows:
            i = t.rowCount()
            t.insertRow(i)
            t.setCellWidget(i, 0, pokemon_with_name(r.pokemon, 30))
            t.setItem(i, 1, _item(r.count))
            col = Palette.DANGER if r.avg_lost > hp else (Palette.WARNING if r.avg_lost > hp / 2 else Palette.SUCCESS)
            t.setCellWidget(i, 2, _bar(r.avg_lost / 100, col, f"{r.avg_lost:.0f}%"))
            t.setItem(i, 3, _item(f"{r.over_threshold}/{r.count}  ({r.pct_over * 100:.0f}%)",
                                  Palette.DANGER_BRIGHT if r.pct_over >= 0.5 else None))
            t.setItem(i, 4, _item(", ".join(f"{k} ×{n}" for k, n in r.hit_types.most_common()) or "—", center=False))

    def _fill_tradeoff(self, drop: str, rows: List[sa.KoTargetRow], total: int, totals):
        self._targets = [r.target for r in rows]
        excl = [r.target for r in rows if r.exclusive]
        rank = ", ".join(f"{k} {n}" for k, n in totals.most_common())
        self.box5.summary.setText(
            f"<b>{drop}</b> ha inflitto <b>{total}</b> KO · coperture esclusive: "
            f"<b>{', '.join(excl) or 'nessuna'}</b><br><span style='color:{Palette.TEXT_MUTED}'>KO per membro: {rank or '—'}</span>")
        t = self.tbl_tr
        t.setRowCount(0)
        for r in rows:
            i = t.rowCount()
            t.insertRow(i)
            t.setCellWidget(i, 0, pokemon_with_name(r.target, 30))
            t.setItem(i, 1, _item(r.count))
            t.setItem(i, 2, _item(", ".join(f"{m} ({sa.move_type(m)})" for m in r.moves), center=False))
            if r.exclusive:
                t.setCellWidget(i, 3, _badge("ESCLUSIVA", Palette.DANGER_BRIGHT))
            else:
                t.setItem(i, 3, _item("anche: " + ", ".join(r.other_killers), Palette.TEXT_MUTED))

    # ---- drill-down / candidato ----
    def _open_switch_detail(self, row: int, _col: int):
        if 0 <= row < len(self._switch_rows):
            dlg = SwitchDetailDialog(self._switch_rows[row], float(self.spin_hp.value()), self)
            dlg.replay_requested.connect(self.replay_requested.emit)
            dlg.exec()

    def _eval_candidate(self):
        paste = self.edit_cand.toPlainText().strip()
        if not paste or (self._cand_worker and self._cand_worker.isRunning()):
            return
        self.btn_cand.setEnabled(False)
        self.box6.loading.show()
        self._cand_worker = _CandidateWorker(paste, self._weak, self._counters, self._targets, self)
        self._cand_worker.finished_ok.connect(self._on_candidate)
        self._cand_worker.failed.connect(self._on_candidate_failed)
        self._cand_worker.start()

    def _on_candidate_failed(self, msg: str):
        self.btn_cand.setEnabled(True)
        self.box6.loading.hide()
        self.box6.summary.setText(f"<span style='color:{Palette.DANGER_BRIGHT}'>Errore: {msg}</span>")

    def _on_candidate(self, checks: List[sa.CandidateCheck]):
        self.btn_cand.setEnabled(True)
        self.box6.loading.hide()
        t = self.tbl_cand
        t.setRowCount(0)
        if not checks:
            self.box6.summary.setText("Nessun Pokémon riconosciuto nel paste.")
            return
        tier_col = {"1HKO": Palette.SUCCESS_BRIGHT, "2HKO": Palette.PRIMARY, "3+ HKO": Palette.DANGER_BRIGHT}
        for c in checks:
            def add(kind, target, text, color):
                i = t.rowCount()
                t.insertRow(i)
                t.setCellWidget(i, 0, pokemon_with_name(c.species, 26))
                t.setItem(i, 1, _item(kind))
                t.setItem(i, 2, _item(target))
                t.setItem(i, 3, _item(text, color, center=False, bold=True))
            types = "/".join(c.types) or "?"
            if not c.type_checks:
                add("Resistenza", "—", f"Tipi {types}: nessuna debolezza strutturale da coprire", Palette.TEXT_MUTED)
            for typ, mult in c.type_checks:
                ok = mult < 1.0
                label = "immune" if mult == 0 else ("resiste" if ok else ("neutro" if mult == 1 else "DEBOLE"))
                add("Resistenza", typ, f"×{mult:g} ({label}) — tipi {types}",
                    Palette.SUCCESS_BRIGHT if ok else (Palette.WARNING if mult == 1 else Palette.DANGER_BRIGHT))
            for kind, rows in (("Vs counter", c.counter_damage), ("Vs bersaglio KO", c.target_damage)):
                for target, move, mx, tier in rows:
                    add(kind, target, f"{move or '—'}: fino a {mx:.0f}% · {tier}", tier_col.get(tier))
        self.box6.summary.setText(f"{len(checks)} candidato/i valutati contro {len(self._weak)} tipi deboli, "
                                  f"{len(self._counters)} counter e {len(self._targets)} bersagli.")
