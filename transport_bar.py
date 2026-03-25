# =============================================================================
# transport_bar.py  --  Play/pause/step transport + sparkline charts
# =============================================================================

from __future__ import annotations

import pyqtgraph as pg

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSlider,
    QPushButton, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

# Suppress pyqtgraph's default OpenGL requirement message
pg.setConfigOptions(antialias=True, useOpenGL=False)

TOTAL_QUARTERS = 32
BAR_BG         = '#0d1117'
BTN_STYLE = """
    QPushButton {{
        background: {bg}; color: {fg}; font-size: 14pt;
        border: 1px solid #374151; border-radius: 6px;
        min-width: 34px; max-width: 34px;
        min-height: 34px; max-height: 34px;
    }}
    QPushButton:hover   {{ background: #374151; }}
    QPushButton:pressed {{ background: #1d4ed8; }}
    QPushButton:checked {{ background: #1d4ed8; border-color: #3b82f6; }}
"""


def _mk_btn(icon: str, bg: str = '#1f2937', fg: str = '#e2e8f0',
            checkable: bool = False) -> QPushButton:
    btn = QPushButton(icon)
    btn.setCheckable(checkable)
    btn.setStyleSheet(BTN_STYLE.format(bg=bg, fg=fg))
    return btn


def _mk_sparkline(label: str, color: str) -> tuple:
    """Return (outer_widget, PlotWidget, curve) for one sparkline."""
    outer = QWidget()
    outer.setStyleSheet('background: transparent;')
    layout = QVBoxLayout(outer)
    layout.setContentsMargins(2, 0, 2, 0)
    layout.setSpacing(1)

    lbl = QLabel(label)
    lbl.setFont(QFont('Arial', 7))
    lbl.setStyleSheet('color: #6b7280; background: transparent;')
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(lbl)

    pw = pg.PlotWidget(background=BAR_BG)
    pw.setFixedSize(110, 52)
    pw.hideAxis('bottom')
    pw.hideAxis('left')
    pw.getPlotItem().setContentsMargins(0, 0, 0, 0)
    pw.getPlotItem().layout.setContentsMargins(0, 0, 0, 0)
    curve = pw.plot(pen=pg.mkPen(color=color, width=1.5))
    layout.addWidget(pw)

    val_lbl = QLabel('—')
    val_lbl.setFont(QFont('Arial', 8))
    val_lbl.setStyleSheet(f'color: {color}; background: transparent;')
    val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(val_lbl)

    return outer, curve, val_lbl


class TransportBar(QWidget):
    """
    Fixed-height 90px transport widget.

    Signals
    -------
    play_requested, pause_requested, step_requested, reset_requested
    speed_changed(int)
    seek_requested(int)
    """

    play_requested  = pyqtSignal()
    pause_requested = pyqtSignal()
    step_requested  = pyqtSignal()
    reset_requested = pyqtSignal()
    speed_changed   = pyqtSignal(int)
    seek_requested  = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(92)
        self.setStyleSheet(f'background: {BAR_BG}; border-top: 1px solid #1f2937;')

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 4, 10, 4)
        root.setSpacing(8)

        # ── Left: transport buttons + speed ──────────────────────────────────
        left = QHBoxLayout()
        left.setSpacing(4)

        self._reset_btn = _mk_btn('↺')
        self._play_btn  = _mk_btn('▶', checkable=True)
        self._step_btn  = _mk_btn('⟩')

        for btn in (self._reset_btn, self._play_btn, self._step_btn):
            left.addWidget(btn)

        # Speed
        speed_col = QVBoxLayout()
        speed_col.setSpacing(1)
        speed_lbl = QLabel('Speed')
        speed_lbl.setFont(QFont('Arial', 7))
        speed_lbl.setStyleSheet('color: #6b7280;')
        speed_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._speed_val = QLabel('4×')
        self._speed_val.setFont(QFont('Arial', 8))
        self._speed_val.setStyleSheet('color: #d1d5db;')
        self._speed_val.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(1, 20)
        self._speed_slider.setValue(4)
        self._speed_slider.setFixedWidth(80)
        self._speed_slider.setFixedHeight(14)
        self._speed_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 3px; background: #374151; border-radius: 1px; }
            QSlider::handle:horizontal { width: 9px; height: 9px; margin: -3px 0;
                                         background: #6366f1; border-radius: 4px; }
            QSlider::sub-page:horizontal { background: #6366f1; }
        """)

        speed_col.addWidget(speed_lbl)
        speed_col.addWidget(self._speed_val)
        speed_col.addWidget(self._speed_slider)
        left.addLayout(speed_col)

        root.addLayout(left)

        # Divider
        root.addWidget(self._vline())

        # ── Middle: sparklines ────────────────────────────────────────────────
        mid = QHBoxLayout()
        mid.setSpacing(4)

        (self._vac_w, self._vac_curve, self._vac_val)   = _mk_sparkline('Vacuum',    '#ef4444')
        (self._wf_w,  self._wf_curve,  self._wf_val)    = _mk_sparkline('Workforce', '#3d9cf5')
        (self._fill_w,self._fill_curve,self._fill_val)   = _mk_sparkline('Fill %',   '#1fc8cc')
        (self._pool_w,self._pool_curve,self._pool_val)   = _mk_sparkline('Pool',     '#22c55e')

        for w in (self._vac_w, self._wf_w, self._fill_w, self._pool_w):
            mid.addWidget(w)

        root.addLayout(mid, 1)

        # Divider
        root.addWidget(self._vline())

        # ── Right: quarter indicator + replay scrubber ────────────────────────
        right = QVBoxLayout()
        right.setSpacing(2)

        self._qtr_lbl = QLabel('Q 0 / 32')
        self._qtr_lbl.setFont(QFont('Arial', 9))
        self._qtr_lbl.setStyleSheet('color: #9ca3af;')
        self._qtr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setRange(0, TOTAL_QUARTERS - 1)
        self._scrubber.setValue(0)
        self._scrubber.setFixedWidth(160)
        self._scrubber.setFixedHeight(16)
        self._scrubber.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #374151; border-radius: 2px; }
            QSlider::handle:horizontal { width: 10px; height: 10px; margin: -3px 0;
                                         background: #9b6ff5; border-radius: 5px; }
            QSlider::sub-page:horizontal { background: #9b6ff5; }
        """)

        right.addWidget(self._qtr_lbl)
        right.addWidget(self._scrubber)

        root.addLayout(right)

        # ── Connections ───────────────────────────────────────────────────────
        self._reset_btn.clicked.connect(self.reset_requested)
        self._step_btn.clicked.connect(self.step_requested)
        self._play_btn.toggled.connect(self._on_play_toggle)
        self._speed_slider.valueChanged.connect(self._on_speed)
        self._scrubber.sliderMoved.connect(self.seek_requested)

        self._scrubber_user_moved = False

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _vline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet('color: #1f2937;')
        line.setFixedWidth(1)
        return line

    def _on_play_toggle(self, checked: bool):
        self._play_btn.setText('⏸' if checked else '▶')
        if checked:
            self.play_requested.emit()
        else:
            self.pause_requested.emit()

    def _on_speed(self, v: int):
        self._speed_val.setText(f'{v}×')
        self.speed_changed.emit(v)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_playing(self, playing: bool):
        self._play_btn.blockSignals(True)
        self._play_btn.setChecked(playing)
        self._play_btn.setText('⏸' if playing else '▶')
        self._play_btn.blockSignals(False)

    def set_position(self, index: int):
        self._qtr_lbl.setText(f'Q {index + 1} / {TOTAL_QUARTERS}')
        self._scrubber.blockSignals(True)
        self._scrubber.setValue(max(0, min(TOTAL_QUARTERS - 1, index)))
        self._scrubber.blockSignals(False)

    def update_sparklines(self, snapshots: list):
        if not snapshots:
            return
        vac   = [s.get('system_vacuum', 0)   for s in snapshots]
        wf    = [s.get('total_workers', 0)   for s in snapshots]
        fill  = [s.get('fill_pct', 0) * 100  for s in snapshots]
        pool  = [s.get('pool_size', 0)       for s in snapshots]

        self._vac_curve.setData(vac)
        self._wf_curve.setData(wf)
        self._fill_curve.setData(fill)
        self._pool_curve.setData(pool)

        self._vac_val.setText(f'{vac[-1]:,.0f}')
        self._wf_val.setText(f'{wf[-1]:,}')
        self._fill_val.setText(f'{fill[-1]:.1f}%')
        self._pool_val.setText(f'{pool[-1]:,}')
