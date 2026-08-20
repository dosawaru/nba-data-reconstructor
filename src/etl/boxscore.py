import logging
import time 
import random
from typing import List, Dict, Tuple
from nba_api.stats.endpoints import boxscoretraditionalv3
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

if __name__ == "__main__":
    ingestor = BoxscoreIngestor()
    home_starters, away_starters = ingestor.get_starting_lineups("0022400002")
    print(f"Home starters: {home_starters}")
    print(f"Away starters: {away_starters}")