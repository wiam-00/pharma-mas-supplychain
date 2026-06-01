"""
simulation/env_simulator.py
Environnement de simulation de la supply chain pharmaceutique.

Rôle :
  - Charge le dataset CSV une seule fois en mémoire.
  - Expose les snapshots quotidiens (une journée complète = toutes pharmacies/drugs).
  - Fournit des méthodes de filtrage pour chaque agent consommateur.
  - Thread-safe : les snapshots sont émis séquentiellement sans état partagé.
"""

import logging
from typing import Iterator

import pandas as pd

from config import DATASET_PATH, DATASET_PATH_RAW, START_DATE, END_DATE

logger = logging.getLogger("MAS.Environment")


class PharmacyEnvironment:
    """
    Source de données centrale du MAS.
    Instancier une seule fois dans main.py et partager la référence.
    """

    def __init__(self, path: str | None = None):
        resolved = path or DATASET_PATH
        try:
            self.df = pd.read_csv(resolved, parse_dates=["Date", "Expiry_Date"])
        except FileNotFoundError:
            logger.warning(
                f"[WARNING] Processed dataset not found at '{resolved}'. "
                f"Falling back to raw dataset at '{DATASET_PATH_RAW}'."
            )
            self.df = pd.read_csv(DATASET_PATH_RAW, parse_dates=["Date", "Expiry_Date"])

        self.df = self.df[
            (self.df["Date"] >= START_DATE) &
            (self.df["Date"] <= END_DATE)
        ].reset_index(drop=True)

        self.dates       = sorted(self.df["Date"].dt.date.unique())
        self._cursor     = 0
        self.total_days  = len(self.dates)

        logger.info(
            f"[INFO] PharmacyEnvironment ready — "
            f"{len(self.df):,} rows | {self.total_days} days | "
            f"{self.df['Pharmacy_ID'].nunique()} pharmacies | "
            f"{self.df['Drug_ID'].nunique()} drugs"
        )

    # ── Itération ────────────────────────────────────────────────────────────

    def has_next(self) -> bool:
        return self._cursor < self.total_days

    def next_snapshot(self) -> pd.DataFrame | None:
        """Retourne toutes les lignes du prochain jour, ou None si terminé."""
        if not self.has_next():
            return None
        date     = self.dates[self._cursor]
        snapshot = self.df[self.df["Date"].dt.date == date].copy()
        self._cursor += 1
        logger.debug(
            f"[TICK {self._cursor}/{self.total_days}] "
            f"Date={date} | {len(snapshot)} records"
        )
        return snapshot

    def iter_snapshots(self) -> Iterator[pd.DataFrame]:
        """Générateur Python — alternative à has_next() / next_snapshot()."""
        while self.has_next():
            yield self.next_snapshot()

    def reset(self):
        self._cursor = 0
        logger.info("[INFO] Environment reset to day 0.")

    # ── Filtres métier (utilisés par les agents) ──────────────────────────────

    def get_stock_alerts(self, snapshot: pd.DataFrame) -> pd.DataFrame:
        """
        Pour StockAgent : lignes avec stockout OU transfert urgent.
        """
        mask = (snapshot["Stockout_Flag"] == 1) | (snapshot["Transfer_Needed_Flag"] == 1)
        return self._prioritize(snapshot[mask].copy())

    def get_expiry_rows(self, snapshot: pd.DataFrame) -> pd.DataFrame:
        """
        Pour SafetyAgent : lignes avec péremption proche (Near_Expiry_Flag).
        """
        mask = snapshot["Near_Expiry_Flag"] == 1
        return snapshot[mask].copy()

    def get_demand_rows(self, snapshot: pd.DataFrame) -> pd.DataFrame:
        """
        Pour PredictionAgent : toutes les lignes avec Units_Sold > 0
        (données d'entraînement pour la prévision de demande).
        """
        return snapshot[snapshot["Units_Sold"] > 0].copy()

    # ── Utilitaires ───────────────────────────────────────────────────────────

    @staticmethod
    def _prioritize(df: pd.DataFrame) -> pd.DataFrame:
        """Trie les alertes par criticité décroissante."""
        if df.empty:
            return df
        df["_priority_score"] = (
            df["Is_Critical_Drug"] * 10 +
            df["Stockout_Flag"] * 5 +
            df["Transfer_Needed_Flag"] * 3
        )
        return df.sort_values("_priority_score", ascending=False).drop(
            columns=["_priority_score"]
        )

    def get_history(
        self,
        pharmacy_id: str,
        drug_id: str,
        n_days: int = 30,
    ) -> pd.DataFrame:
        """
        Retourne les N derniers jours de données pour un couple (pharmacy, drug).
        Utilisé par PredictionAgent pour construire ses features.
        """
        current_date = self.dates[min(self._cursor, self.total_days - 1)]
        mask = (
            (self.df["Pharmacy_ID"] == pharmacy_id) &
            (self.df["Drug_ID"]     == drug_id) &
            (self.df["Date"].dt.date <= current_date)
        )
        return self.df[mask].tail(n_days).copy()

    @property
    def progress_pct(self) -> float:
        return round(self._cursor / max(self.total_days, 1) * 100, 1)