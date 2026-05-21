import os
from typing import Dict

import pandas as pd

from shared.normalization import normalize_basic


def read_table(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    elif ext == ".csv":
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(path, encoding="gbk")
    else:
        raise ValueError("Unsupported file type: choose .xlsx/.xls/.csv")


def write_table(df: pd.DataFrame, path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        df.to_excel(path, index=False)
    elif ext == ".csv":
        df.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        raise ValueError("Unsupported export type: choose .xlsx/.csv")


def load_overrides(path: str) -> Dict[str, str]:
    if not path:
        return {}
    try:
        if path.lower().endswith(".csv"):
            odf = pd.read_csv(path)
        else:
            odf = pd.read_excel(path)
        cols = {c.lower().strip(): c for c in odf.columns}
        kcol = cols.get("source_merged") or cols.get("source") or list(odf.columns)[0]
        vcol = cols.get("country") or list(odf.columns)[1]
        out = {}
        for _, r in odf.iterrows():
            k = normalize_basic(r.get(kcol, ""))
            v = normalize_basic(r.get(vcol, ""))
            if k and v:
                out[k] = v
        return out
    except Exception as e:
        import sys
        print(f"[overrides] failed to load from '{path}': {e}", file=sys.stderr)
        return {}
