import json
import logging
import time
import random
from pathlib import Path
from typing import List, Dict, Tuple, Any

from nba_api.stats.endpoints import boxscoretraditionalv3, boxscoresummaryv2
from nba_api.stats.static import teams
from requests.exceptions import ReadTimeout, ConnectionError, ChunkedEncodingError

# logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

CACHE_DIR = Path("data/cache/boxscore")
RETRYABLE = (ReadTimeout, ConnectionError, ChunkedEncodingError, ValueError, OSError)


class BoxscoreIngestor:
    """
    Extract boxscore from game_id and initial state (starting lineup).
    Successful responses are cached under data/cache/boxscore/ to avoid
    re-hitting stats.nba.com on reruns.
    """

    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, kind: str, game_id: str) -> Path:
        return self.cache_dir / f"{kind}_{game_id}.json"

    def _load_cache(self, kind: str, game_id: str) -> Any | None:
        path = self._cache_path(kind, game_id)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            logging.info(f"Cache hit ({kind}) for game {game_id}")
            return data
        except Exception as e:
            logging.warning(f"Bad cache for {kind}/{game_id}: {e}")
            return None

    def _save_cache(self, kind: str, game_id: str, data: Any) -> None:
        path = self._cache_path(kind, game_id)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f)

    def get_starting_lineups(self, game_id: str, max_retries: int = 3) -> Tuple[List[int], List[int]]:
        cached = self._load_cache("lineups", game_id)
        if cached is not None:
            return list(cached["home"]), list(cached["away"])

        retries = 0
        while retries < max_retries:
            logging.info(f"Fetching starting lineup for game {game_id}")
            try:
                box = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id, timeout=60)
                data = box.get_dict()

                boxscore_data = data.get("boxScoreTraditional", {})
                home_team = boxscore_data.get("homeTeam", {})
                away_team = boxscore_data.get("awayTeam", {})

                home_starters = [
                    int(player.get("personId"))
                    for player in home_team.get("players", [])
                    if player.get("position") and player.get("position").strip() != ""
                ]
                away_starters = [
                    int(player.get("personId"))
                    for player in away_team.get("players", [])
                    if player.get("position") and player.get("position").strip() != ""
                ]

                self._save_cache("lineups", game_id, {"home": home_starters, "away": away_starters})
                return home_starters, away_starters
            except RETRYABLE as e:
                wait_time = (3 ** retries) + random.uniform(2.0, 5.0)
                logging.error(f"Error fetching starting lineup for game {game_id}: {e}")
                logging.info(f"Backing off {wait_time:.1f}s before retry {retries + 1}/{max_retries}")
                time.sleep(wait_time)
                retries += 1
            except Exception as e:
                logging.error(f"Unexpected error fetching starting lineup for game {game_id}: {e}")
                raise
        raise RuntimeError(f"Failed to fetch starting lineup for game {game_id} after {max_retries} retries")

    def get_game_info(self, game_id: str, max_retries: int = 3) -> Dict:
        cached = self._load_cache("info", game_id)
        if cached is not None:
            return cached

        retries = 0
        while retries < max_retries:
            logging.info(f"Fetching game info for game {game_id}")
            try:
                summary = boxscoresummaryv2.BoxScoreSummaryV2(game_id=game_id, timeout=60)
                game = summary.game_summary.get_data_frame().iloc[0]
                home_id = int(game["HOME_TEAM_ID"])
                away_id = int(game["VISITOR_TEAM_ID"])
                raw_date = str(game["GAME_DATE_EST"])
                game_date = raw_date.split("T")[0] if "T" in raw_date else raw_date[:10]

                home = teams.find_team_name_by_id(home_id) or {}
                away = teams.find_team_name_by_id(away_id) or {}

                info = {
                    "game_date": game_date,
                    "home_team": home.get("full_name", str(home_id)),
                    "away_team": away.get("full_name", str(away_id)),
                    "home_team_id": home_id,
                    "away_team_id": away_id,
                }
                self._save_cache("info", game_id, info)
                return info
            except RETRYABLE as e:
                wait_time = (3 ** retries) + random.uniform(2.0, 5.0)
                logging.error(f"Error fetching game info for game {game_id}: {e}")
                logging.info(f"Backing off {wait_time:.1f}s before retry {retries + 1}/{max_retries}")
                time.sleep(wait_time)
                retries += 1
            except Exception as e:
                logging.error(f"Unexpected error fetching game info for game {game_id}: {e}")
                raise
        raise RuntimeError(f"Failed to fetch game info for game {game_id} after {max_retries} retries")


if __name__ == "__main__":
    ingestor = BoxscoreIngestor()
    home_starters, away_starters = ingestor.get_starting_lineups("0022400002")
    print(f"Home starters: {home_starters}")
    print(f"Away starters: {away_starters}")
