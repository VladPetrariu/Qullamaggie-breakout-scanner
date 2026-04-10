"""Simple file-based cache for DataFrames and JSON objects."""

import json
import time
from pathlib import Path

import pandas as pd


class Cache:
    def __init__(self, cache_dir: str | Path):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    # -- DataFrame (parquet) -------------------------------------------------

    def get_df(self, key: str, max_age_hours: float = 24) -> pd.DataFrame | None:
        path = self.dir / f"{key}.parquet"
        if not path.exists():
            return None
        if self._is_stale(path, max_age_hours):
            return None
        try:
            return pd.read_parquet(path)
        except Exception:
            path.unlink(missing_ok=True)
            return None

    def set_df(self, key: str, df: pd.DataFrame) -> None:
        path = self.dir / f"{key}.parquet"
        df.to_parquet(path, index=True)

    # -- JSON ----------------------------------------------------------------

    def get_json(self, key: str, max_age_hours: float = 24):
        path = self.dir / f"{key}.json"
        if not path.exists():
            return None
        if self._is_stale(path, max_age_hours):
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            path.unlink(missing_ok=True)
            return None

    def set_json(self, key: str, data) -> None:
        path = self.dir / f"{key}.json"
        with open(path, "w") as f:
            json.dump(data, f)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _is_stale(path: Path, max_age_hours: float) -> bool:
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        return age_hours > max_age_hours
