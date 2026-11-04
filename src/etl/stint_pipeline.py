import logging
import time
from pathlib import Path
from typing import List, Optional

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from config.database import SessionLocal, engine
from src.etl.boxscore import BoxscoreIngestor
from src.etl.query_events import PBPEventQuery
from src.etl.season import game_id_to_season
from src.etl.stint_transform import game_stint_to_team_rows
from src.models.events import PlayByPlayEvent
from src.models.stints import PbpStint
from src.parser.state_reconstructor import DeterministicStateReconstructor
from src.parser.stint_aggregator import StintAggregator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Resume after last successfully stinted game (currently through 602).
RESUME_FROM = 603
SLEEP_BETWEEN_GAMES_SEC = 4.0
MISSED_GAMES_PATH = Path("data/processed/missed_stint_games.txt")


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

        last_error: Exception | None = None
        for attempt in range(2):
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
            except OperationalError as e:
                last_error = e
                logging.warning(f"Neon write failed for {game_id}; disposing pool and retrying")
                db.rollback()
                engine.dispose()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        raise last_error  # type: ignore[misc]

    def process_season(self, season: str, resume_from: int = RESUME_FROM) -> int:
        game_ids = self.list_game_ids(season=season)
        if not game_ids:
            logging.warning(f"No games in database for season {season}")
            return 0

        if resume_from > 1:
            game_ids = [gid for gid in game_ids if int(gid[-5:]) >= resume_from]
            logging.info(f"Resuming from game #{resume_from}: {len(game_ids)} games remaining")

        total = 0
        missed: List[str] = []
        for game_id in game_ids:
            try:
                total += self.process_game(game_id)
            except Exception as e:
                logging.warning(f"Skipping {game_id}: {e}")
                missed.append(game_id)
            time.sleep(SLEEP_BETWEEN_GAMES_SEC)

        if missed:
            MISSED_GAMES_PATH.parent.mkdir(parents=True, exist_ok=True)
            with MISSED_GAMES_PATH.open("a", encoding="utf-8") as f:
                for gid in missed:
                    f.write(f"{gid}\n")
            logging.warning(
                f"Missed {len(missed)} games (appended to {MISSED_GAMES_PATH}): {missed}"
            )

        logging.info(
            f"Season {season}: wrote {total} stint rows across "
            f"{len(game_ids) - len(missed)}/{len(game_ids)} games "
            f"({len(missed)} missed)"
        )
        return total


if __name__ == "__main__":
    pipeline = NBAStintPipeline()
    pipeline.process_season("2025-26")
