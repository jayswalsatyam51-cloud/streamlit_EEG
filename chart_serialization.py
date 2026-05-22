"""Serialize Plotly figures for the web dashboard (same charts as Streamlit)."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from qeeg_charts import (
    fig_channel_sparkline,
    fig_heatmap_pct_change,
    fig_neurotrack_trajectory,
    fig_pct_change_bars,
    fig_subsection_comparison,
    fig_symptom_scores,
    fig_top_clinical_changes,
    fig_z_trajectory,
)
from qeeg_statistical_analysis import AnalysisPackage, build_neurotrack_table_rows


def figure_to_json(fig: go.Figure) -> dict[str, Any]:
    if not fig.data:
        return {"data": [], "layout": {}}
    return json.loads(fig.to_json())


def build_clinical_charts(
    pkg: AnalysisPackage,
    *,
    section: str,
    subsection: str,
    band: str,
    ec_label: str,
    eo_label: str,
) -> dict[str, Any]:
    stats = pkg.vertical_subsection_stats
    charts: dict[str, Any] = {}
    if not stats.empty:
        charts["top_changes"] = figure_to_json(fig_top_clinical_changes(stats))
        charts["heatmap"] = figure_to_json(fig_heatmap_pct_change(stats))
        sec_stats = stats[stats["section"] == section] if "section" in stats.columns else stats
        if not sec_stats.empty:
            charts["pct_bars"] = figure_to_json(fig_pct_change_bars(sec_stats, subsection))
            charts["subsection_cmp"] = figure_to_json(fig_subsection_comparison(sec_stats, band))
    df = pkg.section_frames.get(section)
    if df is not None and not df.empty:
        charts["trajectory"] = figure_to_json(
            fig_z_trajectory(df, subsection, ec_label, eo_label, title=section)
        )
        if subsection != "ALL":
            charts["channel_scatter"] = figure_to_json(
                fig_channel_sparkline(df, band, subsection, ec_label, eo_label)
            )
    return charts


def build_neurotrack_charts(
    pkg: AnalysisPackage,
    *,
    segment: str,
    band: str,
    ec_label: str,
    eo_label: str,
    expand_global: bool = True,
) -> dict[str, Any]:
    charts: dict[str, Any] = {}
    if pkg.timeline_sets:
        charts["trajectory"] = figure_to_json(
            fig_neurotrack_trajectory(
                pkg.timeline_sets,
                segment=segment,
                band=band,
                set_labels=[ec_label, eo_label],
            )
        )
    if pkg.symptom_results:
        charts["symptoms"] = figure_to_json(fig_symptom_scores(pkg.symptom_results))
    return charts


def segments_from_timeline(pkg: AnalysisPackage) -> list[str]:
    if not pkg.timeline_sets:
        return ["GLOBAL_AVG"]
    segs = sorted({s for ts in pkg.timeline_sets for s in ts["data"]})
    return ["GLOBAL_AVG"] + segs[:80]
