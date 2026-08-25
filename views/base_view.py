from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from config.theme import Palette, Spacing

class BaseHeaderWidget(QWidget):
    """
    Widget base con header sezione.
    Tutti i valori cromatici usano token da config.theme (Atomic Design).
    """
    def __init__(self, title_text: str):
        super().__init__()
        self.main_layout = QVBoxLayout(self)
        # Grid 8pt: LG (24) laterali, MD (16) top, LG bottom
        self.main_layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.LG)
        self.main_layout.setSpacing(Spacing.MD)

        # Header — 52px, bronzo come colore primario (Hisui Goodra palette)
        self.header_label = QLabel(title_text)
        self.header_label.setFixedHeight(52)
        self.header_label.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {Palette.PRIMARY};"
            "margin: 0; padding: 0; background: transparent; border: none;"
            "letter-spacing: 0.4px;"
            f"font-family: 'Segoe UI Variable', 'Inter', 'Segoe UI', sans-serif;"
        )
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.main_layout.addWidget(self.header_label)

    def add_content(self, widget: QWidget):
        self.main_layout.addWidget(widget)

    def add_layout(self, layout):
        self.main_layout.addLayout(layout)
