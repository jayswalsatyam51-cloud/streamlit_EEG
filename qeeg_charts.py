"""Plotly charts for QEEG vertical / horizontal Streamlit views."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

Z_THRESHOLD = 1.96

BAND_ORDER = [
    "DELTA",
    "THETA",
    "ALPHA",
    "BETA",
    "HIGH BETA",
    "BETA 1",
    "BETA 2",
    "BETA 3",
]

RATIO_BAND_ORDER = [
    "D/T",
    "D/A",
    "D/B",
    "D/G",
    "T/A",
    "T/B",
    "T/G",
    "A/B",
    "A/G",
    "B/G",
]


def _order_bands(df: pd.DataFrame, band_col: str = "band") -> pd.DataFrame:
    order = RATIO_BAND_ORDER if df[band_col].isin(RATIO_BAND_ORDER).any() else BAND_ORDER
    cat = pd.Categorical(df[band_col], categories=order, ordered=True)
    out = df.copy()
    out[band_col] = cat
    return out.sort_values(band_col)


def _band_means(df: pd.DataFrame, subsection: str) -> pd.DataFrame:
    work = df.copy()
    if subsection != "ALL":
        work = work[work["Subsection"] == subsection]
    if work.empty:
        return pd.DataFrame()
    agg = (
        work.groupby("Band", as_index=False)
        .agg(
            t1=("T1 Z", lambda s: float(s.abs().mean())),
            t2=("T2 Z", lambda s: float(s.abs().mean())),
        )
    )
    return _order_bands(agg.rename(columns={"Band": "band"}))


def fig_z_trajectory(
    df: pd.DataFrame,
    subsection: str,
    ec_label: str,
    eo_label: str,
    *,
    title: str = "Band trajectory (mean |Z|)",
) -> go.Figure:
    """Line chart EC vs EO across bands — mirrors vertical analysis trajectory view."""
    means = _band_means(df, subsection)
    if means.empty:
        return go.Figure()

    fig = go.Figure()
    fig.add_hrect(y0=Z_THRESHOLD, y1=12, fillcolor="rgba(239,68,68,0.08)", line_width=0)
    fig.add_hrect(y0=-12, y1=-Z_THRESHOLD, fillcolor="rgba(239,68,68,0.08)", line_width=0)
    fig.add_hline(y=0, line_color="#cbd5e1", line_width=1)
    fig.add_hline(y=Z_THRESHOLD, line_dash="dot", line_color="#ef4444", line_width=1)
    fig.add_hline(y=-Z_THRESHOLD, line_dash="dot", line_color="#ef4444", line_width=1)

    fig.add_trace(
        go.Scatter(
            x=means["band"].astype(str),
            y=means["t1"],
            mode="lines+markers",
            name=ec_label,
            line=dict(color="#2563eb", width=3),
            marker=dict(size=8),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=means["band"].astype(str),
            y=means["t2"],
            mode="lines+markers",
            name=eo_label,
            line=dict(color="#db2777", width=3),
            marker=dict(size=8),
        )
    )
    fig.update_layout(
        title=f"{title} — {subsection}",
        xaxis_title="Band",
        yaxis_title="Mean |Z|",
        template="plotly_white",
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def fig_pct_change_bars(stats_df: pd.DataFrame, subsection: str) -> go.Figure:
    """Percent change by band for one subsection."""
    work = stats_df[stats_df["subsection"] == subsection].copy()
    if work.empty:
        return go.Figure()
    work = _order_bands(work, "band")
    colors = ["#dc2626" if v >= 0 else "#16a34a" for v in work["pct_change"]]
    fig = go.Figure(
        go.Bar(
            x=work["band"].astype(str),
            y=work["pct_change"],
            marker_color=colors,
            text=[f"{v:.1f}%" for v in work["pct_change"]],
            textposition="outside",
        )
    )
    fig.update_layout(
        title=f"Percent change by band — {subsection}",
        xaxis_title="Band",
        yaxis_title="% change (EC → EO)",
        template="plotly_white",
        height=380,
    )
    return fig


def fig_heatmap_pct_change(stats_df: pd.DataFrame) -> go.Figure:
    """Heatmap: subsection × band percent change."""
    if stats_df.empty:
        return go.Figure()
    pivot = stats_df.pivot_table(
        index="subsection", columns="band", values="pct_change", aggfunc="mean"
    )
    col_order = [b for b in BAND_ORDER + RATIO_BAND_ORDER if b in pivot.columns]
    pivot = pivot[col_order] if col_order else pivot
    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=list(pivot.columns.astype(str)),
            y=list(pivot.index.astype(str)),
            colorscale="RdYlGn_r",
            colorbar=dict(title="% Δ"),
        )
    )
    fig.update_layout(
        title="Percent change heatmap (subsection × band)",
        template="plotly_white",
        height=320,
    )
    return fig


def fig_subsection_comparison(stats_df: pd.DataFrame, band: str) -> go.Figure:
    """Grouped bar: EC vs EO mean |Z| per subsection for one band."""
    work = stats_df[stats_df["band"] == band].copy()
    if work.empty:
        return go.Figure()
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="EC",
            x=work["subsection"],
            y=work["set1_mean_abs"],
            marker_color="#2563eb",
        )
    )
    fig.add_trace(
        go.Bar(
            name="EO",
            x=work["subsection"],
            y=work["set2_mean_abs"],
            marker_color="#db2777",
        )
    )
    fig.update_layout(
        barmode="group",
        title=f"EC vs EO by subsection — {band}",
        xaxis_title="Subsection",
        yaxis_title="Mean |Z|",
        template="plotly_white",
        height=380,
    )
    return fig


def fig_channel_sparkline(
    df: pd.DataFrame,
    band: str,
    subsection: str,
    ec_label: str,
    eo_label: str,
    *,
    max_channels: int = 40,
) -> go.Figure:
    """Scatter EC vs EO per channel (vertical comparison cloud)."""
    work = df[(df["Band"] == band) & (df["Subsection"] == subsection)].copy()
    if work.empty:
        return go.Figure()
    work = work.head(max_channels)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=work["T1 Z"],
            y=work["T2 Z"],
            mode="markers",
            text=work["Channel"],
            marker=dict(size=9, color="#6366f1", opacity=0.75),
            name="Regions",
        )
    )
    lim = max(
        float(work["T1 Z"].abs().max()),
        float(work["T2 Z"].abs().max()),
        Z_THRESHOLD,
    ) * 1.1
    fig.add_trace(
        go.Scatter(
            x=[-lim, lim],
            y=[-lim, lim],
            mode="lines",
            line=dict(color="#94a3b8", dash="dash"),
            showlegend=False,
            name="unity",
        )
    )
    fig.update_layout(
        title=f"Regional comparison — {band} / {subsection}",
        xaxis_title=f"{ec_label} |Z|",
        yaxis_title=f"{eo_label} |Z|",
        template="plotly_white",
        height=420,
    )
    return fig


def fig_horizontal_timeline(
    matrix_df: pd.DataFrame,
    ec_label: str,
    eo_label: str,
    row_label: str,
) -> go.Figure:
    """Two-point timeline (EC → EO) for matrix row."""
    if matrix_df.empty:
        return go.Figure()
    row = matrix_df[matrix_df["label"] == row_label]
    if row.empty:
        row = matrix_df.head(1)
    r = row.iloc[0]
    y1, y2 = r.get("set_1"), r.get("set_2")
    fig = go.Figure()
    fig.add_hrect(y0=Z_THRESHOLD, y1=12, fillcolor="rgba(239,68,68,0.08)", line_width=0)
    fig.add_hrect(y0=-12, y1=-Z_THRESHOLD, fillcolor="rgba(239,68,68,0.08)", line_width=0)
    fig.add_trace(
        go.Scatter(
            x=[ec_label, eo_label],
            y=[y1, y2],
            mode="lines+markers",
            line=dict(color="#2563eb", width=3),
            marker=dict(size=10),
            name=row_label,
        )
    )
    fig.add_hline(y=Z_THRESHOLD, line_dash="dot", line_color="#ef4444")
    fig.add_hline(y=-Z_THRESHOLD, line_dash="dot", line_color="#ef4444")
    fig.update_layout(
        title=f"Timeline — {row_label}",
        yaxis_title="Z score",
        template="plotly_white",
        height=380,
    )
    return fig


def fig_neurotrack_trajectory(
    timeline_sets: list[dict[str, Any]],
    *,
    segment: str,
    band: str,
    set_labels: list[str],
) -> go.Figure:
    """EC → EO trajectory (NeuroTrack / kwikedart Vertical mode)."""
    if not timeline_sets:
        return go.Figure()

    x_labels = set_labels[: len(timeline_sets)]
    if band == "ALL":
        all_bands = sorted(
            {
                b
                for ts in timeline_sets
                for seg_data in ts["data"].values()
                for b in seg_data
                if len(str(b)) <= 12
            }
        )
        fig = go.Figure()
        colors = [
            "#2563eb",
            "#db2777",
            "#ea580c",
            "#16a34a",
            "#9333ea",
            "#0891b2",
        ]
        for idx, b in enumerate(all_bands[:8]):
            ys = []
            for ts in timeline_sets:
                if segment == "GLOBAL_AVG":
                    vals = [
                        seg_data.get(b)
                        for seg_data in ts["data"].values()
                        if b in seg_data and seg_data.get(b) is not None
                    ]
                    ys.append(float(sum(vals) / len(vals)) if vals else None)
                else:
                    ys.append(ts["data"].get(segment, {}).get(b))
            fig.add_trace(
                go.Scatter(
                    x=x_labels,
                    y=ys,
                    mode="lines+markers",
                    name=str(b),
                    line=dict(color=colors[idx % len(colors)], width=2),
                    connectgaps=True,
                )
            )
        title_seg = "Global Brain Average" if segment == "GLOBAL_AVG" else segment
        fig.update_layout(
            title=f"Trajectory — {title_seg} (all bands)",
            yaxis_title="Z score",
            template="plotly_white",
            height=420,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        return fig

    ys = []
    for ts in timeline_sets:
        if segment == "GLOBAL_AVG":
            vals = [
                seg_data.get(band)
                for seg_data in ts["data"].values()
                if band in seg_data and seg_data.get(band) is not None
            ]
            ys.append(float(sum(vals) / len(vals)) if vals else None)
        else:
            ys.append(ts["data"].get(segment, {}).get(band))
    fig = go.Figure()
    fig.add_hrect(y0=Z_THRESHOLD, y1=12, fillcolor="rgba(239,68,68,0.08)", line_width=0)
    fig.add_hrect(y0=-12, y1=-Z_THRESHOLD, fillcolor="rgba(239,68,68,0.08)", line_width=0)
    fig.add_hline(y=0, line_color="#cbd5e1", line_width=1)
    fig.add_hline(y=Z_THRESHOLD, line_dash="dot", line_color="#ef4444", line_width=1)
    fig.add_hline(y=-Z_THRESHOLD, line_dash="dot", line_color="#ef4444", line_width=1)
    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=ys,
            mode="lines+markers",
            line=dict(color="#2563eb", width=3),
            marker=dict(size=10),
            name="Z score",
            connectgaps=True,
        )
    )
    title_seg = "Global Brain Average" if segment == "GLOBAL_AVG" else segment
    fig.update_layout(
        title=f"Trajectory — {title_seg} ({band})",
        yaxis_title="Z score",
        template="plotly_white",
        height=400,
    )
    return fig


def fig_top_clinical_changes(stats_df: pd.DataFrame, *, top_n: int = 10) -> go.Figure:
    """Horizontal bar chart of largest |% change| across sections (clinical summary)."""
    if stats_df.empty:
        return go.Figure()
    work = stats_df.copy()
    work["label"] = work["subsection"].astype(str) + " · " + work["band"].astype(str)
    work = work.reindex(work["pct_change"].abs().sort_values(ascending=True).tail(top_n).index)
    colors = ["#dc2626" if v >= 0 else "#16a34a" for v in work["pct_change"]]
    fig = go.Figure(
        go.Bar(
            x=work["pct_change"],
            y=work["label"],
            orientation="h",
            marker_color=colors,
            text=[f"{v:.1f}%" for v in work["pct_change"]],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Largest percent changes (EC → EO)",
        xaxis_title="% change",
        template="plotly_white",
        height=max(280, 36 * len(work)),
        margin=dict(l=120),
    )
    return fig


def fig_symptom_scores(symptoms: list[dict[str, Any]]) -> go.Figure:
    """Horizontal bar chart of symptom engine scores."""
    if not symptoms:
        return go.Figure()
    names = [s["name"] for s in symptoms]
    scores = [s["score"] for s in symptoms]
    colors = ["#dc2626" if sc > 7 else "#f59e0b" if sc > 4 else "#10b981" for sc in scores]
    fig = go.Figure(
        go.Bar(
            x=scores,
            y=names,
            orientation="h",
            marker_color=colors,
            text=[f"{s:.1f}" for s in scores],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Symptom pattern scores",
        xaxis_title="Severity (0–10)",
        template="plotly_white",
        height=320,
        xaxis=dict(range=[0, 10]),
    )
    return fig
