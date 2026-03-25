# =============================================================================
# side_panel.py  --  Collapsible right panel with macro metric cards
# =============================================================================

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QFrame, QScrollArea, QPushButton,
    QGridLayout, QSizePolicy,
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QFont

PANEL_WIDTH = 256
BG_COLOR    = '#111827'
CARD_COLOR  = '#1f2937'
TEXT_MUTED  = '#6b7280'
TEXT_MAIN   = '#e2e8f0'


def _qss_card():
    return f"""
        QFrame {{
            background: {CARD_COLOR};
            border-radius: 6px;
            border: 1px solid #374151;
        }}
    """


def _mk_label(text: str, size: int = 9, bold: bool = False, color: str = TEXT_MAIN) -> QLabel:
    lbl = QLabel(text)
    f   = QFont('Arial', size)
    f.setBold(bold)
    lbl.setFont(f)
    lbl.setStyleSheet(f'color: {color};')
    return lbl


def _mk_bar(color: str, height: int = 4) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setFixedHeight(height)
    bar.setTextVisible(False)
    bar.setStyleSheet(f"""
        QProgressBar {{
            background: #374151;
            border-radius: 2px;
            border: none;
        }}
        QProgressBar::chunk {{
            background: {color};
            border-radius: 2px;
        }}
    """)
    return bar


class MetricCard(QFrame):
    """Single metric card with title, value, bar, and trend arrow."""

    def __init__(self, title: str, value_color: str, bar_color: str,
                 description: str = '', parent=None):
        super().__init__(parent)
        self.setStyleSheet(_qss_card())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        # Title row
        top = QHBoxLayout()
        top.setSpacing(4)
        self._title_lbl  = _mk_label(title, 7, color=TEXT_MUTED)
        self._trend_lbl  = _mk_label('', 9, bold=True)
        top.addWidget(self._title_lbl)
        top.addStretch()
        top.addWidget(self._trend_lbl)
        layout.addLayout(top)

        # Value
        self._value_lbl = _mk_label('—', 14, bold=True, color=value_color)
        layout.addWidget(self._value_lbl)

        # Description
        if description:
            layout.addWidget(_mk_label(description, 7, color=TEXT_MUTED))

        # Progress bar
        self._bar = _mk_bar(bar_color)
        layout.addWidget(self._bar)

        self._prev_value: float | None = None
        self._value_color = value_color

    def set_value(self, value: float, bar_pct: float,
                  fmt_str: str = '{:.1f}', unit: str = ''):
        trend = ''
        if self._prev_value is not None:
            if value > self._prev_value:
                trend = '▲'
                trend_col = '#ef4444'
            elif value < self._prev_value:
                trend = '▼'
                trend_col = '#22c55e'
            else:
                trend = '—'
                trend_col = TEXT_MUTED
            self._trend_lbl.setText(trend)
            self._trend_lbl.setStyleSheet(f'color: {trend_col};')

        self._prev_value = value
        self._value_lbl.setText(fmt_str.format(value) + unit)
        self._bar.setValue(max(0, min(100, int(bar_pct * 100))))


class TierGrid(QFrame):
    """2×5 grid showing fill% per tier, colour-coded."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_qss_card())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        layout.addWidget(_mk_label('TIER FILL %', 7, color=TEXT_MUTED))

        grid = QGridLayout()
        grid.setSpacing(4)
        self._cells: dict[float, tuple] = {}

        tiers = [round(t * 0.1, 1) for t in range(1, 11)]
        for idx, tier in enumerate(tiers):
            row = idx // 5
            col = idx % 5
            cell = QFrame()
            cell.setFixedSize(40, 32)
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(2, 2, 2, 2)
            cell_layout.setSpacing(0)
            lbl_t = _mk_label(f'T{tier:.1f}', 6, color=TEXT_MUTED)
            lbl_v = _mk_label('—', 8, bold=True)
            lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.addWidget(lbl_t)
            cell_layout.addWidget(lbl_v)
            self._cells[tier] = (cell, lbl_v)
            grid.addWidget(cell, row, col)

        layout.addLayout(grid)

    def update_tiers(self, per_tier: list):
        for t in per_tier:
            tier  = t['tier']
            fp    = t.get('fill_pct', 0.0)
            cell, lbl = self._cells.get(tier, (None, None))
            if lbl is None:
                continue
            pct = fp * 100
            lbl.setText(f'{pct:.0f}%')
            if pct >= 80:
                col = '#22c55e'
            elif pct >= 50:
                col = '#fbbf24'
            elif pct >= 30:
                col = '#f97316'
            else:
                col = '#ef4444'
            lbl.setStyleSheet(f'color: {col};')
            cell.setStyleSheet(
                f'background: {col}18; border-radius: 4px; border: 1px solid {col}44;'
            )


class SidePanel(QWidget):
    """Fixed-width right panel with collapsible toggle."""

    EXPANDED_WIDTH = PANEL_WIDTH

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.EXPANDED_WIDTH)
        self.setStyleSheet(f'background: {BG_COLOR};')
        self._expanded = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Toggle button
        self._toggle_btn = QPushButton('◀ Metrics')
        self._toggle_btn.setFixedHeight(28)
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background: #1f2937; color: #9ca3af;
                border: none; border-bottom: 1px solid #374151;
                font-size: 9px;
            }
            QPushButton:hover { background: #374151; color: #e2e8f0; }
        """)
        self._toggle_btn.clicked.connect(self._toggle)
        outer.addWidget(self._toggle_btn)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet('QScrollArea { border: none; background: transparent; }')
        self._scroll = scroll

        content = QWidget()
        content.setStyleSheet(f'background: {BG_COLOR};')
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 6)
        self._content_layout.setSpacing(5)

        # ── Metric cards ──────────────────────────────────────────────────────
        self._vacuum_card  = MetricCard('SYSTEM VACUUM',    '#ef4444', '#ef4444',
                                        'effective worker shortfall')
        self._fill_card    = MetricCard('SYSTEM FILL %',    '#0ea5e9', '#0ea5e9')
        self._wf_card      = MetricCard('WORKFORCE',         '#3d9cf5', '#3d9cf5')
        self._pool_card    = MetricCard('TALENT POOL',       '#22c55e', '#22c55e',
                                        'workers seeking placement')
        self._retire_card  = MetricCard('RETIREMENT PRESSURE', '#f97316', '#f97316',
                                        'tenure > threshold')
        self._mgmt_card    = MetricCard('MANAGEMENT DRAIN', '#9b6ff5', '#9b6ff5')
        self._flow_card    = MetricCard('NET FLOW / QTR',   '#22c55e', '#22c55e',
                                        'entries + placements - exits')

        for card in [self._vacuum_card, self._fill_card, self._wf_card,
                     self._pool_card, self._retire_card, self._mgmt_card,
                     self._flow_card]:
            self._content_layout.addWidget(card)

        # Tier grid
        self._tier_grid = TierGrid()
        self._content_layout.addWidget(self._tier_grid)
        self._content_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # Track previous snapshot for net-flow calculation
        self._prev_snap: dict | None = None

    # ── Toggle ────────────────────────────────────────────────────────────────

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.setFixedWidth(self.EXPANDED_WIDTH)
            self._toggle_btn.setText('◀ Metrics')
            self._scroll.show()
        else:
            self.setFixedWidth(28)
            self._toggle_btn.setText('▶')
            self._scroll.hide()

    # ── Update ────────────────────────────────────────────────────────────────

    def update_from_snapshot(self, snap: dict):
        if not self._expanded:
            self._prev_snap = snap
            return

        total_w  = snap.get('total_workers', 0)
        vac      = snap.get('system_vacuum', 0.0)
        fill     = snap.get('fill_pct', 0.0)
        pool     = snap.get('pool_size', 0)
        per_tier = snap.get('per_tier', [])
        exits    = snap.get('exits', {})

        # Estimate retirement pressure from stagnant / high-tenure workers
        # proxy: workers in tiers 0.7-1.0 × stagnant_frac — not in snapshot,
        # so we just track exits_retirement as the best available signal
        retire_exits = exits.get('retirement', 0)
        mgmt_exits   = exits.get('management_graduation', 0)

        # Net flow
        entries    = exits.get('entry', 0)
        placements = exits.get('placement', 0)
        perm_exits = sum(exits.get(k, 0) for k in
                         ('retirement', 'fatal_injury', 'shock_removal',
                          'frustration_quit', 'career_change', 'discouragement',
                          'management_graduation'))
        net_flow   = entries + placements - perm_exits

        # Max workers reference (initial scale ~9500 at scale 1000)
        max_wf_ref = max(total_w * 1.5, 1)

        self._vacuum_card.set_value(vac, min(vac / max(vac + total_w * 0.5, 1), 1.0),
                                    '{:,.0f}')
        self._fill_card.set_value(fill * 100, fill, '{:.1f}', '%')
        self._wf_card.set_value(total_w, min(total_w / max_wf_ref, 1.0),
                                '{:,}', '')
        self._pool_card.set_value(pool, min(pool / max(total_w + pool, 1), 1.0),
                                  '{:,}', '')
        self._retire_card.set_value(retire_exits, min(retire_exits / max(total_w * 0.05, 1), 1.0),
                                    '{:,}', '/qtr')
        self._mgmt_card.set_value(mgmt_exits, min(mgmt_exits / max(total_w * 0.02, 1), 1.0),
                                   '{:,}', '/qtr')

        flow_color = '#22c55e' if net_flow >= 0 else '#ef4444'
        self._flow_card._value_lbl.setStyleSheet(f'color: {flow_color};')
        self._flow_card.set_value(net_flow, 0.5 + net_flow / max(abs(net_flow) * 4, 1),
                                  '{:+,}', '')

        self._tier_grid.update_tiers(per_tier)
        self._prev_snap = snap
