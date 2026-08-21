from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QTableWidget, 
    QTableWidgetItem, QHeaderView, QComboBox, QPushButton, QLabel, QTextEdit, QGridLayout, QGroupBox
)
from PySide6.QtCore import Qt
from database.connection import SessionLocal
from database.models import Move, Item, Ability
from views.base_view import BaseHeaderWidget

class GenericCatalogWidget(BaseHeaderWidget):
    def __init__(self, title, model_class, columns, column_labels):
        super().__init__(title)
        self.model_class = model_class
        self.columns = columns
        
        # Filtri
        filter_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Cerca per nome...")
        self.search_bar.textChanged.connect(self.load_data)
        filter_layout.addWidget(self.search_bar)
        
        self.setup_extra_filters(filter_layout)
        self.add_layout(filter_layout)
        
        # Tabella
        self.table = QTableWidget()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(column_labels)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.add_content(self.table)
        
    def setup_extra_filters(self, layout):
        pass # Override nelle sottoclassi
        
    def build_query(self, session):
        q = session.query(self.model_class)
        txt = self.search_bar.text().strip().lower()
        if txt:
            q = q.filter(self.model_class.name.ilike(f"%{txt}%"))
        return q
        
    def load_data(self):
        session = SessionLocal()
        try:
            query = self.build_query(session)
            results = query.all()
            self.table.setRowCount(len(results))
            for row_idx, item in enumerate(results):
                for col_idx, col_name in enumerate(self.columns):
                    val = getattr(item, col_name, "")
                    if col_name == "accuracy" and val == 0:
                        val = "-" # Infallibile
                    self.table.setItem(row_idx, col_idx, QTableWidgetItem(str(val)))
        finally:
            session.close()

    def showEvent(self, event):
        super().showEvent(event)
        self.load_data()
        
    def set_search(self, term):
        self.search_bar.setText(term)
        self.load_data()

class MovesWidget(GenericCatalogWidget):
    def __init__(self):
        super().__init__("Dizionario Mosse", Move, 
                         ["name", "type", "category", "base_power", "accuracy", "short_desc"],
                         ["Nome", "Tipo", "Categoria", "Potenza", "Precisione", "Descrizione"])
                         
    def setup_extra_filters(self, layout):
        self.cb_type = QComboBox()
        self.cb_type.addItems(["Tutti i Tipi", "Normal", "Fire", "Water", "Grass", "Electric", "Ice", "Fighting", "Poison", "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"])
        self.cb_type.currentTextChanged.connect(self.load_data)
        
        self.cb_cat = QComboBox()
        self.cb_cat.addItems(["Tutte le Categorie", "Physical", "Special", "Status"])
        self.cb_cat.currentTextChanged.connect(self.load_data)
        
        layout.addWidget(self.cb_type)
        layout.addWidget(self.cb_cat)
        
    def build_query(self, session):
        q = super().build_query(session)
        t = self.cb_type.currentText()
        if t != "Tutti i Tipi":
            q = q.filter(Move.type == t)
        c = self.cb_cat.currentText()
        if c != "Tutte le Categorie":
            q = q.filter(Move.category == c)
        return q

class ItemsWidget(GenericCatalogWidget):
    def __init__(self):
        super().__init__("Dizionario Strumenti", Item, ["name", "short_desc"], ["Nome", "Descrizione"])

class AbilitiesWidget(GenericCatalogWidget):
    def __init__(self):
        super().__init__("Dizionario Abilità", Ability, ["name", "short_desc"], ["Nome", "Descrizione"])

class MoveDetailWidget(QWidget):
    from PySide6.QtCore import Signal
    back_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # Barra superiore con bottone Indietro
        top_bar = QHBoxLayout()
        self.btn_back = QPushButton("⬅️ Torna Indietro")
        self.btn_back.setStyleSheet("background-color: #e74c3c; font-weight: bold; padding: 5px;")
        self.btn_back.clicked.connect(self.back_requested.emit)
        top_bar.addWidget(self.btn_back)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # Titolo Mossa
        self.lbl_name = QLabel()
        self.lbl_name.setStyleSheet("font-size: 24px; font-weight: bold; color: #3498db; margin-top: 10px;")
        layout.addWidget(self.lbl_name)

        # Contenitore Statistiche
        stats_group = QGroupBox("Statistiche Mossa")
        stats_layout = QGridLayout(stats_group)
        
        self.lbl_type = QLabel()
        self.lbl_category = QLabel()
        self.lbl_power = QLabel()
        self.lbl_accuracy = QLabel()
        self.lbl_priority = QLabel()

        stats_layout.addWidget(QLabel("<b>Tipo:</b>"), 0, 0)
        stats_layout.addWidget(self.lbl_type, 0, 1)
        
        stats_layout.addWidget(QLabel("<b>Categoria:</b>"), 0, 2)
        stats_layout.addWidget(self.lbl_category, 0, 3)
        
        stats_layout.addWidget(QLabel("<b>Potenza:</b>"), 1, 0)
        stats_layout.addWidget(self.lbl_power, 1, 1)
        
        stats_layout.addWidget(QLabel("<b>Precisione:</b>"), 1, 2)
        stats_layout.addWidget(self.lbl_accuracy, 1, 3)
        
        stats_layout.addWidget(QLabel("<b>Priorità:</b>"), 2, 0)
        stats_layout.addWidget(self.lbl_priority, 2, 1)

        layout.addWidget(stats_group)

        # Descrizione
        desc_group = QGroupBox("Descrizione")
        desc_layout = QVBoxLayout(desc_group)
        self.txt_desc = QTextEdit()
        self.txt_desc.setReadOnly(True)
        self.txt_desc.setStyleSheet("font-size: 16px;")
        desc_layout.addWidget(self.txt_desc)
        layout.addWidget(desc_group)

    def display_move(self, move_name: str):
        session = SessionLocal()
        try:
            # Match per name esatto (ignorando le maiuscole grazie a ilike o query diretta)
            move = session.query(Move).filter(Move.name.ilike(move_name)).first()
            if not move:
                self.lbl_name.setText("Mossa non trovata")
                self.lbl_type.clear()
                self.lbl_category.clear()
                self.lbl_power.clear()
                self.lbl_accuracy.clear()
                self.lbl_priority.clear()
                self.txt_desc.setText("Nessun dato disponibile nel database.")
                return

            self.lbl_name.setText(move.name)
            self.lbl_type.setText(move.type)
            self.lbl_category.setText(move.category)
            
            pwr = str(move.base_power) if move.base_power else "-"
            self.lbl_power.setText(pwr)
            
            acc = str(move.accuracy) if move.accuracy else "-"
            self.lbl_accuracy.setText(acc)
            
            prio = str(move.priority)
            if move.priority > 0: prio = f"+{move.priority}"
            self.lbl_priority.setText(prio)
            
            self.txt_desc.setText(move.short_desc)
        finally:
            session.close()
