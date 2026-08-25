from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon


class AnimatedMenuButton(QPushButton):
    """
    Bottone animato per il menu laterale.
    - Anima l'icona con un effetto bounce al passaggio del mouse (OutBack easing).
    - Scambia automaticamente tra icona normale (viola Goodra #A69ACA)
      e icona hover (viola chiaro #C8BEE8).
    """
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)

        self.default_icon_size = QSize(20, 20)
        self.hover_icon_size   = QSize(25, 25)

        self.setIconSize(self.default_icon_size)

        # Animazione sulla proprietà iconSize (Q_PROPERTY built-in in QPushButton)
        self.anim = QPropertyAnimation(self, b"iconSize")
        self.anim.setDuration(280)
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack)

        # Le icone vengono impostate dal chiamante via setIcon()
        # Qui prepariamo solo i riferimenti ai path hover
        self._normal_icon: QIcon | None = None
        self._hover_icon:  QIcon | None = None

    # ── API pubblica ────────────────────────────────────────────────
    def setIcons(self, normal_path: str, hover_path: str) -> None:
        """Imposta entrambe le varianti dell'icona (normale e hover)."""
        self._normal_icon = QIcon(normal_path)
        self._hover_icon  = QIcon(hover_path)
        self.setIcon(self._normal_icon)

    # ── Overrides eventi mouse ──────────────────────────────────────
    def enterEvent(self, event):
        self.anim.stop()
        self.anim.setStartValue(self.iconSize())
        self.anim.setEndValue(self.hover_icon_size)
        self.anim.start()
        if self._hover_icon:
            self.setIcon(self._hover_icon)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.anim.stop()
        self.anim.setStartValue(self.iconSize())
        self.anim.setEndValue(self.default_icon_size)
        self.anim.start()
        if self._normal_icon:
            self.setIcon(self._normal_icon)
        super().leaveEvent(event)
