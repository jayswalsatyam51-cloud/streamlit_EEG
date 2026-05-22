"""JSON serialization helpers for analysis API responses."""

from __future__ import annotations

from typing import Any

import pandas as pd

from qeeg_statistical_analysis import AnalysisPackage


def _df_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    return df.replace({float("nan"): None}).to_dict(orient="records")


def package_to_json(pkg: AnalysisPackage, *, cswl_format: str | None = None) -> dict[str, Any]:
    """Safe JSON payload for the web dashboard."""
    return {
        "mode": pkg.mode,
        "cswl_format": cswl_format,
        "vertical_subsection_stats": _df_records(pkg.vertical_subsection_stats),
        "horizontal_matrix": _df_records(pkg.horizontal_matrix),
        "symptom_results": pkg.symptom_results,
        "compact_diagnostics": pkg.compact_diagnostics,
        "global_top_changes": (pkg.clinical_diagnostics or {}).get(
            "global_top_percent_changes", []
        ),
        "sections": list(pkg.section_frames.keys()),
    }
