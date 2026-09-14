import logging
import time 
import random
from typing import List, Dict, Tuple
from nba_api.stats.endpoints import boxscoretraditionalv3, boxscoresummaryv2
from nba_api.stats.static import teams
from requests.exceptions import ReadTimeout, ConnectionError

# logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class BoxscoreIngestor:
    """
    Extract boxscore from game_id and initial state (starting lineup)
    """

    def __init__(self):
        pass

    def get_starting_lineups(self, game_id: str, max_retries: int = 3) -> Tuple[List[int], List[int]]:        
        """
        Get starting lineup for both teams
        """
        retries = 0
        backoff_factor = 2
        while retries < max_retries:
            logging.info(f"Fetching starting lineup for game {game_id})")
            try: 
                box = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id, timeout=30)
                data = box.get_dict()

                boxscore_data = data.get("boxScoreTraditional", {})
                home_team = boxscore_data.get("homeTeam", {})
                away_team = boxscore_data.get("awayTeam", {})

                home_players = home_team.get("players", [])
                away_players = away_team.get("players", [])

                home_starters = [
                    int(player.get("personId")) 
                    for player in home_players 
                    if player.get("position") and player.get("position").strip() != ""
                ]

                away_starters = [
                    int(player.get("personId")) 
                    for player in away_players 
                    if player.get("position") and player.get("position").strip() != ""
                ]

                return home_starters, away_starters
            except (ReadTimeout, ConnectionError, ValueError) as e:
                jitter = random.uniform(0.5, 1.5)
                wait_time = backoff_factor ** retries + jitter
                logging.error(f"Error fetching starting lineup for game {game_id}: {e}")
                time.sleep(wait_time)
                retries += 1
            except Exception as e:
                logging.error(f"Unexpected error fetching starting lineup for game {game_id}: {e}")
                raise
        raise RuntimeError(f"Failed to fetch starting lineup for game {game_id} after {max_retries} retries")

    def get_game_info(self, game_id: str, max_retries: int = 3) -> Dict:
        """Return home/away team names and game date for a game_id."""
        retries = 0
        backoff_factor = 2
        while retries < max_retries:
            logging.info(f"Fetching game info for game {game_id}")
            try:
                summary = boxscoresummaryv2.BoxScoreSummaryV2(game_id=game_id, timeout=30)
                game = summary.game_summary.get_data_frame().iloc[0]
                home_id = int(game["HOME_TEAM_ID"])
                away_id = int(game["VISITOR_TEAM_ID"])
                raw_date = str(game["GAME_DATE_EST"])
                game_date = raw_date.split("T")[0] if "T" in raw_date else raw_date[:10]

                home = teams.find_team_name_by_id(home_id) or {}
                away = teams.find_team_name_by_id(away_id) or {}

                return {
                    "game_date": game_date,
                    "home_team": home.get("full_name", str(home_id)),
                    "away_team": away.get("full_name", str(away_id)),
                    "home_team_id": home_id,
                    "away_team_id": away_id,
                }
            except (ReadTimeout, ConnectionError, ValueError) as e:
                jitter = random.uniform(0.5, 1.5)
                wait_time = backoff_factor ** retries + jitter
                logging.error(f"Error fetching game info for game {game_id}: {e}")
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