# =============================================================================
# sim_runner.py  --  QThread that runs the simulation (in-process or subprocess)
# =============================================================================
#
# When running as a frozen executable (PyInstaller), the simulation runs
# directly in this thread via imported modules (no subprocess available).
# When running from source, it launches `python run.py` as a subprocess
# for process isolation.
# =============================================================================

from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


def _is_frozen() -> bool:
    return getattr(sys, 'frozen', False)


class SimRunner(QThread):
    """
    Runs the simulation and emits per-quarter data as dicts.

    In frozen mode  : calls simulation modules directly in this QThread.
    In source mode  : launches `python run.py --stream-json --params` subprocess.

    Signals
    -------
    quarter_ready(dict)  : emitted for each completed quarter
    sim_complete()       : emitted when simulation finishes cleanly
    sim_error(str)       : emitted on exception or non-zero exit
    log_line(str)        : informational log messages
    """

    quarter_ready = pyqtSignal(dict)
    sim_complete  = pyqtSignal()
    sim_error     = pyqtSignal(str)
    log_line      = pyqtSignal(str)

    def __init__(self, params_dict: dict, scale: int = 1000, parent=None):
        super().__init__(parent)
        self.params_dict = params_dict
        self.scale       = scale
        self._proc: subprocess.Popen | None = None
        self._stop_flag  = False
        self._cwd = Path(__file__).parent

    # ── Thread entry point ────────────────────────────────────────────────────

    def run(self):
        if _is_frozen():
            self._run_inprocess()
        else:
            self._run_subprocess()

    # ── In-process mode (frozen exe) ─────────────────────────────────────────

    def _run_inprocess(self):
        """Run simulation directly via imported modules — used in frozen exe."""
        try:
            import run as run_module
            import config

            overrides = self.params_dict or {}
            run_module._apply_config_overrides(overrides)
            params = run_module._build_sim_params(self.scale, overrides)

            self.log_line.emit("Starting simulation...")

            from simulation import Simulation
            sim   = Simulation(params)
            snaps = sim.run()

            for snap in snaps:
                if self._stop_flag:
                    break
                record = self._snap_to_dict(snap)
                self.quarter_ready.emit(record)

            if not self._stop_flag:
                self.log_line.emit("Simulation complete.")
                self.sim_complete.emit()

        except Exception as exc:
            self.sim_error.emit(str(exc))

    @staticmethod
    def _snap_to_dict(snap) -> dict:
        per_tier = [
            {
                'tier':       t['tier'],
                'headcount':  t['headcount'],
                'vacuum':     t['vacuum'],
                'fill_pct':   t['fill_pct'],
                'demand':     t['demand_height'],
                'eff_volume': t['eff_volume'],
            }
            for t in snap.per_tube
        ]
        total_demand = sum(t['demand']     for t in per_tier)
        total_eff    = sum(t['eff_volume'] for t in per_tier)
        system_vacuum = sum(t['vacuum']    for t in per_tier)
        fill_pct      = (total_eff / total_demand) if total_demand > 0 else 0.0
        binding_tier  = max(per_tier, key=lambda t: t['vacuum'])['tier'] if per_tier else 0.0
        return {
            'year':          snap.year,
            'quarter':       snap.step,
            'total_workers': snap.total_balls,
            'system_vacuum': round(system_vacuum, 2),
            'fill_pct':      round(fill_pct, 4),
            'pool_size':     snap.pool_size,
            'binding_tier':  binding_tier,
            'per_tier':      per_tier,
            'exits':         snap.exits,
        }

    # ── Subprocess mode (source / development) ────────────────────────────────

    def _run_subprocess(self):
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            self._proc = subprocess.Popen(
                [
                    sys.executable, "-u",
                    str(self._cwd / "run.py"),
                    "--scale", str(self.scale),
                    "--stream-json",
                    "--params",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=env,
                cwd=str(self._cwd),
            )

            payload = json.dumps(self.params_dict) + "\n"
            self._proc.stdin.write(payload)
            self._proc.stdin.close()

            for raw_line in iter(self._proc.stdout.readline, ""):
                if self._stop_flag:
                    break
                line = raw_line.rstrip("\n")
                if line.startswith("JSON_QUARTER:"):
                    try:
                        data = json.loads(line[13:])
                        self.quarter_ready.emit(data)
                    except json.JSONDecodeError as exc:
                        self.log_line.emit(f"[JSON parse error] {exc}")
                elif line.startswith("LOG:"):
                    self.log_line.emit(line[4:])
                elif line.strip():
                    self.log_line.emit(line)

            self._proc.wait()
            stderr_text = self._proc.stderr.read()
            if stderr_text.strip():
                self.log_line.emit(f"STDERR: {stderr_text[:2000]}")

            if not self._stop_flag:
                if self._proc.returncode != 0:
                    self.sim_error.emit(
                        f"Process exited with code {self._proc.returncode}.\n"
                        f"{stderr_text[:500]}"
                    )
                else:
                    self.sim_complete.emit()

        except Exception as exc:
            self.sim_error.emit(str(exc))

    # ── Stop ─────────────────────────────────────────────────────────────────

    def stop(self):
        self._stop_flag = True
        if self._proc is not None:
            try:
                self._proc.terminate()
            except OSError:
                pass
