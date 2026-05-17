"""
QEEG statistical analysis — Vertical (Set 1 vs Set 2) and Horizontal (timeline / matrix).

Ported from NeuroTrack horizontal (QEEG-2.1.1.jsx) and vertical comparison patterns.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

from metrics_core import compute_subsection_bandwise_metrics

AnalysisMode = Literal["vertical", "horizontal"]

CSWL_SECTION_ORDER = [
    "Z Scored FFT Absolute Power",
    "Z Scored FFT Power Ratio",
    "Z Scored Peak Frequency",
]

BAND_SHORT = {
    "DELTA": "D",
    "THETA": "T",
    "ALPHA": "A",
    "BETA": "B",
    "HIGH BETA": "HB",
    "BETA 1": "B1",
    "BETA 2": "B2",
    "BETA 3": "B3",
}

SYMPTOM_RULES: list[dict[str, Any]] = [
    {
        "id": "anxiety",
        "name": "Anxiety / Hyper-arousal",
        "icd": ["F41.1", "F41.9"],
        "description": "Excessive Beta activity or frontal/temporal hyper-arousal patterns.",
        "checks": [
            {"band": "HB", "threshold": 1.5, "type": "high"},
            {"band": "B3", "threshold": 1.5, "type": "high"},
            {"band": "A", "threshold": 2.0, "type": "high", "segment_keyword": "Tha"},
        ],
    },
    {
        "id": "depression",
        "name": "Mood Dysregulation / Depression",
        "icd": ["F32.9", "F34.1"],
        "description": "Frontal alpha asymmetry or widespread low-frequency shifts.",
        "checks": [
            {"band": "A", "threshold": 1.5, "type": "high", "segment_keyword": "1L"},
            {"band": "D", "threshold": 1.5, "type": "low"},
        ],
    },
    {
        "id": "attention",
        "name": "Attention / Executive Function",
        "icd": ["F90.0", "R41.84"],
        "description": "Elevated Theta or disconnected Beta in frontal regions.",
        "checks": [
            {"band": "T", "threshold": 2.0, "type": "high", "segment_keyword": "1"},
            {"band": "D", "threshold": 2.0, "type": "high"},
            {"band": "B1", "threshold": 1.5, "type": "low"},
        ],
    },
    {
        "id": "pain",
        "name": "Chronic Pain / Tension",
        "icd": ["G89.2", "R52"],
        "description": "Central/parietal High Beta or thalamic dysregulation.",
        "checks": [
            {"band": "HB", "threshold": 1.5, "type": "high", "segment_keyword": "Tha"},
            {"band": "B3", "threshold": 1.5, "type": "high"},
        ],
    },
    {
        "id": "trauma",
        "name": "Trauma / PTSD Patterns",
        "icd": ["F43.10", "F43.12"],
        "description": "Temporal instability or elevated slow frequencies.",
        "checks": [
            {"band": "T", "threshold": 2.0, "type": "high", "segment_keyword": "Tha"},
            {"band": "A", "threshold": 1.5, "type": "low"},
        ],
    },
]


@dataclass
class DescriptiveStats:
    n: int
    mean: float
    sd: float
    median: float
    iqr: float
    min: float
    max: float
    range: float
    abnormal_rate_pct: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "mean": round(self.mean, 2),
            "sd": round(self.sd, 2),
            "median": round(self.median, 2),
            "iqr": round(self.iqr, 2),
            "min": round(self.min, 2),
            "max": round(self.max, 2),
            "range": round(self.range, 2),
            "abnormal_rate_pct": round(self.abnormal_rate_pct, 1),
        }


def calculate_descriptive_stats(values_raw: list[float | None]) -> DescriptiveStats | None:
    """Same statistics as NeuroTrack horizontal matrix (mean, SD, median, IQR, % abnormal)."""
    values = [float(v) for v in values_raw if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if not values:
        return None
    arr = np.array(values, dtype=float)
    n = len(arr)
    sorted_v = np.sort(arr)
    mean = float(np.mean(arr))
    sd = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    mid = n // 2
    median = float(sorted_v[mid]) if n % 2 else float((sorted_v[mid - 1] + sorted_v[mid]) / 2)
    q1 = float(sorted_v[int(n * 0.25)])
    q3 = float(sorted_v[int(n * 0.75)])
    abnormal = int(np.sum(np.abs(arr) > 1.96))
    return DescriptiveStats(
        n=n,
        mean=mean,
        sd=sd,
        median=median,
        iqr=q3 - q1,
        min=float(sorted_v[0]),
        max=float(sorted_v[-1]),
        range=float(sorted_v[-1] - sorted_v[0]),
        abnormal_rate_pct=(abnormal / n) * 100,
    )


def _section_csv_map(csv_files: list[str]) -> dict[str, str]:
    return {os.path.basename(f).replace(".csv", ""): f for f in csv_files}


def _load_section_frames(csv_files: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for section, path in _section_csv_map(csv_files).items():
        if section in CSWL_SECTION_ORDER and os.path.exists(path):
            out[section] = pd.read_csv(path)
    return out


def _segment_band_value(row: pd.Series, use_set: Literal[1, 2]) -> float:
    col = "T1 Z" if use_set == 1 else "T2 Z"
    return float(row[col])


def csv_to_timeline_sets(
    df: pd.DataFrame,
    set1_name: str = "Set 1",
    set2_name: str = "Set 2",
) -> list[dict[str, Any]]:
    """Horizontal analysis input: one dict per set with segment -> band -> z value."""
    sets: list[dict[str, Any]] = []
    for set_idx, label in enumerate([set1_name, set2_name], start=1):
        data: dict[str, dict[str, float]] = {}
        for _, row in df.iterrows():
            ch = str(row["Channel"])
            band = str(row["Band"])
            val = _segment_band_value(row, 1 if set_idx == 1 else 2)
            if ch not in data:
                data[ch] = {}
            data[ch][band] = val
            short = BAND_SHORT.get(band)
            if short:
                data[ch][short] = val
        sets.append({"id": label, "filename": label, "label": label, "data": data})
    return sets


def build_horizontal_matrix(
    timeline_sets: list[dict[str, Any]],
    *,
    selected_segment: str,
    selected_band: str,
) -> pd.DataFrame:
    """
    Statistical matrix row per segment or band (mirrors NeuroTrack table).
    selected_band: band name or 'ALL'
    selected_segment: channel name or 'GLOBAL_AVG'
    """
    if not timeline_sets:
        return pd.DataFrame()

    all_segments = sorted({seg for s in timeline_sets for seg in s["data"]})
    sample_seg = all_segments[0] if all_segments else ""
    bands = sorted(
        {b for s in timeline_sets for seg, bd in s["data"].items() for b in bd if len(b) <= 12}
    )

    rows_out: list[dict[str, Any]] = []

    if selected_band == "ALL":
        row_labels = bands
        for band in row_labels:
            values = []
            for ts in timeline_sets:
                if selected_segment == "GLOBAL_AVG":
                    seg_vals = [
                        ts["data"].get(seg, {}).get(band)
                        for seg in all_segments
                        if band in ts["data"].get(seg, {})
                    ]
                    seg_vals = [v for v in seg_vals if v is not None]
                    values.append(
                        float(np.mean(seg_vals)) if seg_vals else None
                    )
                else:
                    values.append(ts["data"].get(selected_segment, {}).get(band))
            stats = calculate_descriptive_stats(values)
            row = {"label": band, "type": "band", **{f"set_{i+1}": v for i, v in enumerate(values)}}
            if stats:
                row.update(stats.as_dict())
            rows_out.append(row)
    else:
        if selected_segment == "GLOBAL_AVG":
            row_labels = all_segments
        else:
            row_labels = [selected_segment]
        for seg in row_labels:
            values = []
            for ts in timeline_sets:
                if selected_segment == "GLOBAL_AVG":
                    values.append(ts["data"].get(seg, {}).get(selected_band))
                else:
                    values.append(ts["data"].get(selected_segment, {}).get(selected_band))
            stats = calculate_descriptive_stats(values)
            row = {"label": seg, "type": "segment", **{f"set_{i+1}": v for i, v in enumerate(values)}}
            if stats:
                row.update(stats.as_dict())
            rows_out.append(row)

    return pd.DataFrame(rows_out)


def run_symptom_engine(
    timeline_set: dict[str, Any],
) -> list[dict[str, Any]]:
    """Symptom probability engine for one set (horizontal / NeuroTrack)."""
    target = timeline_set["data"]
    results: list[dict[str, Any]] = []

    for rule in SYMPTOM_RULES:
        max_severity = 0.0
        contributors: list[dict[str, Any]] = []
        for seg_name, seg_values in target.items():
            for check in rule["checks"]:
                if check.get("segment_keyword") and check["segment_keyword"] not in seg_name:
                    continue
                val = seg_values.get(check["band"])
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    continue
                severity = 0.0
                triggered = False
                if check["type"] == "high" and val > check["threshold"]:
                    severity = min(10.0, max(1.0, ((val - check["threshold"]) / 1.5) * 10))
                    triggered = True
                elif check["type"] == "low" and val < -check["threshold"]:
                    severity = min(
                        10.0,
                        max(1.0, ((abs(val) - check["threshold"]) / 1.5) * 10),
                    )
                    triggered = True
                if triggered:
                    max_severity = max(max_severity, severity)
                    contributors.append(
                        {
                            "segment": seg_name,
                            "band": check["band"],
                            "value": round(float(val), 3),
                            "severity": round(severity, 2),
                        }
                    )
        contributors.sort(key=lambda x: x["severity"], reverse=True)
        results.append(
            {
                "id": rule["id"],
                "name": rule["name"],
                "icd": rule["icd"],
                "description": rule["description"],
                "score": round(max_severity, 2),
                "contributors": contributors[:5],
            }
        )
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def build_vertical_summary_tables(
    csv_files: list[str],
) -> dict[str, pd.DataFrame]:
    """
    Vertical analysis: per-section channel-level Set1 vs Set2 with row stats.
    """
    frames = _load_section_frames(csv_files)
    tables: dict[str, pd.DataFrame] = {}

    for section, df in frames.items():
        if df.empty:
            continue
        work = df.copy()
        for c in ("T1 Z", "T2 Z", "DZ"):
            if c in work.columns:
                work[c] = pd.to_numeric(work[c], errors="coerce")
        work["delta_signed"] = work["T2 Z"] - work["T1 Z"]
        work["pct_change"] = np.where(
            work["T1 Z"].abs() > 1e-9,
            (work["delta_signed"].abs() / work["T1 Z"].abs()) * 100,
            0.0,
        )
        work["Percent_Change"] = np.where(
            work["T1 Z"].abs() > 1e-9,
            (work["delta_signed"] / work["T1 Z"].abs()) * 100,
            0.0,
        )
        work["abnormal_t1"] = work["T1 Z"].abs() > 1.96
        work["abnormal_t2"] = work["T2 Z"].abs() > 1.96
        tables[section] = work

    return tables


def build_vertical_subsection_stats(csv_files: list[str]) -> pd.DataFrame:
    """Aggregate vertical stats per section × subsection × band."""
    rows: list[dict[str, Any]] = []
    frames = _load_section_frames(csv_files)

    for section, df in frames.items():
        for subsection in df["Subsection"].dropna().unique():
            sub_df = df[df["Subsection"] == subsection]
            for band in sub_df["Band"].dropna().unique():
                band_df = sub_df[sub_df["Band"] == band]
                t1 = band_df["T1 Z"].astype(float)
                t2 = band_df["T2 Z"].astype(float)
                if band_df.empty:
                    continue
                abs_avg_1 = float(t1.abs().mean())
                abs_avg_2 = float(t2.abs().mean())
                delta = abs(abs_avg_1 - abs_avg_2)
                pct = (delta / abs_avg_1 * 100) if abs_avg_1 else 0.0
                norm = band_df["Normalize"].astype(str).value_counts()
                rows.append(
                    {
                        "section": section,
                        "subsection": subsection,
                        "band": band,
                        "n_channels": len(band_df),
                        "set1_mean_abs": round(abs_avg_1, 3),
                        "set2_mean_abs": round(abs_avg_2, 3),
                        "delta": round(delta, 3),
                        "pct_change": round(pct, 2),
                        "normalize_yes": int(norm.get("Yes", 0)),
                        "normalize_no": int(norm.get("No", 0)),
                        "normalize_ns": int(norm.get("NS", 0)),
                        "abnormal_set1_pct": round(float((t1.abs() > 1.96).mean() * 100), 1),
                        "abnormal_set2_pct": round(float((t2.abs() > 1.96).mean() * 100), 1),
                    }
                )
    return pd.DataFrame(rows)


def build_neurotrack_table_rows(
    timeline_sets: list[dict[str, Any]],
    *,
    selected_segment: str,
    selected_band: str,
    expand_global: bool = False,
) -> list[dict[str, Any]]:
    """Matrix rows matching QEEG-2.1.1.jsx / NeuroTrack Statistical Matrix."""
    if not timeline_sets:
        return []

    all_segments = sorted({seg for s in timeline_sets for seg in s["data"]})
    bands = sorted(
        {b for s in timeline_sets for seg, bd in s["data"].items() for b in bd if len(str(b)) <= 12}
    )
    rows_out: list[dict[str, Any]] = []

    if selected_band == "ALL":
        for band in bands:
            values = []
            for ts in timeline_sets:
                if selected_segment == "GLOBAL_AVG":
                    seg_vals = [
                        ts["data"].get(seg, {}).get(band)
                        for seg in all_segments
                        if band in ts["data"].get(seg, {})
                    ]
                    seg_vals = [v for v in seg_vals if v is not None]
                    values.append(float(np.mean(seg_vals)) if seg_vals else None)
                else:
                    values.append(ts["data"].get(selected_segment, {}).get(band))
            stats = calculate_descriptive_stats(values)
            rows_out.append(
                {
                    "label": band,
                    "type": "band",
                    "is_expandable": False,
                    "values": values,
                    "stats": stats.as_dict() if stats else None,
                }
            )
    elif selected_segment == "GLOBAL_AVG":
        global_values = []
        for ts in timeline_sets:
            vals = [
                ts["data"].get(seg, {}).get(selected_band)
                for seg in all_segments
                if selected_band in ts["data"].get(seg, {})
            ]
            vals = [v for v in vals if v is not None]
            global_values.append(float(np.mean(vals)) if vals else None)
        rows_out.append(
            {
                "label": "GLOBAL AVERAGE",
                "type": "main",
                "is_expandable": True,
                "values": global_values,
                "stats": calculate_descriptive_stats(global_values).as_dict()
                if calculate_descriptive_stats(global_values)
                else None,
            }
        )
        if expand_global:
            for seg in all_segments:
                values = [ts["data"].get(seg, {}).get(selected_band) for ts in timeline_sets]
                stats = calculate_descriptive_stats(values)
                rows_out.append(
                    {
                        "label": seg,
                        "type": "sub",
                        "is_expandable": False,
                        "values": values,
                        "stats": stats.as_dict() if stats else None,
                    }
                )
    else:
        values = [ts["data"].get(selected_segment, {}).get(selected_band) for ts in timeline_sets]
        stats = calculate_descriptive_stats(values)
        rows_out.append(
            {
                "label": selected_segment,
                "type": "main",
                "is_expandable": False,
                "values": values,
                "stats": stats.as_dict() if stats else None,
            }
        )
    return rows_out


@dataclass
class AnalysisPackage:
    mode: AnalysisMode
    section_frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    vertical_subsection_stats: pd.DataFrame = field(default_factory=pd.DataFrame)
    vertical_channel_tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    horizontal_matrix: pd.DataFrame = field(default_factory=pd.DataFrame)
    neurotrack_table_rows: list[dict[str, Any]] = field(default_factory=list)
    timeline_sets: list[dict[str, Any]] = field(default_factory=list)
    symptom_results: list[dict[str, Any]] = field(default_factory=list)
    clinical_diagnostics: dict[str, Any] = field(default_factory=dict)
    metrics_digest: str = ""
    compact_diagnostics: str = ""

    def to_prompt_context(self) -> str:
        parts = [self.compact_diagnostics, "", "--- METRICS DIGEST ---", self.metrics_digest]
        if self.clinical_diagnostics.get("compact_text"):
            parts.insert(1, self.clinical_diagnostics["compact_text"])
        if self.mode == "vertical" and self.symptom_results:
            parts.append("\n--- SYMPTOM ENGINE (NeuroTrack; top patterns) ---")
            for s in self.symptom_results[:5]:
                parts.append(
                    f"- {s['name']} (score {s['score']}/10, ICD {', '.join(s['icd'])}): "
                    f"{s['description']}"
                )
        if self.mode == "horizontal" and not self.vertical_subsection_stats.empty:
            parts.append("\n--- CLINICAL TOP % CHANGE ---")
            top = self.vertical_subsection_stats.sort_values("pct_change", ascending=False).head(8)
            for _, r in top.iterrows():
                parts.append(
                    f"- [{r['section']}] {r['subsection']}/{r['band']}: %Δ={r['pct_change']}%"
                )
        return "\n".join(parts).strip()


def run_statistical_analysis(
    csv_files: list[str],
    mode: AnalysisMode,
    *,
    set1_label: str = "Set 1",
    set2_label: str = "Set 2",
    horizontal_segment: str = "GLOBAL_AVG",
    horizontal_band: str = "DELTA",
    symptom_set_index: int = 1,
) -> AnalysisPackage:
    """Build full statistical package for vertical or horizontal analysis."""
    frames = _load_section_frames(csv_files)
    digest_parts: list[str] = []

    for section in CSWL_SECTION_ORDER:
        if section not in frames:
            continue
        text = compute_subsection_bandwise_metrics(
            frames[section],
            "Subsection",
            "Band",
            "T1 Z",
            "T2 Z",
            "Normalize",
        )
        digest_parts.append(f"\n\n=== {section} ===\n\n{text}")

    pkg = AnalysisPackage(
        mode=mode,
        section_frames=frames,
        metrics_digest="\n".join(digest_parts).strip(),
    )

    # Horizontal = clinical EC vs EO (KwikEDART). Vertical = NeuroTrack timeline.
    if mode == "horizontal":
        pkg.vertical_subsection_stats = build_vertical_subsection_stats(csv_files)
        pkg.vertical_channel_tables = build_vertical_summary_tables(csv_files)
        try:
            from interpretation_diagnostics import compute_eeg_interpretation_diagnostics

            pkg.clinical_diagnostics = compute_eeg_interpretation_diagnostics(csv_files)
        except Exception:
            pkg.clinical_diagnostics = {}
        pkg.compact_diagnostics = _format_clinical_compact(
            pkg.vertical_subsection_stats, set1_label, set2_label
        )
    else:
        primary = frames.get("Z Scored FFT Absolute Power")
        if primary is None or primary.empty:
            raise ValueError("Absolute Power section required for vertical (NeuroTrack) analysis")
        pkg.timeline_sets = csv_to_timeline_sets(primary, set1_label, set2_label)
        pkg.horizontal_matrix = build_horizontal_matrix(
            pkg.timeline_sets,
            selected_segment=horizontal_segment,
            selected_band=horizontal_band,
        )
        pkg.neurotrack_table_rows = build_neurotrack_table_rows(
            pkg.timeline_sets,
            selected_segment=horizontal_segment,
            selected_band=horizontal_band,
            expand_global=True,
        )
        idx = min(max(symptom_set_index, 1), len(pkg.timeline_sets)) - 1
        pkg.symptom_results = run_symptom_engine(pkg.timeline_sets[idx])
        pkg.compact_diagnostics = _format_neurotrack_compact(
            pkg.horizontal_matrix, pkg.symptom_results, set1_label, set2_label
        )

    return pkg


def _format_clinical_compact(
    stats_df: pd.DataFrame, set1_label: str, set2_label: str
) -> str:
    if stats_df.empty:
        return "No clinical comparison statistics available."
    lines = [
        f"=== HORIZONTAL CLINICAL ANALYSIS ({set1_label} vs {set2_label}) ===",
    ]
    top = stats_df.sort_values("pct_change", ascending=False).head(12)
    for _, r in top.iterrows():
        lines.append(
            f"- [{r['section']}] {r['subsection']} / {r['band']}: "
            f"{set1_label}={r['set1_mean_abs']}, {set2_label}={r['set2_mean_abs']}, "
            f"%Δ={r['pct_change']}%, abnormal% EC={r['abnormal_set1_pct']}, EO={r['abnormal_set2_pct']}"
        )
    return "\n".join(lines)


def _format_vertical_compact(stats_df: pd.DataFrame) -> str:
    if stats_df.empty:
        return "No vertical subsection statistics available."
    lines = ["=== VERTICAL ANALYSIS (Set 1 vs Set 2) ==="]
    top = stats_df.sort_values("pct_change", ascending=False).head(12)
    for _, r in top.iterrows():
        lines.append(
            f"- [{r['section']}] {r['subsection']} / {r['band']}: "
            f"Set1={r['set1_mean_abs']}, Set2={r['set2_mean_abs']}, "
            f"%Δ={r['pct_change']}%, abnormal% S1={r['abnormal_set1_pct']}, S2={r['abnormal_set2_pct']}"
        )
    return "\n".join(lines)


def _format_neurotrack_compact(
    matrix: pd.DataFrame,
    symptoms: list[dict[str, Any]],
    set1_label: str = "Set 1",
    set2_label: str = "Set 2",
) -> str:
    lines = [f"=== VERTICAL NEUROTRACK ({set1_label} → {set2_label}) ==="]
    if not matrix.empty:
        for _, r in matrix.head(15).iterrows():
            set_vals = ", ".join(
                f"S{i+1}={r.get(f'set_{i+1}')}"
                for i in range(2)
                if f"set_{i+1}" in r
            )
            lines.append(
                f"- {r.get('label')}: {set_vals}, mean={r.get('mean')}, "
                f"SD={r.get('sd')}, %abnormal={r.get('abnormal_rate_pct')}"
            )
    for s in symptoms[:5]:
        lines.append(f"- Symptom: {s['name']} severity {s['score']}/10")
    return "\n".join(lines)
