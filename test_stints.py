import logging
from src.etl.query_events import PBPEventQuery
from src.etl.boxscore import BoxscoreIngestor
from src.etl.playername import PlayerNameResolver
from src.parser.state_reconstructor import DeterministicStateReconstructor
from src.parser.stint_aggregator import StintAggregator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def test_stint_generation():
    game_id = "0022400321"

    # 1. Fetch Starters & Event Stream
    boxscore = BoxscoreIngestor()
    resolver = PlayerNameResolver()
    game_info = boxscore.get_game_info(game_id)
    home_starters, away_starters = boxscore.get_starting_lineups(game_id)

    query = PBPEventQuery()
    raw_events = query.fetch_events(game_id)

    # 2. Execute Deterministic State Reconstruction
    reconstructor = DeterministicStateReconstructor(
        home_starters=home_starters,
        away_starters=away_starters,
    )
    annotated_events = reconstructor.process_events(raw_events)

    # 3. Aggregate Stints
    aggregator = StintAggregator()
    stints = aggregator.aggregate_stints(annotated_events)

    print(f"\n==================== STINT AGGREGATION SUMMARY ====================")
    print(f"Game: {game_info['away_team']} @ {game_info['home_team']} | Date: {game_info['game_date']} | ID: {game_id}")
    print(f"Total Discrete Stints Derived: {len(stints)}")
    
    # Display the first 3 stints
    for idx, s in enumerate(stints[:3]):
        home_names = resolver.resolve_lineup(s["home_lineup"])
        away_names = resolver.resolve_lineup(s["away_lineup"])
        print(f"\n--- Stint {idx + 1} [ID: {s['stint_id']}] ---")
        print(f"  Period: {s['period']} | Clock: {s['start_clock']} -> {s['end_clock']} ({s['duration']}s)")
        print(f"  Home Possessions: {s['home_possessions']} | Away Possessions: {s['away_possessions']}")
        print(f"  Home Score / Box: {s['home_pts']} PTS ({s['home_fgm']}/{s['home_fga']} FG, {s['home_tov']} TOV)")
        print(f"  Away Score / Box: {s['away_pts']} PTS ({s['away_fgm']}/{s['away_fga']} FG, {s['away_tov']} TOV)")
        print(f"  Home Lineup: {', '.join(home_names)}")
        print(f"  Away Lineup: {', '.join(away_names)}")
    print(f"===================================================================\n")


if __name__ == "__main__":
    test_stint_generation()