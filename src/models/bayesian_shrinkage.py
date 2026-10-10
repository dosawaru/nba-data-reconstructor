from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class BayesianHyperparameters:
    lineup_variance: float = 11500.0 # variance of the lineup effect
    prior_tau_variance: float = 225.0 # variance of the prior tau
    min_exposure_threshold: float = 10 # minimum exposure threshold for a player to be considered

class BayesianShrinkage:
    """
    Excecute Bayesian shrinkage on 5-man lineup
    """
    def __init__(self, rf_model_path: Path, hyperparameters: Optional[BayesianHyperparameters] = None) -> None:
        if not rf_model_path.exists():
            raise FileNotFoundError(f"Random forest model not found at {rf_model_path}")

        logger.info(f"Loading random forest model from {rf_model_path}")
        self.rf_model = joblib.load(rf_model_path)
        self.params = hyperparameters or BayesianHyperparameters()

    def estimate_hyperparameters(self, df_lineups: pd.DataFrame) -> Tuple[float, float]:
        """
        Estimate the hyperparameters for the Bayesian shrinkage model
        """

        qualified = df_lineups[df_lineups["total_possessions"] >= 100].copy()
        if len(qualified) < 30:
            logger.warning(f"Insufficient data for hyperparameter estimation. Using default hyperparameters.")
            return self.params.lineup_variance, self.params.prior_tau_variance

        residuals = qualified["net_rating"] - qualified["predicted_net_rating"]
        tau_sq = float(np.var(residuals, ddof=1))

        sigma_sq = self.params.lineup_variance

        logger.info(f"Estimated empirical hyperparameters: sigma^2={sigma_sq:.1f}, tau^2={tau_sq:.1f}")
        return sigma_sq, tau_sq
    
    def regularize_lineups(self, lineup_summary_df: pd.DataFrame, feature_matrix: np.ndarray) -> pd.DataFrame:
        """
        Computes the shrinkage factor B and the posterior net rating for each lineup topology
        """

        required_features = {"lineup_player_ids", "total_possessions", "net_rating"}
        if not required_features.issubset(lineup_summary_df.columns):
            missing = required_features - set(lineup_summary_df.columns)
            raise ValueError(f"Missing required features: {missing}")

        result_df = lineup_summary_df.copy()

        # generate shrinkage factors from Random Forest model
        logger.info(f"Generating non-linear shrinkage factors from Random Forest model")
        result_df["predicted_net_rating"] = self.rf_model.predict(feature_matrix)

        # extract hyperparameters
        sigma_sq, tau_sq = self.estimate_hyperparameters(result_df)

        # calculate shrinkage factor B
        n = result_df["total_possessions"].to_numpy(dtype=np.float64)
        denominator = sigma_sq + (tau_sq * n)
        shrinkage_b = np.where(n < self.params.min_exposure_threshold, 1.0, sigma_sq / denominator)
        result_df["shrinkage_factor_b"] = shrinkage_b

        # calculate posterior net rating
        x_bar = result_df["net_rating"].to_numpy(dtype=np.float64)
        mu_rf = result_df["predicted_net_rating"].to_numpy(dtype=np.float64)
        b = result_df["shrinkage_factor_b"].to_numpy(dtype=np.float64)

        result_df["shrinkage_posterior_net_rating"] = (b * mu_rf) + ((1 - b) * x_bar)

        # posterior standard error
        post_var = 1 / (1 / tau_sq + n / sigma_sq)
        result_df["shrinkage_posterior_std_error"] = np.sqrt(post_var)

        logger.info(f"Regularized {len(result_df)} lineups")
        return result_df

    def export_priors(self, df: pd.DataFrame, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        export_payload = df[[
            "lineup_player_ids",
            "total_possessions",
            "net_rating",
            "predicted_net_rating",
            "shrinkage_factor_b",
            "shrinkage_posterior_net_rating",
            "shrinkage_posterior_std_error",
        ]].to_dict(orient="records")

        joblib.dump(export_payload, output_path)
        logger.info(f"Exported priors to {output_path}")

if __name__ == "__main__":
    RF_MODEL_PATH = Path("models/weights/baseline_rf_model.joblib")
    PRIORS_PATH = Path("models/weights/bayesian_shrinkage_priors.joblib")

    np.random.seed(42)
    sample_size = 5

    mock_lineups = pd.DataFrame({
        "lineup_player_ids": [f"lineup_{i}" for i in range(sample_size)],
        "total_possessions": [5, 45, 120, 500, 1200],
        "net_rating": [+24.0, -18.0, +8.5, +4.2, +3.1]
    })

    mock_features = np.array([
        [112.5, 99.0, 5.2],
        [116.0, 101.5, -3.0],
        [110.0, 96.0, 0.0],
        [114.5, 98.0, 1.5],
        [108.0, 97.2, 0.0]
    ])

    engine = BayesianShrinkage(rf_model_path=RF_MODEL_PATH)
    shrunk_results = engine.regularize_lineups(mock_lineups, mock_features)
    engine.export_priors(shrunk_results, PRIORS_PATH)