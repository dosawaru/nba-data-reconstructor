import time
import random
import logging
import requests
import requests_cache

# caching protocol for the NBA PHP API to intercept redundant calls and reduce API usage, expire after -1 means never expire
requests_cache.install_cache("nba_php_cache", backend="sqlite", expire_after= -1)

# logging configuration
logging.basicConfig(level= logging.INFO, format= "%(asctime)s - %(levelname)s - %(message)s")

class NBAPlayByPlayIngestor:
    """
    Handles unstructured play-by-play data from stats.nba.com API
    Extracts structured data and stores in a database
    """

    def __init__(self):
        self.base_url = "https://stats.nba.com/stats/playbyplayv2"
        self.headers = {
            "Host": "stats.nba.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "x-nba-stats-origin": "stats",
            "x-nba-stats-token": "true",
            "Connection": "keep-alive",
            "Referer": "https://www.nba.com/",
            "Origin": "https://www.nba.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }


    def fetch_game_events(self, game_id: str, max_retries: int = 5) -> dict:
        """
        Fetches play-by-play events for a given game
        Args:
            game_id: The ID of the game to fetch events for
            max_retries: The maximum number of retries to attempt if the API call fails
        Returns:
            A dictionary containing the play-by-play events
        """
        # parameters for the API call

        params = {
            "EndPeriod": "10",
            "GameID": game_id,
            "StartPeriod": "1",
        }

        retries = 0
        backoff_factor = 2

        session = requests.Session()

        # retry logic to handle API rate limiting
        while retries < max_retries:
            try:
                # Connect timeout: 6s, Read timeout: 30s
                response = session.get(
                    url=self.base_url,
                    headers=self.headers,
                    params=params,
                    timeout=(6, 30)
                )

                # Check if ingested from local SQLite cache
                if getattr(response, 'from_cache', False):
                    logging.info(f"Game {game_id}: Ingested directly from local SQLite cache.")
                    return response.json()

                if response.status_code == 200:
                    logging.info(f"Game {game_id}: Successfully ingested from live API.")
                    return response.json()

                # Rate limiting intercept (429)
                elif response.status_code == 429:
                    jitter = random.uniform(0.5, 1.5)
                    wait_time = (backoff_factor ** retries) + jitter
                    logging.warning(f"Rate limited (429) on {game_id}. Backing off for {wait_time:.2f}s...")
                    time.sleep(wait_time)
                    retries += 1

                else:
                    logging.error(f"Unexpected status code {response.status_code} on game {game_id}.")
                    response.raise_for_status()

            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout) as e:
                jitter = random.uniform(1.0, 2.0)
                wait_time = (backoff_factor ** retries) + jitter
                logging.warning(f"Timeout on {game_id} ({e.__class__.__name__}). Retrying in {wait_time:.2f}s (Attempt {retries + 1}/{max_retries})...")
                time.sleep(wait_time)
                retries += 1

            except requests.exceptions.RequestException as e:
                logging.error(f"Network exception on {game_id}: {e}")
                time.sleep(backoff_factor ** retries)
                retries += 1

        raise Exception(f"Fatal Error: Max retries exceeded for Game ID {game_id}")

if __name__ == "__main__":
    ingestor = NBAPlayByPlayIngestor()
    payload = ingestor.fetch_game_events("0022200001")  # 0022200001 is the opening game of the 2022-2023 NBA Season
    result_sets = payload.get("resultSets", [])
    if result_sets:
        row_count = len(result_sets[0].get("rowSet", []))
        print(f"Ingestion verified! Retrieved {row_count} raw play-by-play events.")
