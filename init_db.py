import logging
from config.database import engine, Base
from src.models.events import PlayByPlayEvent

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def initialize_cloud_schema():
    logging.info("Connecting to Cloud PostgreSQL instance...")
    Base.metadata.create_all(bind=engine)
    logging.info("Successfully deployed relational schema to database!")

if __name__ == "__main__":
    initialize_cloud_schema()