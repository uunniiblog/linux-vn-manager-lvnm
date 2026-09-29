from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox

class ToggleSwitch(QCheckBox):
    """A palette-aware, checkable On/Off switch."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(160)
        self.setMinimumHeight(68)
        self._position = 1.0 if self.isChecked() else 0.0

        self._animation = QVariantAnimation(self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._on_animation_value)
        self.toggled.connect(self._animate_to_state)

    def sizeHint(self):
        return QSize(160, 68)

    def minimumSizeHint(self):
        return QSize(160, 64)

    def hitButton(self, position):
        """Make the complete custom-painted control clickable."""
        return self.rect().contains(position)

    def sync_visual_state(self):
        """Immediately synchronize the knob after a signal-blocked update."""
        self._animation.stop()
        self._position = 1.0 if self.isChecked() else 0.0
        self.update()

    def _animate_to_state(self, checked):
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def _on_animation_value(self, value):
        self._position = float(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        palette = self.palette()
        text_color = palette.color(palette.ColorRole.WindowText)
        accent = palette.color(palette.ColorRole.Highlight)
        off_track = palette.color(palette.ColorRole.Mid)
        knob_color = QColor("#f5f5f5")

        if not self.isEnabled():
            text_color = palette.color(palette.ColorRole.PlaceholderText)
            accent.setAlpha(110)
            off_track.setAlpha(90)
            knob_color.setAlpha(160)
        elif self.underMouse():
            accent = accent.lighter(112)
            off_track = off_track.lighter(112)

        label_rect = QRectF(0, 0, self.width(), 27)
        painter.setPen(text_color)
        label_font = self.font()
        label_font.setBold(True)
        painter.setFont(label_font)
        painter.drawText(label_rect, Qt.AlignCenter, self.text())

        track_width = 58.0
        track_height = 30.0
        track_x = (self.width() - track_width) / 2.0
        track_y = 31.0
        track_rect = QRectF(track_x, track_y, track_width, track_height)

        track_color = self._blend(off_track, accent, self._position)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, track_height / 2.0, track_height / 2.0)

        knob_diameter = 24.0
        knob_margin = (track_height - knob_diameter) / 2.0
        knob_start = track_x + knob_margin
        knob_end = track_x + track_width - knob_diameter - knob_margin
        knob_x = knob_start + ((knob_end - knob_start) * self._position)
        knob_rect = QRectF(knob_x, track_y + knob_margin, knob_diameter, knob_diameter)

        painter.setBrush(knob_color)
        painter.drawEllipse(knob_rect)

        if self.hasFocus():
            focus_color = QColor(accent)
            focus_color.setAlpha(190)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(focus_color, 2))
            painter.drawRoundedRect(track_rect.adjusted(-2, -2, 2, 2), 18, 18)

    @staticmethod
    def _blend(start: QColor, end: QColor, amount: float) -> QColor:
        amount = max(0.0, min(1.0, amount))
        inverse = 1.0 - amount
        return QColor(
            round(start.red() * inverse + end.red() * amount),
            round(start.green() * inverse + end.green() * amount),
            round(start.blue() * inverse + end.blue() * amount),
            round(start.alpha() * inverse + end.alpha() * amount),
        )
