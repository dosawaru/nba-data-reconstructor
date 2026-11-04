import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from src.models.feature_extractor import StintFeatureExtractor

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TARGET_SEASON = "2025-26"
OUTPUT_PATH = Path("data/processed/season_2025_2026_reconstructed_states.csv")


def main() -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")

    extractor = StintFeatureExtractor(db_url=db_url)
    path = extractor.export_reconstructed_states(TARGET_SEASON, OUTPUT_PATH)
    logger.info(f"Done: {path}")


if __name__ == "__main__":
    main()
