import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, List

import joblib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.models.lineup_keys import canonical_lineup_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# store bayesian prior for lookup
model_state: Dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    priors_path = Path("models/weights/bayesian_shrinkage_priors.joblib")

    if priors_path.exists():
        logger.info(f"Loading Bayesian shrinkage priors from {priors_path}")
        raw_priors = joblib.load(priors_path)

        for record in raw_priors:
            key = canonical_lineup_key(record["lineup_player_ids"])
            model_state[key] = record

        logger.info(f"Loaded {len(model_state)} Bayesian shrinkage priors")
    else:
        logger.warning(f"Bayesian shrinkage priors not found at {priors_path}")

    yield

    logger.info("Shutting down Bayesian shrinkage priors")
    model_state.clear()

app = FastAPI(lifespan=lifespan)

class LineupRequest(BaseModel):
    player_ids: List[str] = Field(
        ...,
        min_items=5,
        max_items=5,
        description="List of 5 player IDs in the starting lineup"
    )

class LineupResponse(BaseModel):
    lineup_id: str
    total_possessions: float
    shrinkage_factor_b: float
    posterior_net_rating: float
    posterior_std_error: float

@app.post("/api/v1/predict-lineup", response_model=LineupResponse)
async def predict_lineup(request: LineupRequest):
    """
    normalizes the lineup topology and returns the regularized margin
    """
    normalized_key = canonical_lineup_key(request.player_ids)

    record = model_state.get(normalized_key)

    if not record:
        logger.warning(f"Lineup topology {normalized_key} not found in historical priors.")
        raise HTTPException(
            status_code=404,
            detail="Lineup topology not found in historical priors. Unable to execute shrinkage."
        )

    return LineupResponse(
        lineup_id=normalized_key,
        total_possessions=record["total_possessions"],
        shrinkage_factor_b=record["shrinkage_factor_b"],
        posterior_net_rating=record["shrinkage_posterior_net_rating"],
        posterior_std_error=record["shrinkage_posterior_std_error"]
    )
