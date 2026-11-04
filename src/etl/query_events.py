import logging
from typing import List, Dict, Any

from sqlalchemy.exc import OperationalError

from config.database import SessionLocal, engine
from src.models.events import PlayByPlayEvent

# logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class PBPEventQuery:
    """
    Queries the raw chronology of play-by-play events from the database for
    deterministic state reconstruction
    """

    def fetch_events(self, game_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all event records from a given game_id, and
        sorting by period and clock time
        """
        last_error: Exception | None = None
        for attempt in range(2):
            db = SessionLocal()
            try:
                logging.info(f"Fetching events for game {game_id}")
                records = (
                    db.query(PlayByPlayEvent)
                    .filter(PlayByPlayEvent.game_id == game_id)
                    .order_by(PlayByPlayEvent.period.asc(), PlayByPlayEvent.eventnum.asc())
                    .all()
                )

                if not records:
                    logging.warning(f"No events found for game {game_id}")
                    return []

                events = [
                    {
                        "event_id": r.event_id,
                        "game_id": r.game_id,
                        "eventnum": r.eventnum,
                        "eventmsgtype": r.eventmsgtype,
                        "eventmsgactiontype": r.eventmsgactiontype,
                        "period": r.period,
                        "pctimestring": r.pctimestring,
                        "homedescription": r.homedescription,
                        "neutraldescription": r.neutraldescription,
                        "visitordescription": r.visitordescription,
                        "score": r.score,
                        "scoremargin": r.scoremargin,
                        "player1_id": r.player1_id,
                        "player2_id": r.player2_id,
                        "player3_id": r.player3_id,
                    }
                    for r in records
                ]

                logging.info(f"Successfully fetched {len(events)} events for game {game_id}")
                return events
            except OperationalError as e:
                last_error = e
                logging.warning(f"Neon/DB connection dropped for {game_id}; disposing pool and retrying")
                engine.dispose()
            except Exception as e:
                logging.error(f"Error fetching events for game {game_id}: {e}")
                raise
            finally:
                db.close()

        raise last_error  # type: ignore[misc]


if __name__ == "__main__":
    query = PBPEventQuery()
    test_game_id = "0022400002"
    print(f"Fetching events for game {test_game_id}")
    events = query.fetch_events(test_game_id)
    print(f"Fetched {len(events)} events")
    print(events[:5])
