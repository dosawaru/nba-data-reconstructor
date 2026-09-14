import logging
from sqlalchemy import text
from config.database import engine, Base
from src.models.events import PlayByPlayEvent

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DEDUP_SQL = """
DELETE FROM play_by_play_events a
USING play_by_play_events b
WHERE a.event_id > b.event_id
  AND a.game_id = b.game_id
  AND a.eventnum = b.eventnum
"""

UNIQUE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_play_by_play_game_eventnum
ON play_by_play_events (game_id, eventnum)
"""


def dedupe_and_constrain_events() -> None:
    """Drop duplicate (game_id, eventnum) rows, then enforce uniqueness."""
    with engine.begin() as conn:
        result = conn.execute(text(DEDUP_SQL))
        deleted = result.rowcount if result.rowcount is not None else 0
        logging.info(f"Removed {deleted} duplicate play-by-play rows")
        conn.execute(text(UNIQUE_INDEX_SQL))
        logging.info("Ensured unique index on (game_id, eventnum)")


def initialize_cloud_schema():
    logging.info("Connecting to Cloud PostgreSQL instance...")
    Base.metadata.create_all(bind=engine)
    dedupe_and_constrain_events()
    logging.info("Successfully deployed relational schema to database!")

if __name__ == "__main__":
    initialize_cloud_schema()
