from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from dotenv import load_dotenv
import os

load_dotenv()

# logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class FeatureConfig:
    league_avg_drtg: float = 114.5
    league_avg_pace: float = 98.0
    seconds_per_game: float = 48 * 60
    min_stint_seconds: float = 15.0

class StintFeatureExtractor:
    """
    Transform raw game data into feature vectors for each stint to be used in a machine learning model
    """

    def __init__(self, db_url: str, config: Optional[FeatureConfig] = None) -> None:
        self.engine: Engine = create_engine(db_url)
        self.config: FeatureConfig = config or FeatureConfig()

    def load_player_season_baselines(self, season: str) -> Dict[int, Dict[str, float]]:
        logger.info("Using league-average fallbacks for player baselines (season %s)", season)
        return {}

    def load_stint_data(self, season: str) -> pd.DataFrame:
        """
        Load stint data from the database
        """
        query = """
            SELECT 
                stint_id,
                game_id,
                team_id,
                opp_team_id,
                lineup_player_ids,
                opp_lineup_player_ids,
                duration_seconds,
                possessions,
                points_scored,
                points_allowed,
                garbage_time_flag
            FROM pbp_stints
            WHERE season = %(season)s
              AND duration_seconds >= %(min_duration)s
              AND garbage_time_flag = FALSE
        """
        logger.info(f"Extracting stint data for season {season}")
        return pd.read_sql(
            query,
            self.engine,
            params={"season": season, "min_duration": self.config.min_stint_seconds},
        )

    def compute_pace_factor(self, possessions: np.array, duration_seconds: np.array) -> np.array:
        """
        Compute the pace factor for a given stint
        """
        safe_duration = np.where(duration_seconds <= 0, np.nan, duration_seconds)
        pace = (possessions / safe_duration) * self.config.seconds_per_game
        return np.nan_to_num(pace, nan=self.config.league_avg_pace)

    def compute_environment_usage_delta(self, active_lineup: List[int], team_id: int, player_baseline: Dict[int, Dict[str, float]]) -> float:
        """
        Compute the environment usage delta for a given stint
        """
        active_usage_sum = sum(player_baseline.get(player_id, {}).get("usage", 20) for player_id in active_lineup)
        return float(100.0 - active_usage_sum)

    def extract_features(self, season: str) -> Tuple[np.array, np.array, pd.DataFrame]:
        """
        Vectorizes stint records into mathematical feature matrix X and target y.

        Feature Vector: [DRTG_opp, Stint_Pace, Delta_USG_on_off]
        Target: Lineup Net Rating per 100 possessions.
        """

        stints_df = self.load_stint_data(season)
        baselines = self.load_player_season_baselines(season)

        if stints_df.empty:
            raise ValueError(f"No stint data found for season {season}")

        logger.info(f"Formulating feature space across {len(stints_df)} validated stints...")

        # Normalize Pace
        stints_df['pace_factor'] = self.compute_pace_factor(
            stints_df['possessions'].values, 
            stints_df['duration_seconds'].values,
        )

        # Compute Environment Usage Delta
        stints_df['delta_usg_on_off'] = stints_df.apply(
            lambda row: self.compute_environment_usage_delta(
                row['lineup_player_ids'],
                row['team_id'],
                baselines,
            ),
            axis=1,
        )

        # Compute DRTG_opp
        stints_df['drtg_opp'] = stints_df["opp_lineup_player_ids"].apply(
            lambda opp_ids: np.mean(
                [baselines.get(player_id, {}).get("drtg", self.config.league_avg_drtg) for player_id in opp_ids]
            )
        )

        # Compute Target: Lineup Net Rating per 100 possessions
        safe_possessions = np.where(stints_df["possessions"] == 0, 1.0, stints_df["possessions"])
        stints_df["net_rating"] = (
            (stints_df["points_scored"] - stints_df["points_allowed"]) / safe_possessions
        ) * 100.0

        # Create feature matrix X and target vector y
        feature_columns = ["drtg_opp", "pace_factor", "delta_usg_on_off"]
        X = stints_df[feature_columns].to_numpy(dtype=np.float64)
        y = stints_df["net_rating"].to_numpy(dtype=np.float64)

        return X, y, stints_df[feature_columns + ["net_rating", "stint_id", "game_id"]]

    def export_features(self, X: np.array, y: np.ndarray, output_dir:Path, season: str) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        x_path = output_dir / f"x_{season}.joblib"
        y_path = output_dir / f"y_{season}.joblib"

        joblib.dump(X, x_path)
        joblib.dump(y, y_path)
        logger.info(f"Exported feature data for season {season} to {output_dir}")

if __name__ == "__main__":
    DB_URL = os.getenv("DATABASE_URL")
    TARGET_SEASON = "2024-25"
    ARTIFACT_DIR = Path("data/processed")

    extractor = StintFeatureExtractor(db_url=DB_URL)
    X_train, y_train, stint_df = extractor.extract_features(TARGET_SEASON)
    extractor.export_features(X_train, y_train, ARTIFACT_DIR, TARGET_SEASON)

