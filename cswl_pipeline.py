"""
CSWL pair → section CSVs → combined DOCX (shared by FastAPI and Streamlit).

Supports:
  - loreta_spectrum: LORETA / regional rows with 2–31 Hz z-score bins (e.g. EC.D1.cswl)
  - montage: LinkEars-style rows (FP1 - LE, F3 - LE, …) with band z-scores in file
"""

from __future__ import annotations

import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

MAX_CSWL_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB

CswlFormat = Literal["montage", "loreta_spectrum"]

# 2–31 Hz inclusive, one bin per Hz (30 bins). values[0] in file = bin for 2 Hz.
SPECTRUM_BINS = 30
SPECTRUM_START_HZ = 2

ABS_BANDS = [
    "DELTA",
    "THETA",
    "ALPHA",
    "BETA",
    "HIGH BETA",
    "BETA 1",
    "BETA 2",
    "BETA 3",
]

RATIO_BANDS = [
    ("D/T", "DELTA", "THETA"),
    ("D/A", "DELTA", "ALPHA"),
    ("D/B", "DELTA", "BETA"),
    ("D/G", "DELTA", "HIGH BETA"),
    ("T/A", "THETA", "ALPHA"),
    ("T/B", "THETA", "BETA"),
    ("T/G", "THETA", "HIGH BETA"),
    ("A/B", "ALPHA", "BETA"),
    ("A/G", "ALPHA", "HIGH BETA"),
    ("B/G", "BETA", "HIGH BETA"),
]

PEAK_BAND_WINDOWS = {
    "DELTA": (2, 4),
    "THETA": (4, 8),
    "ALPHA": (8, 12),
    "BETA": (12, 25),
    "HIGH BETA": (25, 31),
}

LEFT_CHANNELS = [
    "FP1 - LE",
    "F3 - LE",
    "C3 - LE",
    "P3 - LE",
    "O1 - LE",
    "F7 - LE",
    "T3 - LE",
    "T5 - LE",
]
RIGHT_CHANNELS = [
    "FP2 - LE",
    "F4 - LE",
    "C4 - LE",
    "P4 - LE",
    "O2 - LE",
    "F8 - LE",
    "T4 - LE",
    "T6 - LE",
]
CENTER_CHANNELS = ["Fz - LE", "Cz - LE", "Pz - LE"]

MONTAGE_LABEL_RE = re.compile(
    r"^(FP1|FP2|F[3-8]|C[3-4]|P[3-4]|O[1-2]|T[3-6]|Fz|Cz|Pz)\s*-\s*LE\s*$",
    re.IGNORECASE,
)


def secure_cswl_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._\- ]", "_", Path(name or "").name)
    return cleaned or f"upload_{uuid.uuid4().hex[:8]}.cswl"


def read_cswl_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 12:
            continue
        label = parts[0]
        values = []
        for token in parts[5:]:
            try:
                values.append(float(token))
            except ValueError:
                continue
        if len(values) < 8:
            continue
        rows.append({"label": label, "values": values})
    if not rows:
        raise ValueError("No valid CSWL rows found in uploaded file")
    return rows


def detect_cswl_format(rows: list[dict]) -> CswlFormat:
    """Classify file as montage (10–20) or LORETA regional spectrum."""
    montage_hits = sum(
        1 for r in rows if MONTAGE_LABEL_RE.match(r["label"].strip())
    )
    if montage_hits >= 3:
        return "montage"
    return "loreta_spectrum"


def _infer_subsection_montage(label: str) -> str:
    label = label.strip()
    if label in LEFT_CHANNELS:
        return "LEFT"
    if label in RIGHT_CHANNELS:
        return "RIGHT"
    if label in CENTER_CHANNELS:
        return "CENTER"
    label_l = label.lower()
    if "left" in label_l:
        return "LEFT"
    if "right" in label_l:
        return "RIGHT"
    return "CENTER"


def _infer_subsection_loreta(label: str) -> str:
    label_l = label.lower()
    if re.search(r"\bleft\b", label_l):
        return "LEFT"
    if re.search(r"\bright\b", label_l):
        return "RIGHT"
    return "CENTER"


def _normalize_montage_label(label: str) -> str:
    """Normalize 'fp1 - le' → 'FP1 - LE' for channel lists."""
    m = MONTAGE_LABEL_RE.match(label.strip())
    if not m:
        return label.strip()
    ch = m.group(1)
    if ch.lower() in ("fz", "cz", "pz"):
        ch = ch[0].upper() + ch[1:].lower()
    else:
        ch = ch.upper()
    return f"{ch} - LE"


def _extract_spectrum(values: list[float]) -> np.ndarray:
    """
    30 z-score bins for 2–31 Hz.
    When 31+ numbers are present, values[0] is treated as 1 Hz / total and skipped.
    """
    if len(values) >= SPECTRUM_BINS + 1:
        spec = np.array(values[1 : SPECTRUM_BINS + 1], dtype=float)
    else:
        spec = np.array(values[:SPECTRUM_BINS], dtype=float)
    if spec.size < SPECTRUM_BINS:
        spec = np.pad(spec, (0, SPECTRUM_BINS - spec.size), mode="edge")
    return spec[:SPECTRUM_BINS]


def _band_averages_from_spectrum(spec: np.ndarray) -> dict[str, float]:
    """Map 2–31 Hz bins to clinical bands (same windows as PDF QEEG reports)."""

    def mean_range(hz_start: int, hz_end: int) -> float:
        i0 = hz_start - SPECTRUM_START_HZ
        i1 = hz_end - SPECTRUM_START_HZ + 1
        window = spec[i0:i1]
        return float(np.mean(np.abs(window))) if window.size else 0.0

    return {
        "DELTA": mean_range(2, 4),
        "THETA": mean_range(4, 8),
        "ALPHA": mean_range(8, 12),
        "BETA": mean_range(12, 25),
        "HIGH BETA": mean_range(25, 31),
        "BETA 1": mean_range(12, 15),
        "BETA 2": mean_range(15, 18),
        "BETA 3": mean_range(18, 25),
    }


def _band_averages_montage(values: list[float]) -> dict[str, float]:
    """Read eight band z-scores directly from the export (PDF-equivalent)."""
    if len(values) < len(ABS_BANDS):
        raise ValueError("Montage CSWL row has fewer than 8 band values")
    return {band: float(values[i]) for i, band in enumerate(ABS_BANDS)}


def _peak_frequency_hz(spec: np.ndarray, hz_start: int, hz_end: int) -> float:
    i0 = hz_start - SPECTRUM_START_HZ
    i1 = hz_end - SPECTRUM_START_HZ + 1
    window = np.abs(spec[i0:i1])
    if window.size == 0:
        return float(hz_start)
    return float(SPECTRUM_START_HZ + i0 + int(np.argmax(window)))


def _normalize_label(t1: float, t2: float) -> str:
    dz = abs(t1 - t2)
    if abs(dz) < 0.2 * max(abs(t1), 1e-9):
        return "NS"
    return "Yes" if t2 < t1 else "No"


def _append_metric_rows(
    rows: list[dict],
    subsection: str,
    channel: str,
    bands_1: dict[str, float],
    bands_2: dict[str, float],
    *,
    use_abs: bool = True,
) -> None:
    for band in ABS_BANDS:
        t1 = bands_1[band]
        t2 = bands_2[band]
        if use_abs:
            t1, t2 = abs(t1), abs(t2)
        rows.append(
            {
                "Subsection": subsection,
                "Channel": channel,
                "Band": band,
                "T1 Z": t1,
                "T2 Z": t2,
                "DZ": abs(t1 - t2),
                "Normalize": _normalize_label(t1, t2),
            }
        )


def _append_ratio_rows(
    ratio_rows: list[dict],
    subsection: str,
    channel: str,
    bands_1: dict[str, float],
    bands_2: dict[str, float],
) -> None:
    for ratio_name, num_band, den_band in RATIO_BANDS:
        t1 = bands_1[num_band] / max(abs(bands_1[den_band]), 1e-9)
        t2 = bands_2[num_band] / max(abs(bands_2[den_band]), 1e-9)
        t1, t2 = abs(t1), abs(t2)
        ratio_rows.append(
            {
                "Subsection": subsection,
                "Channel": channel,
                "Band": ratio_name,
                "T1 Z": t1,
                "T2 Z": t2,
                "DZ": abs(t1 - t2),
                "Normalize": _normalize_label(t1, t2),
            }
        )


def _pair_cswl_rows(rows_1: list[dict], rows_2: list[dict]) -> list[tuple[dict, dict]]:
    """Match regions/channels by label (Set 1 / Set 2)."""
    index_2 = {r["label"]: r for r in rows_2}
    pairs: list[tuple[dict, dict]] = []
    missing_in_2: list[str] = []

    for r1 in rows_1:
        r2 = index_2.get(r1["label"])
        if r2 is None:
            missing_in_2.append(r1["label"])
        else:
            pairs.append((r1, r2))

    if missing_in_2:
        sample = ", ".join(missing_in_2[:3])
        raise ValueError(
            f"Set 2 file is missing {len(missing_in_2)} row(s) present in Set 1 "
            f"(e.g. {sample})"
        )

    labels_1 = {r["label"] for r in rows_1}
    extra_in_2 = [label for label in index_2 if label not in labels_1]
    if extra_in_2:
        sample = ", ".join(extra_in_2[:3])
        raise ValueError(
            f"Set 2 file has {len(extra_in_2)} row(s) not in Set 1 (e.g. {sample})"
        )

    if not pairs:
        raise ValueError("CSWL files do not contain comparable rows")

    return pairs


def _build_montage_frames(
    paired_rows: list[tuple[dict, dict]],
) -> dict[str, pd.DataFrame]:
    abs_rows: list[dict] = []
    ratio_rows: list[dict] = []
    peak_rows: list[dict] = []

    for r1, r2 in paired_rows:
        label = _normalize_montage_label(r1["label"])
        subsection = _infer_subsection_montage(label)
        bands_1 = _band_averages_montage(r1["values"])
        bands_2 = _band_averages_montage(r2["values"])

        _append_metric_rows(abs_rows, subsection, label, bands_1, bands_2)
        _append_ratio_rows(ratio_rows, subsection, label, bands_1, bands_2)

        if len(r1["values"]) >= SPECTRUM_BINS + 1:
            spec_1 = _extract_spectrum(r1["values"])
            spec_2 = _extract_spectrum(r2["values"])
            for band, (hz_start, hz_end) in PEAK_BAND_WINDOWS.items():
                t1 = _peak_frequency_hz(spec_1, hz_start, hz_end)
                t2 = _peak_frequency_hz(spec_2, hz_start, hz_end)
                peak_rows.append(
                    {
                        "Subsection": subsection,
                        "Channel": label,
                        "Band": band,
                        "T1 Z": t1,
                        "T2 Z": t2,
                        "DZ": abs(t1 - t2),
                        "Normalize": _normalize_label(t1, t2),
                    }
                )

    frames = {
        "Z Scored FFT Absolute Power": pd.DataFrame(abs_rows),
        "Z Scored FFT Power Ratio": pd.DataFrame(ratio_rows),
    }
    if peak_rows:
        frames["Z Scored Peak Frequency"] = pd.DataFrame(peak_rows)
    return frames


def _build_loreta_frames(
    paired_rows: list[tuple[dict, dict]],
) -> dict[str, pd.DataFrame]:
    abs_rows: list[dict] = []
    ratio_rows: list[dict] = []
    peak_rows: list[dict] = []

    for r1, r2 in paired_rows:
        subsection = _infer_subsection_loreta(r1["label"])
        spec_1 = _extract_spectrum(r1["values"])
        spec_2 = _extract_spectrum(r2["values"])
        bands_1 = _band_averages_from_spectrum(spec_1)
        bands_2 = _band_averages_from_spectrum(spec_2)

        _append_metric_rows(abs_rows, subsection, r1["label"], bands_1, bands_2)
        _append_ratio_rows(ratio_rows, subsection, r1["label"], bands_1, bands_2)

        for band, (hz_start, hz_end) in PEAK_BAND_WINDOWS.items():
            t1 = _peak_frequency_hz(spec_1, hz_start, hz_end)
            t2 = _peak_frequency_hz(spec_2, hz_start, hz_end)
            peak_rows.append(
                {
                    "Subsection": subsection,
                    "Channel": r1["label"],
                    "Band": band,
                    "T1 Z": t1,
                    "T2 Z": t2,
                    "DZ": abs(t1 - t2),
                    "Normalize": _normalize_label(t1, t2),
                }
            )

    return {
        "Z Scored FFT Absolute Power": pd.DataFrame(abs_rows),
        "Z Scored FFT Power Ratio": pd.DataFrame(ratio_rows),
        "Z Scored Peak Frequency": pd.DataFrame(peak_rows),
    }


def build_cswl_section_frames(
    file1: Path, file2: Path
) -> tuple[dict[str, pd.DataFrame], CswlFormat]:
    rows_1 = read_cswl_rows(file1)
    rows_2 = read_cswl_rows(file2)
    fmt1 = detect_cswl_format(rows_1)
    fmt2 = detect_cswl_format(rows_2)
    if fmt1 != fmt2:
        raise ValueError(
            f"CSWL format mismatch: Set 1 is {fmt1!r}, Set 2 is {fmt2!r}. "
            "Upload two files of the same type (both montage or both LORETA)."
        )
    paired_rows = _pair_cswl_rows(rows_1, rows_2)
    if fmt1 == "montage":
        return _build_montage_frames(paired_rows), fmt1
    return _build_loreta_frames(paired_rows), fmt1


def process_cswl_pair_to_output_dir(
    cswl1: Path, cswl2: Path, output_dir: Path
) -> tuple[Path, CswlFormat]:
    """Write section CSVs and `eeg_analysis_summary.docx`. Returns (docx path, format)."""
    from report_builder import create_combined_document

    output_dir.mkdir(parents=True, exist_ok=True)
    section_frames, fmt = build_cswl_section_frames(cswl1, cswl2)
    csv_paths: list[str] = []
    for section_name, df in section_frames.items():
        section_csv_path = output_dir / f"{section_name}.csv"
        df.to_csv(section_csv_path, index=False)
        csv_paths.append(str(section_csv_path))
    doc_output_path = output_dir / "eeg_analysis_summary.docx"
    create_combined_document(csv_paths, str(doc_output_path))
    return doc_output_path, fmt


def _band_averages(values: list[float]) -> dict[str, float]:
    """LORETA spectrum → bands (used by tests and internal callers)."""
    return _band_averages_from_spectrum(_extract_spectrum(values))


def generate_cswl_docx_bytes(cswl1: Path, cswl2: Path) -> tuple[bytes, CswlFormat]:
    """Build DOCX in a temp directory; return bytes and detected format."""
    tmp = Path(tempfile.mkdtemp(prefix="cswl_"))
    try:
        doc_path, fmt = process_cswl_pair_to_output_dir(cswl1, cswl2, tmp)
        return doc_path.read_bytes(), fmt
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
