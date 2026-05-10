"""
Structured, computed diagnostics from EEG section CSVs (Set 1 vs Set 2).
Feeds the AI interpreter with verifiable summaries — similar in spirit to
session-based stats tabs (descriptive / comparative / limitations).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import pandas as pd

SECTION_ORDER = [
    "Z Scored FFT Absolute Power",
    "Z Scored FFT Power Ratio",
    "Z Scored Peak Frequency",
    "Z Scored FFT Coherence",
    "Z Scored FFT Phase Lag",
]


def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def compute_eeg_interpretation_diagnostics(csv_files: List[str]) -> Dict[str, Any]:
    """
    Build a nested dict + a compact text block for LLM prompts.
    """
    section_to_file = {os.path.basename(f).replace(".csv", ""): f for f in csv_files}

    sections: Dict[str, Any] = {}
    all_rows: List[Dict[str, Any]] = []

    for section in SECTION_ORDER:
        fp = section_to_file.get(section)
        if not fp or not os.path.exists(fp):
            continue
        df = pd.read_csv(fp)
        if df.empty:
            continue

        for c in ("Percent_Change", "Delta", "T1 Z", "T2 Z"):
            if c in df.columns:
                df[c] = _safe_num(df[c])

        n = len(df)
        mean_abs_pct = (
            df["Percent_Change"].abs().mean()
            if "Percent_Change" in df.columns
            else None
        )
        mean_abs_delta = df["Delta"].abs().mean() if "Delta" in df.columns else None

        # Direction: T2 mean vs T1 mean per row (band-level)
        t2_higher = 0
        t1_higher = 0
        if "T1 Z" in df.columns and "T2 Z" in df.columns:
            m1 = df["T1 Z"].abs()
            m2 = df["T2 Z"].abs()
            t2_higher = int((m2 > m1).sum())
            t1_higher = int((m1 > m2).sum())

        top_changes: List[Dict[str, Any]] = []
        if "Percent_Change" in df.columns and df["Percent_Change"].notna().any():
            work = df.assign(_apc=df["Percent_Change"].abs()).sort_values(
                "_apc", ascending=False
            ).head(5)
            for _, row in work.iterrows():
                top_changes.append(
                    {
                        "subsection": str(row.get("Subsection", "")),
                        "band": str(row.get("Band", "")),
                        "percent_change": float(row["Percent_Change"])
                        if pd.notna(row["Percent_Change"])
                        else None,
                        "delta": float(row["Delta"])
                        if "Delta" in df.columns and pd.notna(row.get("Delta"))
                        else None,
                    }
                )

        sections[section] = {
            "row_count": n,
            "mean_abs_percent_change": float(mean_abs_pct)
            if mean_abs_pct is not None and pd.notna(mean_abs_pct)
            else None,
            "mean_abs_delta": float(mean_abs_delta)
            if mean_abs_delta is not None and pd.notna(mean_abs_delta)
            else None,
            "rows_t2_abs_higher": t2_higher,
            "rows_t1_abs_higher": t1_higher,
            "top_percent_changes": top_changes,
        }

        for _, row in df.iterrows():
            all_rows.append(
                {
                    "section": section,
                    "subsection": str(row.get("Subsection", "")),
                    "band": str(row.get("Band", "")),
                    "percent_change": float(row["Percent_Change"])
                    if "Percent_Change" in df.columns and pd.notna(row.get("Percent_Change"))
                    else None,
                    "delta": float(row["Delta"])
                    if "Delta" in df.columns and pd.notna(row.get("Delta"))
                    else None,
                }
            )

    global_top: List[Dict[str, Any]] = []
    if all_rows:
        ranked = sorted(
            [r for r in all_rows if r.get("percent_change") is not None],
            key=lambda x: abs(x["percent_change"]),
            reverse=True,
        )[:8]
        global_top = ranked

    out: Dict[str, Any] = {
        "sections": sections,
        "global_top_percent_changes": global_top,
        "notes": [
            "Comparison is between two extracted PDFs (Set 1 vs Set 2), not longitudinal sessions.",
            "Use structured figures only; do not infer clinical diagnosis.",
        ],
    }
    out["compact_text"] = format_diagnostics_compact(out)
    return out


def format_diagnostics_compact(diag: Dict[str, Any]) -> str:
    """Single string for LLM context (verifiable numbers)."""
    lines: List[str] = []
    lines.append("=== COMPUTED DIAGNOSTICS (from CSV; use these numbers when citing) ===")
    for name, sec in diag.get("sections", {}).items():
        lines.append(f"\n[{name}]")
        lines.append(
            f"  rows={sec.get('row_count')}, "
            f"mean_abs_percent_change={sec.get('mean_abs_percent_change')}, "
            f"mean_abs_delta={sec.get('mean_abs_delta')}"
        )
        lines.append(
            f"  band-rows where |T2 Z|>|T1 Z|: {sec.get('rows_t2_abs_higher')}, "
            f"where |T1 Z|>|T2 Z|: {sec.get('rows_t1_abs_higher')}"
        )
        for i, t in enumerate(sec.get("top_percent_changes") or [], 1):
            lines.append(
                f"  top{i}: {t.get('subsection')} / {t.get('band')} — "
                f"%Δ={t.get('percent_change')}, Δ={t.get('delta')}"
            )

    lines.append("\n=== GLOBAL LARGEST |% CHANGE| (across all sections) ===")
    for i, t in enumerate(diag.get("global_top_percent_changes") or [], 1):
        lines.append(
            f"  {i}. [{t.get('section')}] {t.get('subsection')} / {t.get('band')} — "
            f"%Δ={t.get('percent_change')}"
        )
    lines.append("")
    return "\n".join(lines)
