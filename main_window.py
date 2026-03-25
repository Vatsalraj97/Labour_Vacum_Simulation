# =============================================================================
# main_window.py  --  MainWindow: wires canvas, side panel, controls, transport
# =============================================================================

from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QWidget, QVBoxLayout,
    QDockWidget, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer

from snapshot_store  import SnapshotStore
from sim_canvas      import SimCanvas
from side_panel      import SidePanel
from controls_panel  import ControlsPanel
from transport_bar   import TransportBar
from sim_runner      import SimRunner

TOTAL_QUARTERS = 32


class MainWindow(QMainWindow):
    """
    Layout
    ------
    Central widget (vertical):
      ├── QSplitter (horizontal)
      │     ├── SimCanvas          (stretch=1)
      │     └── SidePanel          (fixed 256px)
      └── TransportBar             (fixed height 92px)

    Right dock:
      └── ControlsPanel (QDockWidget)
    """

    def __init__(self, default_scale: int = 1000):
        super().__init__()
        self.setWindowTitle('Labour Vacuum Simulator — US Manufacturing 2025–2033')
        self.setMinimumSize(1200, 720)

        self._default_scale = default_scale
        self._store         = SnapshotStore()
        self._runner: SimRunner | None = None
        self._playing       = False
        self._speed         = 4      # quarters per second
        self._sim_running   = False

        # ── Central widget ────────────────────────────────────────────────────
        central = QWidget()
        central.setStyleSheet('background: #0d1117;')
        c_layout = QVBoxLayout(central)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)

        # Horizontal splitter: canvas | side panel
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet('QSplitter::handle { background: #1f2937; }')

        self._canvas     = SimCanvas(self._store)
        self._side_panel = SidePanel()

        splitter.addWidget(self._canvas)
        splitter.addWidget(self._side_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([900, 256])

        # Transport bar
        self._transport = TransportBar()

        c_layout.addWidget(splitter, 1)
        c_layout.addWidget(self._transport, 0)

        self.setCentralWidget(central)

        # ── Controls dock ─────────────────────────────────────────────────────
        self._controls = ControlsPanel()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._controls)

        # ── Playback timer ────────────────────────────────────────────────────
        self._playback_timer = QTimer(self)
        self._playback_timer.timeout.connect(self._advance_playback)

        # ── Signal wiring ─────────────────────────────────────────────────────
        self._controls.run_requested.connect(self._start_sim)

        self._transport.play_requested.connect(self._play)
        self._transport.pause_requested.connect(self._pause)
        self._transport.step_requested.connect(self._step)
        self._transport.reset_requested.connect(self._reset)
        self._transport.speed_changed.connect(self._set_speed)
        self._transport.seek_requested.connect(self._seek)

    # ── Simulation lifecycle ──────────────────────────────────────────────────

    def _start_sim(self, params: dict, scale: int):
        # Stop any existing run
        if self._runner and self._runner.isRunning():
            self._runner.stop()
            self._runner.wait(3000)

        self._store.clear()
        self._canvas.update()
        self._sim_running = True

        self._runner = SimRunner(params_dict=params, scale=scale, parent=None)
        self._runner.quarter_ready.connect(self._on_quarter)
        self._runner.sim_complete.connect(self._on_complete)
        self._runner.sim_error.connect(self._on_error)
        self._runner.log_line.connect(lambda msg: None)   # suppress to status bar if desired
        self._runner.start()

        self._play()

    def _on_quarter(self, snap: dict):
        self._store.append(snap)
        if self._playing:
            self._store.current_index = self._store.count() - 1

        self._side_panel.update_from_snapshot(snap)
        self._transport.update_sparklines(self._store.snapshots)
        self._transport.set_position(self._store.current_index)
        self._canvas.update()

    def _on_complete(self):
        self._sim_running = False

    def _on_error(self, msg: str):
        self._sim_running = False
        self._pause()
        QMessageBox.critical(self, 'Simulation Error', msg)

    # ── Playback controls ─────────────────────────────────────────────────────

    def _play(self):
        self._playing = True
        interval = max(50, int(1000 / self._speed))
        self._playback_timer.start(interval)
        self._transport.set_playing(True)

    def _pause(self):
        self._playing = False
        self._playback_timer.stop()
        self._transport.set_playing(False)

    def _step(self):
        if self._store.current_index < self._store.count() - 1:
            self._store.current_index += 1
            self._update_ui()

    def _reset(self):
        self._pause()
        if self._store.count() > 0:
            self._store.current_index = 0
            self._update_ui()

    def _set_speed(self, n: int):
        self._speed = n
        if self._playing:
            interval = max(50, int(1000 / n))
            self._playback_timer.setInterval(interval)

    def _seek(self, q: int):
        if 0 <= q < self._store.count():
            self._store.current_index = q
            self._update_ui()

    # ── Auto-advance ─────────────────────────────────────────────────────────

    def _advance_playback(self):
        if self._store.count() == 0:
            return
        if self._store.current_index < self._store.count() - 1:
            self._store.current_index += 1
            self._update_ui()
        elif not self._sim_running:
            # Reached end of replay
            self._pause()

    # ── UI refresh ────────────────────────────────────────────────────────────

    def _update_ui(self):
        snap = self._store.get(self._store.current_index)
        if snap:
            self._side_panel.update_from_snapshot(snap)
            self._transport.update_sparklines(self._store.snapshots)
            self._transport.set_position(self._store.current_index)
        self._canvas.update()

    # ── Window close ─────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._runner and self._runner.isRunning():
            self._runner.stop()
            self._runner.wait(2000)
        event.accept()
