"""
widgets/loading_overlay.py
══════════════════════════════════════════════════════════════════════
LoadingOverlay — Spinner semitrasparente che copre il widget padre.

Design: "Hisui Goodra" — arco rotante bronzo/oro su overlay nero.

Principi applicati:
  - Nielsen #1 (Visibilità Stato Sistema): l'utente vede SEMPRE che
    il sistema sta elaborando, eliminando l'ambiguità dello "freeze".
  - Motion Design (Feedback): la rotazione continua a ~60fps dà
    un segnale temporale preciso dell'attesa.
  - WCAG 1.4.3: il testo "Elaborazione..." ha contrasto 14:1 su nero.

Uso:
    overlay = LoadingOverlay(parent_widget)
    overlay.show("Calcolo in corso...")   # mostra con messaggio
    overlay.hide()                        # nasconde
══════════════════════════════════════════════════════════════════════
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics


class LoadingOverlay(QWidget):
    """
    Widget overlay con spinner rotante. Si ridimensiona automaticamente
    al genitore. Non cattura eventi di tastiera — solo oscura e blocca
    i clic sul contenuto sottostante.
    """

    # Costanti di design (palette Hisui Goodra)
    _COLOR_BG   = QColor(0, 0, 0, 210)       # Nero 82% opacità
    _COLOR_RING = QColor(40, 44, 54, 255)     # Anello base grigio acciaio
    _COLOR_ARC  = QColor(196, 154, 60, 255)   # Bronzo primario
    _COLOR_TEXT = QColor(222, 218, 212, 220)  # Bianco caldo 86% opacità

    def __init__(self, parent: QWidget):
        super().__init__(parent)

        # Semitrasparenza corretta — non opaco, non invisibile ai clic
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._angle: int = 0          # angolo corrente arco rotante
        self._message: str = "Elaborazione in corso..."

        # Timer 60fps per la rotazione fluida
        self._timer = QTimer(self)
        self._timer.setInterval(16)   # 16ms ≈ 60fps
        self._timer.timeout.connect(self._tick)

        self.hide()

    # ── Public API ─────────────────────────────────────────────────
    def show(self, message: str = "Elaborazione in corso..."):  # type: ignore[override]
        self._message = message
        self._angle = 0
        self.resize(self.parent().size())
        self.raise_()
        super().show()
        self._timer.start()

    def hide(self):  # type: ignore[override]
        self._timer.stop()
        super().hide()

    # ── Qt Overrides ───────────────────────────────────────────────
    def resizeEvent(self, event):
        """Si ridimensiona al genitore quando il genitore cambia size."""
        if self.parent():
            self.resize(self.parent().size())
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        # ── 1. Overlay semitrasparente ──────────────────────────────
        painter.fillRect(self.rect(), self._COLOR_BG)

        # ── 2. Card sfondo centrale (opzionale, migliora leggibilità) ──
        card_w, card_h = 160, 160
        card_r = QRectF(cx - card_w // 2, cy - card_h // 2, card_w, card_h)
        painter.setBrush(QColor(13, 15, 20, 240))
        painter.setPen(QPen(QColor(44, 47, 56), 1))
        painter.drawRoundedRect(card_r, 12, 12)

        # ── 3. Anello di sfondo (grigio acciaio) ───────────────────
        radius = 34
        ring_pen = QPen(self._COLOR_RING, 4)
        ring_pen.setCapStyle(Qt.FlatCap)
        painter.setPen(ring_pen)
        ring_rect = QRectF(cx - radius, cy - radius - 16, radius * 2, radius * 2)
        painter.drawArc(ring_rect, 0, 360 * 16)

        # ── 4. Arco rotante bronzo (270° con cap rotondo) ──────────
        arc_pen = QPen(self._COLOR_ARC, 4)
        arc_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(arc_pen)
        start_angle = (90 - self._angle) * 16
        span_angle  = -270 * 16
        painter.drawArc(ring_rect, start_angle, span_angle)

        # ── 5. Messaggio testuale sotto lo spinner ─────────────────
        font = QFont("Segoe UI Variable", 11)
        font.setWeight(QFont.Weight.Medium)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        painter.setFont(font)
        painter.setPen(self._COLOR_TEXT)

        text_rect = QRect(cx - 120, cy + radius - 16 + 12, 240, 28)
        painter.drawText(text_rect, Qt.AlignCenter, self._message)

        painter.end()

    # ── Private ────────────────────────────────────────────────────
    def _tick(self):
        """Avanza l'angolo di 6° per ogni tick (360/60fps = 1 giro/sec)."""
        self._angle = (self._angle + 6) % 360
        self.update()
