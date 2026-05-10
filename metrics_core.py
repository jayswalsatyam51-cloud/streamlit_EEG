"""
Shared band-wise metrics computation used by API reports and AI interpretation.
"""
import numpy as np
import pandas as pd


def compute_subsection_bandwise_metrics(
    df: pd.DataFrame,
    subsection_col: str,
    band_col: str,
    set1_col: str,
    set2_col: str,
    normalize_col: str,
) -> str:
    """Compute metrics for each subsection and band."""
    subsections = df[subsection_col].dropna().unique()
    result_blocks = []

    df[set1_col] = pd.to_numeric(df[set1_col], errors="coerce")
    df[set2_col] = pd.to_numeric(df[set2_col], errors="coerce")

    for subsection in subsections:
        subsection_df = df[df[subsection_col] == subsection]
        bands = subsection_df[band_col].dropna().unique()

        result_blocks.append(f"\n Subsection: {subsection} \n")

        for band in bands:
            band_df = subsection_df[subsection_df[band_col] == band][
                [set1_col, set2_col, normalize_col]
            ].dropna()

            if band_df.empty:
                continue

            abs_sum_1 = np.abs(band_df[set1_col]).sum()
            abs_avg_1 = np.abs(band_df[set1_col]).mean()
            abs_sum_2 = np.abs(band_df[set2_col]).sum()
            abs_avg_2 = np.abs(band_df[set2_col]).mean()

            delta = abs(abs_avg_1 - abs_avg_2)
            percent_change = (delta / abs_avg_1) * 100 if abs_avg_1 != 0 else 0
            direction = "increase" if abs_avg_2 > abs_avg_1 else "decrease"

            total_rows = len(band_df)
            normalize_counts = band_df[normalize_col].astype(str).value_counts()
            normalize_yes = normalize_counts.get("Yes", 0)
            normalize_no = normalize_counts.get("No", 0)
            normalize_ns = normalize_counts.get("NS", 0)

            block = f""" Band: {band}
Set 1 ({set1_col}):
  Absolute Sum: {abs_sum_1:.2f}
  Average Absolute Value: {abs_avg_1:.3f}

Set 2 ({set2_col}):
  Absolute Sum: {abs_sum_2:.2f}
  Average Absolute Value: {abs_avg_2:.3f}

Differences:
  Delta: {delta:.3f}
  Percent Change: {percent_change:.2f}% ({direction} from Set 1 to Set 2)

Normalize Counts:
  Total Rows: {total_rows}
  "Normalize = Yes": {normalize_yes} ({(normalize_yes / total_rows) * 100 if total_rows > 0 else 0:.2f}%)
  "Normalize = No": {normalize_no} ({(normalize_no / total_rows) * 100 if total_rows > 0 else 0:.2f}%)
  "Normalize = NS": {normalize_ns} ({(normalize_ns / total_rows) * 100 if total_rows > 0 else 0:.2f}%)

__________________________________________________\n"""

            result_blocks.append(block)

    return "\n".join(result_blocks)
