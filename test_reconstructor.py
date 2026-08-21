import logging
from typing import Dict, List
from nba_api.stats.static import players
from src.etl.query_events import PBPEventQuery
from src.parser.state_reconstructor import DeterministicStateReconstructor
from src.etl.boxscore import BoxscoreIngestor
from src.etl.playername import PlayerNameResolver

# logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def run_reconstructor():
    """
    Run the deterministic state reconstructor with a sample game
    """

    game_id = "0022400002"
    boxscore = BoxscoreIngestor()
    resolver = PlayerNameResolver()
    home_starters, away_starters= boxscore.get_starting_lineups(game_id)

    query = PBPEventQuery()
    events = query.fetch_events(game_id)

    if not events:
        logging.error(f"No events found for game {game_id}")
        return

    reconstructor = DeterministicStateReconstructor(
        home_starters=home_starters,
        away_starters=away_starters,
    )

    annotated_events = reconstructor.process_events(events)
    logging.info(f"Annotated {len(annotated_events)} events")

    # Sample events to print
    sample_indices = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200]
    for idx in sample_indices:
        event = annotated_events[idx]
        home_names = resolver.resolve_lineup(event["home_lineup"])
        away_names = resolver.resolve_lineup(event["away_lineup"])

        print(f"================================================================================")
        print(f"[Event {event['eventnum']} | Period {event['period']} | Clock {event['pctimestring']}] MSG Type: {event['eventmsgtype']}")
        print(f"Home Active Lineup: {', '.join(home_names)}")
        print(f"Away Active Lineup: {', '.join(away_names)}")
    print(f"================================================================================")

if __name__ == "__main__":
    run_reconstructor()

