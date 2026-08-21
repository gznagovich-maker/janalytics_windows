from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class BaseHeaderWidget(QWidget):
    def __init__(self, title_text: str):
        super().__init__()
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 0, 20, 20)
        
        # Header alto 84px (1.2 * 70px della navbar)
        self.header_label = QLabel(title_text)
        self.header_label.setFixedHeight(84)
        self.header_label.setStyleSheet("font-size: 28px; font-weight: 900; color: #ffcc00; margin: 0; padding: 0;")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        self.main_layout.addWidget(self.header_label)
        
    def add_content(self, widget: QWidget):
        self.main_layout.addWidget(widget)
        
    def add_layout(self, layout):
        self.main_layout.addLayout(layout)
