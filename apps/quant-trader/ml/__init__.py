"""Machine Learning strategy module for quant-trader.

Provides feature engineering, model training, and prediction pipelines
for ML-based trading strategies. Uses sklearn/xgboost only (no deep
learning frameworks required).

Usage in config.yaml::

    strategy:
      name: ml
      model_path: models/          # where trained models are saved
      threshold: 0.6               # confidence threshold for BUY/SELL
"""

from .features import FeatureEngineer
from .models import ModelEnsemble
from .predictor import MLPredictor
from .trainer import MLTrainer
