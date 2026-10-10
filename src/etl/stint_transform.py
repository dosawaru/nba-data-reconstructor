from typing import Any, Dict, List, Optional

from src.etl.season import game_id_to_season


def game_stint_to_team_rows(
    stint: Dict[str, Any],
    home_team_id: int,
    away_team_id: int,
    season: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Expand one game-centric stint record into home and away team-centric rows."""
    game_id = str(stint["game_id"]).zfill(10)
    resolved_season = season or game_id_to_season(game_id)
    base_id = str(stint["stint_id"])
    duration = float(stint["duration"])

    home_row = {
        "stint_id": f"{base_id}_h",
        "game_id": game_id,
        "season": resolved_season,
        "team_id": home_team_id,
        "opp_team_id": away_team_id,
        "lineup_player_ids": list(stint["home_lineup"]),
        "opp_lineup_player_ids": list(stint["away_lineup"]),
        "duration_seconds": duration,
        "possessions": float(stint["home_possessions"]),
        "points_scored": int(stint["home_pts"]),
        "points_allowed": int(stint["away_pts"]),
        "garbage_time_flag": False,
    }
    away_row = {
        "stint_id": f"{base_id}_a",
        "game_id": game_id,
        "season": resolved_season,
        "team_id": away_team_id,
        "opp_team_id": home_team_id,
        "lineup_player_ids": list(stint["away_lineup"]),
        "opp_lineup_player_ids": list(stint["home_lineup"]),
        "duration_seconds": duration,
        "possessions": float(stint["away_possessions"]),
        "points_scored": int(stint["away_pts"]),
        "points_allowed": int(stint["home_pts"]),
        "garbage_time_flag": False,
    }
    return [home_row, away_row]
