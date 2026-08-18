import logging
from math import exp
from sqlalchemy.orm import Session
from src.etl.ingestor import NBAPlayByPlayIngestor
from src.parser.parser import NBAPlayByPlayParser
from src.models.events import PlayByPlayEvent
from config.database import SessionLocal

# logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class NBAPlayByPlayPipeline:
    """
    ETL pipeline for the play-by-play events. Extracts data from the NBA API, 
    transforms it into a structured format, and loads it into the database
    """

    def __init__(self):
        self.ingestor = NBAPlayByPlayIngestor()
        self.parser = NBAPlayByPlayParser()

    def process_game(self, game_id: str):
        """
        Processes a single game by ingesting the data, parsing it, and loading it into the database
        """

        db: Session = SessionLocal()
        try: 
            # extract 
            logging.info(f"Processing game {game_id}")
            raw_payload = self.ingestor.fetch_game_events(game_id)

            # transform the data
            parsed_events = self.parser.parse_play_by_play(raw_payload, game_id)

            if not parsed_events:
                logging.error(f"No events parsed for game {game_id}")
                return
            
            # load the data into the database
            event_objects = [PlayByPlayEvent(**event) for event in parsed_events]

            db.bulk_save_objects(event_objects)
            db.commit()

            logging.info(f"Successfully processed and loaded {len(parsed_events)} events for game {game_id}")
        
        except Exception as e:
            # rollback the transaction if an error occurs
            db.rollback()
            logging.error(f"Error processing game {game_id}: {e}")
            raise
        finally:
            # close the database session
            db.close()

if __name__ == "__main__":
    orchestrator = NBAPlayByPlayPipeline()
    orchestrator.process_game("0022400001") # Test execution on the 2024-2025 season opener
