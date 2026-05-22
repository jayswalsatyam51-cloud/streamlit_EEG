"""JSON serialization helpers for analysis API responses."""

from __future__ import annotations

from typing import Any

import pandas as pd

from chart_serialization import (
    build_clinical_charts,
    build_neurotrack_charts,
    segments_from_timeline,
)
from qeeg_statistical_analysis import AnalysisPackage, build_neurotrack_table_rows


def _df_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    return df.replace({float("nan"): None}).to_dict(orient="records")


def package_to_json(
    pkg: AnalysisPackage,
    *,
    cswl_format: str | None = None,
    ec_label: str = "EC (Eyes Closed)",
    eo_label: str = "EO (Eyes Open)",
    chart_section: str = "Z Scored FFT Absolute Power",
    chart_subsection: str = "LEFT",
    chart_band: str = "DELTA",
    horizontal_segment: str = "GLOBAL_AVG",
    horizontal_band: str = "DELTA",
    expand_global: bool = True,
) -> dict[str, Any]:
    """Full payload for web UI — mirrors Streamlit results."""
    payload: dict[str, Any] = {
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
        "charts": {},
    }

    if pkg.mode == "vertical":
        payload["charts"] = build_clinical_charts(
            pkg,
            section=chart_section,
            subsection=chart_subsection,
            band=chart_band,
            ec_label=ec_label,
            eo_label=eo_label,
        )
        payload["channel_tables"] = {
            name: _df_records(df.head(120))
            for name, df in pkg.vertical_channel_tables.items()
        }
    else:
        rows = build_neurotrack_table_rows(
            pkg.timeline_sets,
            selected_segment=horizontal_segment,
            selected_band=horizontal_band,
            expand_global=expand_global,
        )
        payload["neurotrack_table_rows"] = rows
        payload["segments"] = segments_from_timeline(pkg)
        payload["charts"] = build_neurotrack_charts(
            pkg,
            segment=horizontal_segment,
            band=horizontal_band,
            ec_label=ec_label,
            eo_label=eo_label,
            expand_global=expand_global,
        )

    return payload
