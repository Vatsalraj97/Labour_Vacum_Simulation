# =============================================================================
# controls_panel.py  --  Dockable QDockWidget with all simulation knobs
# =============================================================================

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QSlider, QLabel, QCheckBox, QScrollArea,
    QPushButton, QSpinBox, QSizePolicy, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

# ── Mechanism definitions ─────────────────────────────────────────────────────

MECHANISMS = [
    {
        "name": "Population Pipeline", "color": "#3d9cf5",
        "knobs": [
            {"id": "cohort", "label": "Annual cohort",
             "min": 2_000_000, "max": 7_000_000, "step": 100_000, "default": 4_584_041,
             "fmt": "M2",
             "desc": "Total people reaching working age in the US per year. From US Census ACS. "
                     "Declining post-2028. Absolute ceiling on manufacturing entrants."},
            {"id": "mfg_pct", "label": "Mfg entry %",
             "min": 0.04, "max": 0.15, "step": 0.005, "default": 0.085,
             "fmt": "pct1",
             "desc": "Fraction of cohort choosing manufacturing. Declining from 12% in 2000. "
                     "The single most powerful supply-side lever."},
            {"id": "ent_skill", "label": "Entry skill mean",
             "min": 0.05, "max": 0.25, "step": 0.01, "default": 0.12,
             "fmt": "f2",
             "desc": "Mean starting skill of a new entrant. Higher = better pre-employment training."},
            {"id": "immig_pct", "label": "Immigrant share",
             "min": 0.05, "max": 0.35, "step": 0.01, "default": 0.102,
             "fmt": "pct0",
             "desc": "Share of entrants who are foreign-born. BLS CPS 2023: 10.2%."},
        ],
    },
    {
        "name": "Growth Engine", "color": "#1fcc74",
        "knobs": [
            {"id": "alpha", "label": "Alpha (α)",
             "min": 0.5, "max": 3.0, "step": 0.1, "default": 1.4,
             "fmt": "f1",
             "desc": "Convexity of skill growth. α=1 linear; α=2 only near-ceiling workers grow fast."},
            {"id": "beta", "label": "Beta (β)",
             "min": 0.0, "max": 1.5, "step": 0.05, "default": 0.3,
             "fmt": "f2",
             "desc": "Crowding penalty on growth rate. β=0 no effect; β=1.5 dense tube ~60% slower."},
            {"id": "base_growth", "label": "Base growth rate",
             "min": 0.003, "max": 0.04, "step": 0.001, "default": 0.015,
             "fmt": "pct1",
             "desc": "Quarterly baseline skill growth. 1.5%/qtr ≈ 6%/yr."},
            {"id": "regression", "label": "Regression rate",
             "min": 0.01, "max": 0.5, "step": 0.01, "default": 0.08,
             "fmt": "f2",
             "desc": "Skill loss rate for overqualified workers as fraction of growth rate."},
        ],
    },
    {
        "name": "Graduation & Placement", "color": "#9b6ff5",
        "knobs": [
            {"id": "grad_mult", "label": "Grad skill threshold",
             "min": 0.70, "max": 0.99, "step": 0.01, "default": 0.90,
             "fmt": "pct0",
             "desc": "Skill fraction of tier ceiling required for graduation. 0.90 = need 90%."},
            {"id": "mgmt_rate", "label": "Management drain",
             "min": 0.05, "max": 0.60, "step": 0.01, "default": 0.30,
             "fmt": "pct0",
             "desc": "Quarterly probability eligible worker exits to management."},
            {"id": "place_sigma", "label": "Placement sigma",
             "min": 0.05, "max": 0.50, "step": 0.01, "default": 0.25,
             "fmt": "f2",
             "desc": "Hiring acceptance distribution right tail. Wider = more forgiving."},
            {"id": "pool_decay", "label": "Pool decay rate",
             "min": 0.90, "max": 1.0, "step": 0.005, "default": 0.97,
             "fmt": "f3",
             "desc": "Quarterly multiplier on pool worker placement probability."},
        ],
    },
    {
        "name": "Exit Engine", "color": "#f0a500",
        "knobs": [
            {"id": "quit_rate", "label": "Quit rate T0.1",
             "min": 0.005, "max": 0.10, "step": 0.005, "default": 0.025,
             "fmt": "pct1",
             "desc": "Quarterly within-manufacturing quit at T0.1. Scales down with tier."},
            {"id": "career_change", "label": "Career change T0.1",
             "min": 0.003, "max": 0.04, "step": 0.001, "default": 0.017,
             "fmt": "pct1",
             "desc": "Quarterly probability of permanently leaving manufacturing at T0.1."},
            {"id": "retire_thr", "label": "Retirement threshold",
             "min": 12, "max": 60, "step": 2, "default": 28,
             "fmt": "qtrs",
             "desc": "Quarters before retirement probability escalates. 28Q = 7 years."},
            {"id": "frust_base", "label": "Frustration rate",
             "min": 0.002, "max": 0.10, "step": 0.002, "default": 0.02,
             "fmt": "pct1",
             "desc": "Base quarterly probability of frustration resignation for stagnant workers."},
        ],
    },
    {
        "name": "Injury & Safety", "color": "#e84050",
        "knobs": [
            {"id": "injury_mult", "label": "Injury rate scale",
             "min": 0.1, "max": 5.0, "step": 0.1, "default": 1.0,
             "fmt": "f1",
             "desc": "Global multiplier on all injury rates. 1.0 = BLS SOII 2022 baseline."},
            {"id": "pen_mult", "label": "Injury penalty scale",
             "min": 0.1, "max": 3.0, "step": 0.1, "default": 1.0,
             "fmt": "f1",
             "desc": "Multiplier on permanent skill loss from serious injury."},
        ],
    },
    {
        "name": "Policy Shocks", "color": "#1fc8cc",
        "knobs": [
            {"id": "shock_prob", "label": "Shock probability",
             "min": 0.0, "max": 0.20, "step": 0.005, "default": 0.05,
             "fmt": "pct1",
             "desc": "Quarterly probability a policy shock fires. 5%/qtr ≈ 20% annual."},
            {"id": "shock_rem", "label": "Removal rate",
             "min": 0.005, "max": 0.10, "step": 0.005, "default": 0.02,
             "fmt": "pct1",
             "desc": "Fraction of exposed-tier workers removed when shock fires."},
            {"id": "shocks_on", "label": "Shocks enabled",
             "type": "toggle", "default": True,
             "desc": "Master toggle for all policy shock events."},
        ],
    },
    {
        "name": "Demand Signal", "color": "#f472b6",
        "knobs": [
            {"id": "ind_growth", "label": "Industry growth/yr",
             "min": 0.005, "max": 0.08, "step": 0.005, "default": 0.019,
             "fmt": "pct1",
             "desc": "Annual manufacturing output growth rate raises all tube demand heights."},
            {"id": "reshoring", "label": "Reshoring jobs",
             "min": 0, "max": 1_200_000, "step": 50_000, "default": 300_000,
             "fmt": "k0",
             "desc": "Total reshoring jobs 2025-2033 spread over 32 quarters to T0.3-T0.6."},
        ],
    },
]


def _fmt_value(value: float, fmt: str) -> str:
    if fmt == 'M2':
        return f'{value / 1_000_000:.2f}M'
    if fmt == 'pct1':
        return f'{value * 100:.1f}%'
    if fmt == 'pct0':
        return f'{value * 100:.0f}%'
    if fmt == 'f1':
        return f'{value:.1f}'
    if fmt == 'f2':
        return f'{value:.2f}'
    if fmt == 'f3':
        return f'{value:.3f}'
    if fmt == 'qtrs':
        return f'{int(value)}Q ({value / 4:.1f}yr)'
    if fmt == 'k0':
        return f'{value / 1000:.0f}k'
    return str(value)


class KnobRow(QWidget):
    """One slider row: label | slider | value-label."""

    value_changed = pyqtSignal(str, float)   # (knob_id, new_value)

    def __init__(self, knob: dict, parent=None):
        super().__init__(parent)
        self._knob = knob
        kid  = knob['id']
        kfmt = knob.get('fmt', 'f2')

        kmin  = knob['min']
        kmax  = knob['max']
        kstep = knob['step']
        kdef  = knob['default']

        num_steps = max(1, round((kmax - kmin) / kstep))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(4)

        # Label (tooltip on hover)
        lbl = QLabel(knob['label'])
        lbl.setFixedWidth(110)
        lbl.setFont(QFont('Arial', 8))
        lbl.setStyleSheet('color: #9ca3af;')
        lbl.setToolTip(f"<b>{knob['label']}</b><br><small>{knob.get('desc', '')}</small>")
        lbl.setWordWrap(False)
        layout.addWidget(lbl)

        # Slider
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, num_steps)
        init_pos = round((kdef - kmin) / kstep)
        slider.setValue(init_pos)
        slider.setFixedHeight(16)
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px; background: #374151; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 10px; height: 10px; margin: -3px 0;
                background: #6366f1; border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #6366f1; border-radius: 2px;
            }
        """)
        layout.addWidget(slider, 1)

        # Value label
        val_lbl = QLabel(_fmt_value(kdef, kfmt))
        val_lbl.setFixedWidth(52)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        val_lbl.setFont(QFont('Arial', 8))
        val_lbl.setStyleSheet('color: #d1d5db;')
        layout.addWidget(val_lbl)

        self._slider  = slider
        self._val_lbl = val_lbl

        def on_change(pos):
            v = kmin + pos * kstep
            val_lbl.setText(_fmt_value(v, kfmt))
            self.value_changed.emit(kid, v)

        slider.valueChanged.connect(on_change)

    def get_value(self) -> float:
        kmin  = self._knob['min']
        kstep = self._knob['step']
        return kmin + self._slider.value() * kstep

    def reset_default(self):
        kmin  = self._knob['min']
        kstep = self._knob['step']
        kdef  = self._knob['default']
        self._slider.setValue(round((kdef - kmin) / kstep))


class ToggleRow(QWidget):
    """Checkbox row for boolean knobs."""

    value_changed = pyqtSignal(str, bool)

    def __init__(self, knob: dict, parent=None):
        super().__init__(parent)
        self._knob = knob
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)

        cb = QCheckBox(knob['label'])
        cb.setChecked(knob.get('default', True))
        cb.setFont(QFont('Arial', 8))
        cb.setStyleSheet('color: #9ca3af;')
        cb.setToolTip(f"<b>{knob['label']}</b><br><small>{knob.get('desc', '')}</small>")
        layout.addWidget(cb)
        layout.addStretch()

        self._cb = cb
        cb.toggled.connect(lambda v: self.value_changed.emit(knob['id'], v))

    def get_value(self) -> bool:
        return self._cb.isChecked()

    def reset_default(self):
        self._cb.setChecked(self._knob.get('default', True))


class ControlsPanel(QDockWidget):
    """
    Right-dockable panel with mechanism groups, knob sliders, and run button.

    Signals
    -------
    run_requested(dict, int)  : (params_dict, scale) when user clicks RUN
    """

    run_requested = pyqtSignal(dict, int)

    def __init__(self, parent=None):
        super().__init__('Simulation Controls', parent)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        # Outer scroll container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: #111827; }
            QWidget { background: #111827; }
        """)

        container = QWidget()
        container.setStyleSheet('background: #111827;')
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(6)

        # ── Build mechanism group boxes ───────────────────────────────────────
        self._knob_rows: dict[str, KnobRow | ToggleRow] = {}

        for mech in MECHANISMS:
            grp = QGroupBox(mech['name'])
            grp.setStyleSheet(f"""
                QGroupBox {{
                    font-size: 8pt; font-weight: bold; color: {mech['color']};
                    border: 1px solid #374151;
                    border-left: 3px solid {mech['color']};
                    border-radius: 4px;
                    margin-top: 8px; padding-top: 4px;
                    background: #1f2937;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin; subcontrol-position: top left;
                    left: 8px; padding: 0 4px;
                }}
            """)
            grp_layout = QVBoxLayout(grp)
            grp_layout.setContentsMargins(6, 4, 6, 4)
            grp_layout.setSpacing(2)

            for knob in mech['knobs']:
                if knob.get('type') == 'toggle':
                    row = ToggleRow(knob)
                else:
                    row = KnobRow(knob)
                self._knob_rows[knob['id']] = row
                grp_layout.addWidget(row)

            vbox.addWidget(grp)

        # ── Bottom controls ───────────────────────────────────────────────────
        bottom = QFrame()
        bottom.setStyleSheet('background: #1f2937; border-radius: 6px; border: 1px solid #374151;')
        bot_layout = QVBoxLayout(bottom)
        bot_layout.setContentsMargins(8, 8, 8, 8)
        bot_layout.setSpacing(6)

        # Scale selector
        scale_row = QHBoxLayout()
        scale_lbl = QLabel('Scale (1 : N)')
        scale_lbl.setFont(QFont('Arial', 8))
        scale_lbl.setStyleSheet('color: #9ca3af; background: transparent; border: none;')
        self._scale_spin = QSpinBox()
        self._scale_spin.setRange(10, 10_000)
        self._scale_spin.setValue(1_000)
        self._scale_spin.setSingleStep(100)
        self._scale_spin.setStyleSheet("""
            QSpinBox { background: #374151; color: #e2e8f0; border: 1px solid #4b5563;
                       border-radius: 4px; padding: 2px 4px; font-size: 9pt; }
        """)
        scale_row.addWidget(scale_lbl)
        scale_row.addStretch()
        scale_row.addWidget(self._scale_spin)
        bot_layout.addLayout(scale_row)

        # Run button
        run_btn = QPushButton('▶  RUN SIMULATION')
        run_btn.setFixedHeight(36)
        run_btn.setStyleSheet("""
            QPushButton {
                background: #2563eb; color: #ffffff; font-weight: bold;
                font-size: 10pt; border-radius: 6px; border: none;
            }
            QPushButton:hover   { background: #3b82f6; }
            QPushButton:pressed { background: #1d4ed8; }
        """)
        run_btn.clicked.connect(self._on_run)
        bot_layout.addWidget(run_btn)

        # Reset button
        reset_btn = QPushButton('↺  Reset Defaults')
        reset_btn.setFixedHeight(26)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #374151; color: #9ca3af; font-size: 9pt;
                border-radius: 4px; border: none;
            }
            QPushButton:hover { background: #4b5563; color: #e2e8f0; }
        """)
        reset_btn.clicked.connect(self._reset_defaults)
        bot_layout.addWidget(reset_btn)

        vbox.addWidget(bottom)
        vbox.addStretch()

        scroll.setWidget(container)
        self.setWidget(scroll)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_run(self):
        params = self.collect_params()
        scale  = self._scale_spin.value()
        self.run_requested.emit(params, scale)

    def _reset_defaults(self):
        for row in self._knob_rows.values():
            row.reset_default()

    def collect_params(self) -> dict:
        """Return {knob_id: value} for all knobs."""
        return {kid: row.get_value() for kid, row in self._knob_rows.items()}
