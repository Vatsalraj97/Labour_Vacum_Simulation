# =============================================================================
# snapshot_store.py  --  In-memory list of per-quarter simulation snapshots
# =============================================================================

class SnapshotStore:
    """
    Holds all quarter snapshots produced by SimRunner.
    Each snapshot is a plain dict with keys:
      year, quarter, total_workers, system_vacuum, fill_pct, pool_size,
      binding_tier, per_tier (list of dicts), exits (dict)

    current_index controls which quarter the canvas and side panel display.
    """

    def __init__(self):
        self.snapshots: list = []
        self.current_index: int = -1

    def clear(self):
        self.snapshots = []
        self.current_index = -1

    def append(self, snapshot_dict: dict):
        self.snapshots.append(snapshot_dict)
        if self.current_index < 0:
            self.current_index = 0

    def get(self, index: int):
        if 0 <= index < len(self.snapshots):
            return self.snapshots[index]
        return None

    def latest(self):
        return self.snapshots[-1] if self.snapshots else None

    def count(self) -> int:
        return len(self.snapshots)
