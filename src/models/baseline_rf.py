import logging
from pathlib import Path
from typing import Tuple, Optional

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BaselineRandomForest:

    def __init__(self, n_estimators: int = 150, max_depth: Optional[int] = 10, random_state: int = 42) -> None:
        self.model = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=random_state,
            n_jobs=-1,
        )
        self.rsme: Optional[float] = None

    def load_features(self, feature_path: Path, season: str) -> Tuple[np.array, np.array]:
        x_path = feature_path / f"x_{season}.joblib"
        y_path = feature_path / f"y_{season}.joblib"

        if not x_path.exists() or not y_path.exists():
            raise FileNotFoundError(f"Feature data not found for season {season}")
        
        logger.info(f"Loading feature data for season {season}")
        X = joblib.load(x_path)
        y = joblib.load(y_path)
        return X, y

    def train_and_evaluate(self, X: np.array, y: np.array, test_size: float = 0.2) -> None:
        """
        Train the model and evaluate its performance
        """

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42)
        logger.info(f"Training model with {len(X_train)} training samples and {len(X_test)} test samples")

        self.model.fit(X_train, y_train)
        predictions = self.model.predict(X_test)

        # calculate RMSE
        self.rsme = np.sqrt(mean_squared_error(y_test, predictions))

        logger.info(f"RMSE: {self.rsme:.3f}")
        return self.rsme

    def export_model(self, output_dir: Path) -> None:
        if self.rsme is None:
            raise RuntimeError("Model has not been trained and evaluated")

        output_dir.mkdir(parents=True, exist_ok=True)
        model_path = output_dir / "baseline_rf_model.joblib"

        joblib.dump(self.model, model_path)
        logger.info(f"Exported model to {model_path}")

if __name__ == "__main__":
    TARGET_SEASON = "2025-26"
    ARTIFACT_DIR = Path("data/processed")
    MODEL_DIR = Path("models/weights")

    regressor = BaselineRandomForest()
    
    # Ingest
    X_raw, y_raw = regressor.load_features(ARTIFACT_DIR, TARGET_SEASON)
    
    # Train & Evaluate
    baseline_rmse = regressor.train_and_evaluate(X_raw, y_raw)
    
    # Export weights
    regressor.export_model(MODEL_DIR)