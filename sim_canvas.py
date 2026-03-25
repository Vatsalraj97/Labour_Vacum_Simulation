# =============================================================================
# sim_canvas.py  --  QPainter-based animated simulation canvas
# =============================================================================

from __future__ import annotations
import math
import random

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QPainterPath,
    QLinearGradient, QFontMetrics,
)

from snapshot_store import SnapshotStore

# ── Tier colour palette ────────────────────────────────────────────────────────
TIER_COLORS: dict[float, str] = {
    0.1: '#6b7fa8', 0.2: '#3d9cf5', 0.3: '#1fc8cc', 0.4: '#1fcc74',
    0.5: '#9bd436', 0.6: '#f0c420', 0.7: '#f07320', 0.8: '#e84050',
    0.9: '#9b6ff5', 1.0: '#f472b6',
}

TENURE_COLORS: dict[str, str] = {
    '<8':   '#22d3ee',   # cyan
    '8-16': '#fbbf24',   # amber
    '16-28':'#f97316',   # orange
    '>28':  '#ef4444',   # red
}

TENURE_BUCKETS   = ['<8',  '<8',  '8-16', '8-16', '16-28', '16-28', '>28', '>28', '>28', '>28']
TIERS            = [round(t * 0.1, 1) for t in range(1, 11)]
NUM_POOL_SLOTS   = 350   # 250 tube-worker slots + 100 pool-worker slots
POOL_SLOT_OFFSET = 250


class SimCanvas(QWidget):
    """
    Animated QPainter canvas.  Reads from SnapshotStore.current_index.

    Layout (top → bottom):
      tubes_section   60% of (H - legend_h)
      ocean_section   35% of (H - legend_h)
      legend_strip    30 px
    """

    def __init__(self, store: SnapshotStore, parent=None):
        super().__init__(parent)
        self.store  = store
        self._phase = 0.0
        self.setMinimumSize(600, 400)

        # Pre-generate stable dot positions (avoids jumpy animation)
        self._tube_dots  = self._init_tube_dots()
        self._ocean_dots = self._init_ocean_dots()

        # 30 fps animation timer
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ── Pre-generation ─────────────────────────────────────────────────────────

    def _init_tube_dots(self) -> dict:
        """Per-tier: 6 dots each with (x_frac, y_jitter, tenure_bucket)."""
        result = {}
        for tier in TIERS:
            rng = random.Random(int(tier * 1000))
            result[tier] = [
                (
                    rng.uniform(0.12, 0.88),
                    rng.uniform(-4.0, 4.0),
                    rng.choice(TENURE_BUCKETS),
                )
                for _ in range(6)
            ]
        return result

    def _init_ocean_dots(self) -> list:
        """
        350 slots: [0..249] = tube-worker colours per tier (25 each),
                   [250..349] = pool workers.
        Each entry: (x_frac, y_frac, phase_offset, tier_or_None).
        """
        dots = []
        rng  = random.Random(42)
        for i, tier in enumerate(TIERS):
            for _ in range(25):
                dots.append((
                    rng.uniform(0.01, 0.99),
                    rng.uniform(0.05, 0.95),
                    rng.uniform(0.0, 2 * math.pi),
                    tier,
                ))
        for _ in range(100):
            dots.append((
                rng.uniform(0.01, 0.99),
                rng.uniform(0.05, 0.95),
                rng.uniform(0.0, 2 * math.pi),
                None,   # pool worker
            ))
        return dots

    # ── Animation tick ─────────────────────────────────────────────────────────

    def _tick(self):
        self._phase += 0.04
        if self._phase > 20 * math.pi:
            self._phase -= 20 * math.pi
        self.update()

    # ── paintEvent ────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H     = self.width(), self.height()
        LEGEND_H = 28
        snap     = self.store.get(self.store.current_index)

        # Background
        p.fillRect(0, 0, W, H, QColor('#0d1117'))

        if snap is None:
            self._draw_idle(p, W, H)
            return

        available     = H - LEGEND_H
        ocean_h       = max(80, int(available * 0.35))
        tubes_h       = available - ocean_h
        ocean_y       = tubes_h
        legend_y      = H - LEGEND_H

        self._draw_year_watermark(p, snap, W, H)
        self._draw_tubes(p, snap, W, tubes_h)
        self._draw_ocean(p, snap, W, ocean_y, ocean_h)
        self._draw_legend(p, W, legend_y, LEGEND_H)

    # ── Idle state ─────────────────────────────────────────────────────────────

    def _draw_idle(self, p: QPainter, W: int, H: int):
        p.setPen(QColor('#334155'))
        p.setFont(QFont('Arial', 15))
        p.drawText(QRect(0, 0, W, H), Qt.AlignmentFlag.AlignCenter,
                   'IDLE — press Play to run simulation')

    # ── Year watermark ─────────────────────────────────────────────────────────

    def _draw_year_watermark(self, p: QPainter, snap: dict, W: int, H: int):
        year_str = f"{snap.get('year', ''):.2f}"
        p.save()
        p.setPen(QColor(255, 255, 255, 12))
        font = QFont('Arial', int(H * 0.22))
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRect(0, 0, W, H), Qt.AlignmentFlag.AlignCenter, year_str)
        p.restore()

    # ── Tubes section ──────────────────────────────────────────────────────────

    def _draw_tubes(self, p: QPainter, snap: dict, W: int, section_h: int):
        per_tier = sorted(snap.get('per_tier', []), key=lambda x: x['tier'])
        if not per_tier:
            return

        n         = len(per_tier)
        margin    = 18
        gap       = 5
        label_top = 18      # space for tier label above tube
        hc_bot    = 18      # space for headcount below tube
        tube_draw_h = section_h - label_top - hc_bot
        tube_top  = label_top
        tube_bot  = label_top + tube_draw_h

        total_w   = W - 2 * margin - gap * (n - 1)
        tube_w    = total_w / n

        for i, t in enumerate(per_tier):
            tier      = t['tier']
            x         = margin + i * (tube_w + gap)
            color_hex = TIER_COLORS.get(tier, '#888888')
            tc        = QColor(color_hex)

            fill = max(0.0, min(1.0, t.get('fill_pct', 0.0)))
            fluid_h = tube_draw_h * fill
            fluid_y = tube_bot - fluid_h

            # Background of tube
            p.fillRect(int(x), tube_top, int(tube_w), tube_draw_h,
                       QColor('#111827'))

            # Fluid gradient fill
            if fluid_h > 1:
                grad = QLinearGradient(x, fluid_y, x, tube_bot)
                c1 = QColor(tc); c1.setAlpha(210)
                c2 = QColor(tc); c2.setAlpha(90)
                grad.setColorAt(0.0, c2)
                grad.setColorAt(1.0, c1)
                p.fillRect(int(x), int(fluid_y), int(tube_w), int(fluid_h), grad)

            # Demand line (top of tube = full demand)
            demand_y = tube_top
            pen = QPen(QColor('#ef4444'), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(int(x), demand_y, int(x + tube_w), demand_y)

            # Vacuum hatching between demand line and fluid surface
            gap_px = int(fluid_y) - demand_y
            if gap_px > 1:
                p.save()
                hatch = QBrush(QColor(239, 68, 68, 35), Qt.BrushStyle.BDiagPattern)
                p.fillRect(int(x), demand_y, int(tube_w), gap_px, hatch)
                p.restore()

            # Tube border
            p.setPen(QPen(QColor('#1f2937'), 1))
            p.drawRect(int(x), tube_top, int(tube_w), tube_draw_h)

            # Worker dots on fluid surface (max 6)
            self._draw_surface_dots(p, t, int(x), int(fluid_y), int(tube_w))

            # Tier label above
            p.save()
            p.setPen(QColor(color_hex))
            f = QFont('Arial', 7); f.setBold(True)
            p.setFont(f)
            p.drawText(int(x), 1, int(tube_w), label_top - 1,
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                       f'T{tier:.1f}')
            p.restore()

            # Headcount below
            p.save()
            p.setPen(QColor('#4b5563'))
            p.setFont(QFont('Arial', 7))
            p.drawText(int(x), tube_bot + 2, int(tube_w), hc_bot - 2,
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       str(t.get('headcount', 0)))
            p.restore()

            # Vacuum % label (only if notable)
            vac_pct = 1.0 - fill
            if vac_pct > 0.03 and gap_px > 12:
                p.save()
                p.setPen(QColor('#f87171'))
                p.setFont(QFont('Arial', 6))
                label_y = demand_y + max(2, gap_px // 2 - 6)
                p.drawText(int(x), label_y, int(tube_w), 12,
                           Qt.AlignmentFlag.AlignHCenter,
                           f'{vac_pct * 100:.0f}%↑')
                p.restore()

    def _draw_surface_dots(self, p: QPainter, t: dict, x: int, fluid_y: int, tw: int):
        hc   = t.get('headcount', 0)
        tier = t.get('tier', 0.1)
        if hc == 0:
            return
        n_dots = min(hc, 6)
        dot_defs = self._tube_dots.get(tier, [])[:n_dots]
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        for x_frac, y_jit, tb in dot_defs:
            dx  = int(x + x_frac * tw)
            dy  = fluid_y + int(y_jit)
            col = QColor(TENURE_COLORS.get(tb, '#ffffff'))
            col.setAlpha(220)
            p.setBrush(QBrush(col))
            p.drawEllipse(QPoint(dx, dy), 3, 3)
        p.restore()

    # ── Ocean section ──────────────────────────────────────────────────────────

    def _draw_ocean(self, p: QPainter, snap: dict, W: int, ocean_y: int, ocean_h: int):
        per_tier   = snap.get('per_tier', [])
        pool_size  = snap.get('pool_size', 0)
        total_hc   = sum(t.get('headcount', 0) for t in per_tier)

        # Background
        p.fillRect(0, ocean_y, W, ocean_h, QColor('#070d1a'))

        # Separator
        p.setPen(QPen(QColor('#1e3a5f'), 1))
        p.drawLine(0, ocean_y, W, ocean_y)

        # Label
        p.setPen(QColor('#2d4a6b'))
        f = QFont('Arial', 7)
        p.setFont(f)
        label = f"TALENT POOL  ·  {pool_size:,} workers between placements"
        p.drawText(8, ocean_y + 2, W - 16, 16,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, label)

        content_y = ocean_y + 18
        content_h = ocean_h - 18
        if content_h < 10:
            return

        # Wave layers
        self._draw_waves(p, W, content_y, content_h)

        # Tube worker dots
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        for i, t in enumerate(sorted(per_tier, key=lambda x: x['tier'])):
            tier = t['tier']
            hc   = t.get('headcount', 0)
            if hc == 0 or total_hc == 0:
                continue
            n_dots = min(int(hc / total_hc * 250), 25)
            col = QColor(TIER_COLORS.get(tier, '#888888'))
            col.setAlpha(140)
            p.setBrush(QBrush(col))
            slot_base = i * 25
            for j in range(n_dots):
                idx = slot_base + j
                if idx >= POOL_SLOT_OFFSET:
                    break
                x_f, y_f, ph, _ = self._ocean_dots[idx]
                dx = 5 * math.sin(self._phase + ph)
                dy = 3 * math.cos(self._phase * 0.7 + ph)
                ox = max(2, min(W - 4, int(W * x_f + dx)))
                oy = max(content_y + 2,
                         min(content_y + content_h - 4,
                             int(content_y + content_h * y_f + dy)))
                p.drawEllipse(QPoint(ox, oy), 2, 2)
        p.restore()

        # Pool worker dots (amber, pulsing)
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        n_pool_dots = min(pool_size, 80)
        amber = QColor('#fbbf24')
        for j in range(n_pool_dots):
            idx = POOL_SLOT_OFFSET + (j % 100)
            x_f, y_f, ph, _ = self._ocean_dots[idx]
            dx = 8  * math.sin(self._phase * 1.3 + ph)
            dy = 5  * math.cos(self._phase * 0.9 + ph)
            r  = max(2, int(3 + 1.5 * math.sin(self._phase * 2.5 + ph)))
            ox = max(r, min(W - r - 1, int(W * x_f + dx)))
            oy = max(content_y + r,
                     min(content_y + content_h - r - 1,
                         int(content_y + content_h * y_f + dy)))
            amber.setAlpha(180)
            p.setBrush(QBrush(QColor(amber)))
            p.drawEllipse(QPoint(ox, oy), r, r)
        p.restore()

    def _draw_waves(self, p: QPainter, W: int, y_start: int, h: int):
        for wi in range(2):
            ps   = wi * math.pi / 2.5
            amp  = 6 - wi * 2
            yb   = y_start + int(h * (0.25 + wi * 0.18))
            path = QPainterPath()
            path.moveTo(0, yb)
            steps = 80
            for k in range(steps + 1):
                xk = W * k / steps
                yk = yb + amp * math.sin(xk / W * 5 * math.pi + self._phase + ps)
                path.lineTo(xk, yk)
            path.lineTo(W, y_start + h)
            path.lineTo(0, y_start + h)
            path.closeSubpath()
            wc = QColor(20, 80, 160, 25 - wi * 8)
            p.fillPath(path, wc)

    # ── Legend strip ───────────────────────────────────────────────────────────

    def _draw_legend(self, p: QPainter, W: int, legend_y: int, legend_h: int):
        p.fillRect(0, legend_y, W, legend_h, QColor('#0a0f1a'))
        p.setPen(QPen(QColor('#1e2d3e'), 1))
        p.drawLine(0, legend_y, W, legend_y)

        items = [
            ('—  demand',     '#ef4444',  True),
            ('▓  supply',     '#1fcc74',  False),
            ('░  vacuum',     '#f87171',  False),
            ('●  pool',       '#fbbf24',  False),
            ('●  retirement', '#ef4444',  False),
        ]
        p.setFont(QFont('Arial', 7))
        x = 10
        for label, col, _ in items:
            p.setPen(QColor(col))
            p.drawText(x, legend_y, 90, legend_h,
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       label)
            x += 92
