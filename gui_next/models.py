# -*- coding: utf-8 -*-
"""Qt data models for DataFrame-backed tables (thousands of rows)."""

from __future__ import annotations

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class DataFrameModel(QAbstractTableModel):
    """A minimal QAbstractTableModel over a pandas DataFrame.

    Tables render via QTableView with virtual scrolling; sorting re-sorts
    the underlying frame. Numeric columns render right-aligned.
    """

    def __init__(self, df: pd.DataFrame | None = None, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame = df if df is not None else pd.DataFrame()

    def set_dataframe(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self.endResetModel()

    def df(self) -> pd.DataFrame:
        return self._df

    def row(self, index: QModelIndex) -> dict:
        if not index.isValid():
            return {}
        return self._df.iloc[index.row()].to_dict()

    # Qt overrides -----------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            try:
                return str(self._df.columns[section])
            except IndexError:
                return None
        return str(section + 1)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            value = self._df.iat[index.row(), index.column()]
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return ""
            text = str(value)
            return text if len(text) <= 300 else text[:297] + "…"
        if role == Qt.TextAlignmentRole:
            column = self._df.columns[index.column()]
            if pd.api.types.is_numeric_dtype(self._df[column]):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None

    def sort(self, column: int, order=Qt.AscendingOrder) -> None:
        if column < 0 or column >= len(self._df.columns):
            return
        self.layoutAboutToBeChanged.emit()
        by = self._df.columns[column]
        self._df = self._df.sort_values(by, ascending=(order == Qt.AscendingOrder))
        self.layoutChanged.emit()
