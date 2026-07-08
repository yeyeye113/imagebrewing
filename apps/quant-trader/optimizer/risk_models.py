"""Risk models — 协方差矩阵估计.

提供多种协方差估计方法，均返回 (n, n) numpy 数组。
所有函数接受 pd.DataFrame (columns=symbols, rows=dates, values=returns)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Sample covariance
# ---------------------------------------------------------------------------


def sample_covariance(returns: pd.DataFrame, periods_per_year: int = 252) -> np.ndarray:
    """Annualized sample covariance matrix.  Simple but noisy for large n."""
    return np.asarray(returns.cov().values) * periods_per_year


# ---------------------------------------------------------------------------
# Ledoit-Wolf shrinkage
# ---------------------------------------------------------------------------


def _ledoit_wolf_shrinkage(
    X: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf shrinkage estimator on centered return matrix.

    X: (T, n) matrix of *demeaned* returns.
    Returns (shrunk_cov, shrinkage_intensity).

    Reference: Ledoit & Wolf (2004) "Honey, I Shrunk the Sample Covariance Matrix".
    """
    T, n = X.shape
    if T < 2:
        mu = np.zeros(n)
        S = np.eye(n)
        return S, 1.0

    # Sample covariance (denominator T-1 for unbiased, but LW uses T)
    S = (X.T @ X) / T
    mu = np.trace(S) / n
    F = mu * np.eye(n)  # shrinkage target (scaled identity)

    # Compute optimal shrinkage intensity
    # delta = sum of squared deviations of S from F
    delta_sq = np.sum((S - F) ** 2)

    # Compute X2 = element-wise squared returns for the variance of S
    X2 = X**2
    # phi = sum of (X_t^2)' * (X_t^2) / T^2 - 2 * trace(S .* S') / T + (trace(S)/n)^2
    phi_mat = (X2.T @ X2) / T**2
    phi = np.sum(phi_mat) - 2.0 * np.trace(S @ S) / T + mu**2 * n

    # Clamp phi to [0, delta^2]
    phi = max(0.0, min(phi, delta_sq))

    gamma = np.linalg.norm(S - F, "fro") ** 2
    if gamma == 0:
        return F, 1.0

    shrinkage = min(1.0, phi / delta_sq) if delta_sq > 0 else 1.0
    shrunk = shrinkage * F + (1.0 - shrinkage) * S
    return shrunk, shrinkage


def ledoit_wolf_covariance(returns: pd.DataFrame, periods_per_year: int = 252) -> np.ndarray:
    """Annualized Ledoit-Wolf shrinkage covariance matrix.

    More stable than sample covariance when n/T ratio is high.
    """
    X = returns.values - returns.values.mean(axis=0, keepdims=True)
    shrunk, _ = _ledoit_wolf_shrinkage(X)
    return shrunk * periods_per_year


# ---------------------------------------------------------------------------
# PCA-based factor risk model
# ---------------------------------------------------------------------------


def factor_covariance(
    returns: pd.DataFrame,
    n_factors: int | None = None,
    periods_per_year: int = 252,
) -> np.ndarray:
    """Simplified PCA factor risk model.

    Decomposes: Sigma = B @ F @ B.T + D
    - B: (n, k) factor loadings
    - F: (k, k) factor covariance
    - D: (n, n) diagonal idiosyncratic risk

    If n_factors is None, use min(3, n//3).
    """
    R = returns.values
    T, n = R.shape
    if n_factors is None:
        n_factors = min(3, max(1, n // 3))
    n_factors = min(n_factors, n)

    # Demean
    R_centered = R - R.mean(axis=0, keepdims=True)

    # Eigendecomposition of sample covariance
    S = (R_centered.T @ R_centered) / max(T - 1, 1)
    eigenvalues, eigenvectors = np.linalg.eigh(S)

    # Sort descending
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    # Factor loadings = first k eigenvectors scaled by sqrt(eigenvalue)
    B = eigenvectors[:, :n_factors] * np.sqrt(np.maximum(eigenvalues[:n_factors], 0.0))

    # Factor covariance
    F = np.diag(np.maximum(eigenvalues[:n_factors], 0.0))

    # Idiosyncratic variance = diagonal of (S - B @ F @ B.T)
    residual = S - B @ F @ B.T
    D = np.diag(np.maximum(np.diag(residual), 0.0))

    # Full factor-model covariance
    cov = B @ F @ B.T + D
    return np.asarray(cov * periods_per_year)


# ---------------------------------------------------------------------------
# CovarianceEstimator (unified interface)
# ---------------------------------------------------------------------------

MethodType = Literal["sample", "ledoit_wolf", "factor", "shrinkage"]


@dataclass
class CovarianceEstimator:
    """Unified covariance estimator with method selection.

    Usage:
        est = CovarianceEstimator(method="ledoit_wolf")
        cov_matrix = est.fit(returns_df)
        corr_matrix = est.correlation()
        vols = est.volatility()
    """

    # 取值域见 MethodType; 调用方常传配置来的普通 str, fit() 内已做运行时校验
    method: str = "ledoit_wolf"
    n_factors: int | None = None
    periods_per_year: int = 252

    _cov: np.ndarray | None = None
    _symbols: list[str] | None = None

    def fit(self, returns: pd.DataFrame) -> np.ndarray:
        """Estimate and cache the covariance matrix."""
        self._symbols = list(returns.columns)
        method = self.method.lower()

        if method == "sample":
            self._cov = sample_covariance(returns, self.periods_per_year)
        elif method in ("ledoit_wolf", "shrinkage"):
            self._cov = ledoit_wolf_covariance(returns, self.periods_per_year)
        elif method == "factor":
            self._cov = factor_covariance(returns, self.n_factors, self.periods_per_year)
        else:
            raise ValueError(f"Unknown method: {self.method}")

        return self._cov

    @property
    def covariance(self) -> np.ndarray:
        if self._cov is None:
            raise RuntimeError("Call fit() first")
        return self._cov

    def correlation(self) -> np.ndarray:
        """Correlation matrix derived from the fitted covariance."""
        cov = self.covariance
        std = np.sqrt(np.diag(cov))
        std[std == 0] = 1.0
        return np.asarray(cov / np.outer(std, std))

    def volatility(self) -> np.ndarray:
        """Annualized volatility vector."""
        return np.sqrt(np.diag(self.covariance))

    @property
    def symbols(self) -> list[str]:
        if self._symbols is None:
            raise RuntimeError("Call fit() first")
        return self._symbols
