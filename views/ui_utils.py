from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QColor, QPen

class LoadingOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.hide()
        
    def rotate(self):
        self.angle = (self.angle + 30) % 360
        self.update()
        
    def start(self):
        # Resize to cover parent
        if self.parent():
            self.resize(self.parent().size())
        self.show()
        self.timer.start(30)
        self.raise_()
        
    def stop(self):
        self.timer.stop()
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw semi-transparent background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))
        
        # Draw spinner
        center = self.rect().center()
        radius = 25
        
        painter.translate(center)
        painter.rotate(self.angle)
        
        pen = QPen(QColor(100, 200, 255)) # Ciano chiaro, coerente con stile dark
        pen.setWidth(4)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        
        # Disegna un arco che ruota (occupa 270 gradi)
        painter.drawArc(QRectF(-radius, -radius, radius * 2, radius * 2), 0, 270 * 16)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()
