"""
Print per-game projected vs actual margins with team/date metadata
and player names on each stint.
"""

import ast
import logging
import os
from pathlib import Path
from typing import List, Optional

import pandas as pd
from dotenv import load_dotenv

from src.etl.boxscore import BoxscoreIngestor
from src.etl.playername import PlayerNameResolver
from src.models.backtest import PredictiveEvaluator
from src.models.lineup_keys import canonical_lineup_key as _lineup_key

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _as_id_list(ids) -> List[int]:
    if isinstance(ids, list):
        return [int(x) for x in ids]
    if isinstance(ids, str):
        try:
            parsed = ast.literal_eval(ids)
            if isinstance(parsed, (list, tuple)):
                return [int(x) for x in parsed]
        except (ValueError, SyntaxError):
            pass
        cleaned = ids.strip().strip("[]")
        return [int(x.strip()) for x in cleaned.split(",") if x.strip()]
    return [int(x) for x in ids]


def _format_lineup(resolver: PlayerNameResolver, ids) -> str:
    names = resolver.resolve_lineup(_as_id_list(ids))
    # Drop trailing " (id)" for readability in the ledger
    short = [n.rsplit(" (", 1)[0] for n in names]
    return ", ".join(short)


def _load_home_stints(
    evaluator: PredictiveEvaluator,
    season: str,
    game_id: Optional[str] = None,
) -> pd.DataFrame:
    query = """
        SELECT
            game_id,
            stint_id,
            lineup_player_ids AS home_lineup,
            opp_lineup_player_ids AS away_lineup,
            possessions,
            points_scored,
            points_allowed
        FROM pbp_stints
        WHERE season = %(season)s
          AND stint_id LIKE '%%_h'
    """
    params = {"season": season}
    if game_id:
        query += " AND game_id = %(game_id)s"
        params["game_id"] = game_id
    query += " ORDER BY game_id, stint_id"
    return pd.read_sql(query, evaluator.db_engine, params=params)


def print_season_summary(evaluator: PredictiveEvaluator, season: str) -> List[str]:
    """Print one row per game; return ordered game_ids."""
    df = _load_home_stints(evaluator, season)
    if df.empty:
        print(f"No stints found for season {season}")
        return []

    box = BoxscoreIngestor()
    game_ids = sorted(df["game_id"].astype(str).unique())
    print("\n" + "=" * 100)
    print(f" GAME RESULTS SUMMARY - {season}  ({len(game_ids)} games)")
    print("=" * 100)
    print(
        f"{'Game ID':<12} {'Date':<12} {'Matchup':<42} "
        f"{'Proj':>7} {'Actual':>7} {'Err':>6}"
    )
    print("-" * 100)

    for game_id in game_ids:
        game_df = df[df["game_id"].astype(str) == game_id]
        proj = 0.0
        actual = 0.0
        poss_total = 0.0
        for _, row in game_df.iterrows():
            home_prior = evaluator.priors_map.get(_lineup_key(row["home_lineup"]), 0.0)
            away_prior = evaluator.priors_map.get(_lineup_key(row["away_lineup"]), 0.0)
            poss = float(row["possessions"])
            proj += (home_prior - away_prior) * (poss / 100.0)
            actual += float(row["points_scored"] - row["points_allowed"])
            poss_total += poss
        proj += evaluator.config.home_court_advantage * (poss_total / 100.0)

        try:
            info = box.get_game_info(game_id)
            date = info["game_date"]
            matchup = f"{info['away_team']} @ {info['home_team']}"
        except Exception as e:
            logger.warning(f"Could not fetch game info for {game_id}: {e}")
            date, matchup = "?", "?"

        err = abs(proj - actual)
        print(
            f"{game_id:<12} {date:<12} {matchup:<42} "
            f"{proj:>+7.1f} {actual:>+7.1f} {err:>6.1f}"
        )

    print("=" * 100 + "\n")
    return game_ids


def inspect_single_game(
    evaluator: PredictiveEvaluator,
    season: str,
    target_game_id: Optional[str] = None,
) -> None:
    df = _load_home_stints(evaluator, season, game_id=target_game_id)
    if df.empty:
        print(f"No stints found for season {season} (Game ID: {target_game_id})")
        return

    if not target_game_id:
        target_game_id = str(df["game_id"].iloc[0])
        df = df[df["game_id"].astype(str) == target_game_id]

    resolver = PlayerNameResolver()
    box = BoxscoreIngestor()
    try:
        info = box.get_game_info(target_game_id)
        header = (
            f"{info['away_team']} @ {info['home_team']}  |  {info['game_date']}  |  "
            f"game_id={target_game_id}"
        )
    except Exception as e:
        logger.warning(f"Could not fetch game info for {target_game_id}: {e}")
        header = f"game_id={target_game_id}"

    print("\n" + "=" * 110)
    print(f" DIAGNOSTIC TRACE: {header}")
    print("=" * 110)

    game_proj_margin = 0.0
    game_actual_margin = 0.0
    total_possessions = 0.0

    for _, row in df.iterrows():
        home_ids = row["home_lineup"]
        away_ids = row["away_lineup"]
        home_key = _lineup_key(home_ids)
        away_key = _lineup_key(away_ids)
        home_prior = evaluator.priors_map.get(home_key, 0.0)
        away_prior = evaluator.priors_map.get(away_key, 0.0)
        poss = float(row["possessions"])
        expected_margin = (home_prior - away_prior) * (poss / 100.0)
        actual_margin = float(row["points_scored"] - row["points_allowed"])

        print(f"\nStint {row['stint_id']}  |  poss={poss:.1f}  |  "
              f"home_prior={home_prior:+.1f}  away_prior={away_prior:+.1f}  |  "
              f"proj={expected_margin:+.2f}  actual={actual_margin:+.1f}")
        print(f"  HOME: {_format_lineup(resolver, home_ids)}")
        print(f"  AWAY: {_format_lineup(resolver, away_ids)}")

        game_proj_margin += expected_margin
        game_actual_margin += actual_margin
        total_possessions += poss

    hca_points = evaluator.config.home_court_advantage * (total_possessions / 100.0)
    final_proj_margin = game_proj_margin + hca_points
    absolute_error = abs(final_proj_margin - game_actual_margin)

    print("\n" + "-" * 110)
    print(f"Raw projected margin:              {game_proj_margin:+.2f}")
    print(f"Home court advantage (+2.45/100):  {hca_points:+.2f}")
    print(f"FINAL PROJECTED MARGIN:            {final_proj_margin:+.2f}")
    print(f"ACTUAL FINAL MARGIN:               {game_actual_margin:+.2f}")
    print(f"ABSOLUTE ERROR:                    {absolute_error:.2f}")
    print("=" * 110 + "\n")


if __name__ == "__main__":
    PRIORS_FILE = Path("models/weights/bayesian_shrinkage_priors.joblib")
    SEASON = "2025-26"
    # Set to a specific game_id (e.g. "0022500001") or None to detail the first game
    TARGET_GAME_ID: Optional[str] = None

    if not DB_URL:
        raise RuntimeError("DATABASE_URL is not set.")

    evaluator = PredictiveEvaluator(priors_path=PRIORS_FILE, db_uri=DB_URL)
    game_ids = print_season_summary(evaluator, SEASON)
    if game_ids:
        inspect_single_game(
            evaluator,
            season=SEASON,
            target_game_id=TARGET_GAME_ID or game_ids[0],
        )
