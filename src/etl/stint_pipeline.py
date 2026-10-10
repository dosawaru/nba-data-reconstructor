import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from config.database import SessionLocal
from src.etl.boxscore import BoxscoreIngestor
from src.etl.query_events import PBPEventQuery
from src.etl.season import game_id_to_season
from src.etl.stint_transform import game_stint_to_team_rows
from src.models.events import PlayByPlayEvent
from src.models.stints import PbpStint
from src.parser.state_reconstructor import DeterministicStateReconstructor
from src.parser.stint_aggregator import StintAggregator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class NBAStintPipeline:
    """
    Build team-centric stint rows from ingested play-by-play and load into pbp_stints.
    """

    def __init__(self) -> None:
        self.event_query = PBPEventQuery()
        self.boxscore = BoxscoreIngestor()
        self.aggregator = StintAggregator()

    def list_game_ids(self, season: Optional[str] = None) -> List[str]:
        db: Session = SessionLocal()
        try:
            rows = db.query(PlayByPlayEvent.game_id).distinct().order_by(PlayByPlayEvent.game_id).all()
            game_ids = [str(r[0]) for r in rows]
            if season is None:
                return game_ids
            return [gid for gid in game_ids if game_id_to_season(gid) == season]
        finally:
            db.close()

    def process_game(self, game_id: str) -> int:
        game_id = str(game_id)
        raw_events = self.event_query.fetch_events(game_id)
        if not raw_events:
            logging.warning(f"Skipping {game_id}: no events in database")
            return 0

        home_starters, away_starters = self.boxscore.get_starting_lineups(game_id)
        game_info = self.boxscore.get_game_info(game_id)
        home_team_id = int(game_info["home_team_id"])
        away_team_id = int(game_info["away_team_id"])
        season = game_id_to_season(game_id)

        reconstructor = DeterministicStateReconstructor(
            home_starters=home_starters,
            away_starters=away_starters,
        )
        annotated = reconstructor.process_events(raw_events)
        game_stints = self.aggregator.aggregate_stints(annotated)

        team_rows: List[dict] = []
        for stint in game_stints:
            team_rows.extend(
                game_stint_to_team_rows(
                    stint,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    season=season,
                )
            )

        db: Session = SessionLocal()
        try:
            deleted = (
                db.query(PbpStint)
                .filter(PbpStint.game_id == game_id)
                .delete(synchronize_session=False)
            )
            if deleted:
                logging.info(f"Removed {deleted} existing stint rows for game {game_id}")

            db.bulk_save_objects([PbpStint(**row) for row in team_rows])
            db.commit()
            logging.info(f"Loaded {len(team_rows)} stint rows for game {game_id} ({season})")
            return len(team_rows)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def process_season(self, season: str) -> int:
        game_ids = self.list_game_ids(season=season)
        if not game_ids:
            logging.warning(f"No games in database for season {season}")
            return 0

        total = 0
        for game_id in game_ids:
            total += self.process_game(game_id)
        logging.info(f"Season {season}: wrote {total} stint rows across {len(game_ids)} games")
        return total


if __name__ == "__main__":
    pipeline = NBAStintPipeline()
    pipeline.process_season("2024-25")
