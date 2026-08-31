from PySide6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy, QGraphicsColorizeEffect
from PySide6.QtCore import Qt, Signal, QSize, QPropertyAnimation, QEasingCurve, QEvent
from PySide6.QtGui import QIcon, QPixmap, QCursor, QColor
import os

class HomeCard(QFrame):
    clicked = Signal()

    def __init__(self, title, normal_icon_path, hover_icon_path, parent=None):
        super().__init__(parent)
        self.setObjectName("card_elevated")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        # Styles for the card
        self.setStyleSheet("""
            QFrame#card_elevated {
                background-color: #A69ACA;
                border: 1px solid #A69ACA;
                border-radius: 12px;
            }
            QFrame#card_elevated:hover {
                background-color: #C49A3C;
                border: 1px solid #C49A3C;
            }
        """)

        self.normal_icon_path = normal_icon_path
        self.hover_icon_path = hover_icon_path

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_icon(self.normal_icon_path)
        
        self.effect = QGraphicsColorizeEffect()
        self.effect.setColor(QColor("#111118"))
        self.icon_label.setGraphicsEffect(self.effect)
        
        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #111118;")

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        
        # Make it expand but keep a nice minimum size
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_icon(self, path):
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            # scale pixmap to 48x48
            scaled_pixmap = pixmap.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.icon_label.setPixmap(scaled_pixmap)

    def enterEvent(self, event):
        self.set_icon(self.hover_icon_path)
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #111118;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.set_icon(self.normal_icon_path)
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #111118;")
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class HomeWidget(QWidget):
    # Segnali per la navigazione
    navigate_to_list = Signal()
    navigate_to_import = Signal()
    navigate_to_mass_import = Signal()
    navigate_to_meta_stats = Signal()
    navigate_to_core_analysis = Signal()
    navigate_to_team_analysis = Signal()
    navigate_to_build_compare = Signal()
    navigate_to_optimizer = Signal()
    navigate_to_bulk_optimizer = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(77, 77, 77, 77)
        
        # Title Image instead of text
        self.title_image = QLabel()
        self.title_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_image.setStyleSheet("margin-bottom: 20px;")
        
        logo_path = r"C:\Users\Mirco\Documents\Jorkcorp\janalytics_windows\assets\logo\home.png"
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaledToHeight(240, Qt.TransformationMode.SmoothTransformation)
                self.title_image.setPixmap(scaled_pixmap)
                
        main_layout.addWidget(self.title_image)
        
        # Grid layout for cards
        grid_layout = QGridLayout()
        grid_layout.setSpacing(24)
        
        # RIGA 1
        # Libreria Replay
        self.card_list = HomeCard("Libreria Replay", "resources/icons/film.svg", "resources/icons/film-hover.svg")
        self.card_list.clicked.connect(self.navigate_to_list.emit)
        grid_layout.addWidget(self.card_list, 0, 0)
        
        # Importa Nuovo Log
        self.card_import = HomeCard("Importa Nuovo Log", "resources/icons/arrow-down-tray.svg", "resources/icons/arrow-down-tray-hover.svg")
        self.card_import.clicked.connect(self.navigate_to_import.emit)
        grid_layout.addWidget(self.card_import, 0, 1)
        
        # Import Multiplo
        self.card_mass_import = HomeCard("Import Multiplo", "resources/icons/arrow-down-on-square-stack.svg", "resources/icons/arrow-down-on-square-stack-hover.svg")
        self.card_mass_import.clicked.connect(self.navigate_to_mass_import.emit)
        grid_layout.addWidget(self.card_mass_import, 0, 2)
        
        # RIGA 2
        # Meta Analysis
        self.card_meta = HomeCard("Meta Analysis", "resources/icons/chart-bar.svg", "resources/icons/chart-bar-hover.svg")
        self.card_meta.clicked.connect(self.navigate_to_meta_stats.emit)
        grid_layout.addWidget(self.card_meta, 1, 0)
        
        # Analisi Core
        self.card_core = HomeCard("Analisi Core", "resources/icons/beaker.svg", "resources/icons/beaker-hover.svg")
        self.card_core.clicked.connect(self.navigate_to_core_analysis.emit)
        grid_layout.addWidget(self.card_core, 1, 1)
        
        # Team Analysis
        self.card_team = HomeCard("Team Analysis", "resources/icons/user-group.svg", "resources/icons/user-group-hover.svg")
        self.card_team.clicked.connect(self.navigate_to_team_analysis.emit)
        grid_layout.addWidget(self.card_team, 1, 2)
        
        # RIGA 3
        # Costruisci e Confronta
        self.card_build_compare = HomeCard("Costruisci e Confronta", "resources/icons/puzzle-piece.svg", "resources/icons/puzzle-piece-hover.svg")
        self.card_build_compare.clicked.connect(self.navigate_to_build_compare.emit)
        grid_layout.addWidget(self.card_build_compare, 2, 0)
        
        # Ottimizzazione Team
        self.card_optimizer = HomeCard("Ottimizzazione Team", "resources/icons/sparkles.svg", "resources/icons/sparkles-hover.svg")
        self.card_optimizer.clicked.connect(self.navigate_to_optimizer.emit)
        grid_layout.addWidget(self.card_optimizer, 2, 1)
        
        self.card_bulk_opt = HomeCard("Bulk Optimizer (AOB)", "resources/icons/beaker.svg", "resources/icons/beaker-hover.svg")
        self.card_bulk_opt.clicked.connect(self.navigate_to_bulk_optimizer.emit)
        grid_layout.addWidget(self.card_bulk_opt, 2, 2)

        main_layout.addLayout(grid_layout)
        
        # Add footer (1.2x top bar height = 1.2 * 64 = 77 approx)
        footer = QWidget()
        footer.setFixedHeight(77)
        main_layout.addWidget(footer)
