from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from dotenv import load_dotenv
import os

from src.models.lineup_keys import canonical_lineup_key

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@dataclass
class EvaluationConfig:
    home_court_advantage: float = 2.45        # Net rating boost per 100 possessions
    default_game_pace: float = 98.5           # League baseline possessions per 48 mins

@dataclass
class EvaluationReport:
    total_games_evaluated: int
    mean_absolute_error: float
    root_mean_square_error: float
    within_3_points_pct: float
    within_5_points_pct: float
    prior_hit_rate_pct: float

class PredictiveEvaluator:
    """Simulates a walk-forward evaluation using true possession-weighted stint aggregations."""

    def __init__(self, priors_path: Path, db_uri: str, config: Optional[EvaluationConfig] = None) -> None:
        if not priors_path.exists():
            raise FileNotFoundError(f"Priors file not found at {priors_path}")

        logger.info(f"Loading Bayesian priors from {priors_path}")
        raw_priors: List[Dict] = joblib.load(priors_path)

        self.priors_map: Dict[str, float] = {
            canonical_lineup_key(item["lineup_player_ids"]): float(item["shrinkage_posterior_net_rating"])
            for item in raw_priors
        }
        self.default_prior: float = (
            float(np.mean(list(self.priors_map.values()))) if self.priors_map else 0.0
        )

        self.db_engine: Engine = create_engine(db_uri)
        self.config: EvaluationConfig = config or EvaluationConfig()

    def _lookup_prior(self, key: str) -> tuple[float, bool]:
        if key in self.priors_map:
            return self.priors_map[key], True
        return self.default_prior, False

    def load_stint_level_game_logs(self, test_season: str) -> pd.DataFrame:
        """
        Extracts all verified home-perspective stints to reconstruct full game margins.
        """
        query = """
            SELECT
                game_id,
                lineup_player_ids AS home_lineup,
                opp_lineup_player_ids AS away_lineup,
                possessions,
                points_scored,
                points_allowed
            FROM pbp_stints
            WHERE season = %(season)s
              AND stint_id LIKE '%%_h'
        """
        logger.info(f"Ingesting stint-level logs for {test_season} to map exact Constrained Resource Allocation...")
        return pd.read_sql(query, self.db_engine, params={"season": test_season})

    def run_evaluation(self, test_season: str) -> EvaluationReport:
        stints_df = self.load_stint_level_game_logs(test_season)
        if stints_df.empty:
            raise ValueError(f"No hold-out stints found for {test_season}")

        projected_margin_list: List[float] = []
        actual_margin_list: List[float] = []
        prior_hits = 0
        prior_lookups = 0

        # Group by game to aggregate exact expected margins across all rotational shifts
        grouped_games = stints_df.groupby("game_id")
        logger.info(f"Running mathematical evaluation across {len(grouped_games)} reconstructed games...")

        for game_id, game_stints in grouped_games:
            game_proj_margin = 0.0
            game_actual_margin = 0.0
            total_game_possessions = 0.0

            for _, row in game_stints.iterrows():
                home_key = canonical_lineup_key(row["home_lineup"])
                away_key = canonical_lineup_key(row["away_lineup"])

                home_prior, home_hit = self._lookup_prior(home_key)
                away_prior, away_hit = self._lookup_prior(away_key)
                prior_lookups += 2
                prior_hits += int(home_hit) + int(away_hit)

                stint_poss = float(row["possessions"])

                # Expected margin for THIS SPECIFIC STINT
                expected_stint_margin = (home_prior - away_prior) * (stint_poss / 100.0)

                game_proj_margin += expected_stint_margin
                game_actual_margin += float(row["points_scored"] - row["points_allowed"])
                total_game_possessions += stint_poss

            # Apply Home Court Advantage across the total aggregated pace of the game
            hca_points = self.config.home_court_advantage * (total_game_possessions / 100.0)
            game_proj_margin += hca_points

            projected_margin_list.append(game_proj_margin)
            actual_margin_list.append(game_actual_margin)

        # Vectorized error calculations
        proj_arr = np.array(projected_margin_list)
        actual_arr = np.array(actual_margin_list)
        errors = np.abs(proj_arr - actual_arr)

        rmse = float(np.sqrt(np.mean(errors ** 2)))
        mae = float(np.mean(errors))

        within_3 = float(np.mean(errors <= 3.0)) * 100
        within_5 = float(np.mean(errors <= 5.0)) * 100
        hit_rate = (prior_hits / prior_lookups * 100.0) if prior_lookups else 0.0

        return EvaluationReport(
            total_games_evaluated=len(grouped_games),
            mean_absolute_error=round(mae, 2),
            root_mean_square_error=round(rmse, 2),
            within_3_points_pct=round(within_3, 2),
            within_5_points_pct=round(within_5, 2),
            prior_hit_rate_pct=round(hit_rate, 2),
        )

if __name__ == "__main__":
    PRIORS_FILE = Path("models/weights/bayesian_shrinkage_priors.joblib")
    HOLDOUT_SEASON = "2025-26"

    if not DB_URL:
        raise RuntimeError("DATABASE_URL is not set in environment.")

    evaluator = PredictiveEvaluator(priors_path=PRIORS_FILE, db_uri=DB_URL)
    logger.info(
        "Loaded %d lineup priors (default_prior=%.3f). Running predictive evaluation.",
        len(evaluator.priors_map),
        evaluator.default_prior,
    )

    report = evaluator.run_evaluation(test_season=HOLDOUT_SEASON)

    print("\n" + "=" * 50)
    print("      PREDICTIVE ACCURACY REPORT      ")
    print("=" * 50)
    print(f"Games Analyzed:             {report.total_games_evaluated}")
    print(f"Mean Absolute Error (MAE):  {report.mean_absolute_error} points")
    print(f"Root Mean Square (RMSE):    {report.root_mean_square_error} points")
    print(f"Accuracy (Within 3 pts):    {report.within_3_points_pct}%")
    print(f"Accuracy (Within 5 pts):    {report.within_5_points_pct}%")
    print(f"Prior Hit Rate:             {report.prior_hit_rate_pct}%")
    print("=" * 50 + "\n")
