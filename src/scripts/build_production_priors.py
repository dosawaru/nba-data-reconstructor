import logging
from pathlib import Path

import numpy as np
import pandas as pd

# Adjust import based on your actual project structure
from src.models.bayesian_shrinkage import BayesianShrinkage

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def main():
    # 1. Define I/O Paths
    # Update this to point to your Phase 2 output (CSV or PostgreSQL connection)
    PHASE_2_DATA_PATH = Path("data/processed/season_2025_2026_reconstructed_states.csv") 
    RF_MODEL_PATH = Path("models/weights/baseline_rf_model.joblib")
    PRODUCTION_PRIORS_PATH = Path("models/weights/bayesian_shrinkage_priors.joblib")

    logger.info("Initializing Offline Batch Execution: Bayesian Regularization")

    # 2. Ingest Deterministic State Reconstruction Data
    if not PHASE_2_DATA_PATH.exists():
        logger.error(f"Phase 2 data not found at {PHASE_2_DATA_PATH}. Ensure ingestion pipeline has run.")
        return

    df_lineups = pd.read_csv(PHASE_2_DATA_PATH)
    logger.info(f"Ingested {len(df_lineups)} unique multi-agent states.")

    # 3. Format the Feature Matrix
    # We must construct the exact feature matrix the Random Forest expects.
    # Update these column names to match your Phase 2 schema.
    # Must match Random Forest training order in feature_extractor.py
    feature_columns = [
        "drtg_opp",
        "pace_factor",
        "delta_usg_on_off",
        "ortg_lineup",
        "net_lineup",
        "is_home",
    ]
    
    # Ensure all required columns exist before matrix operations
    missing_cols = set(feature_columns) - set(df_lineups.columns)
    if missing_cols:
        raise ValueError(f"Missing required environmental constraints in data: {missing_cols}")

    feature_matrix = df_lineups[feature_columns].to_numpy(dtype=np.float64)

    # 4. Execute Bayesian Shrinkage
    engine = BayesianShrinkage(rf_model_path=RF_MODEL_PATH)
    
    logger.info("Applying variance filters and computing posterior distributions...")
    regularized_states = engine.regularize_lineups(
        lineup_summary_df=df_lineups, 
        feature_matrix=feature_matrix
    )

    # 5. Serialize Production Payload
    engine.export_priors(df=regularized_states, output_path=PRODUCTION_PRIORS_PATH)
    logger.info("Offline batch execution complete. Engine ready for Phase 4 deployment.")

if __name__ == "__main__":
    main()