"""
CSWL pair → section CSVs → combined DOCX (shared by FastAPI and Streamlit).

Streamlit can import this module alone; report builders are loaded lazily to avoid
import cycles with api.py.
"""

from __future__ import annotations

import glob
import re
import shutil
import tempfile
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

MAX_CSWL_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB


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
        if len(values) < 10:
            continue
        rows.append({"label": label, "values": values})
    if not rows:
        raise ValueError("No valid CSWL rows found in uploaded file")
    return rows


def _infer_subsection(label: str) -> str:
    label_l = label.lower()
    if "left" in label_l:
        return "LEFT"
    if "right" in label_l:
        return "RIGHT"
    return "CENTER"


def _band_averages(values: list[float]) -> dict[str, float]:
    spectrum = values[1:31] if len(values) >= 31 else values[:30]
    if len(spectrum) < 30:
        spectrum = (spectrum + [spectrum[-1]] * (30 - len(spectrum))) if spectrum else [0.0] * 30

    def mean_range(start: int, end: int) -> float:
        window = spectrum[start - 1 : end]
        return float(np.mean(np.abs(window))) if window else 0.0

    return {
        "DELTA": mean_range(1, 4),
        "THETA": mean_range(4, 8),
        "ALPHA": mean_range(8, 12),
        "BETA": mean_range(12, 25),
        "HIGH BETA": mean_range(25, 30),
        "BETA 1": mean_range(12, 15),
        "BETA 2": mean_range(15, 18),
        "BETA 3": mean_range(18, 25),
    }


def _normalize_label(t1: float, t2: float) -> str:
    dz = abs(t1 - t2)
    if abs(dz) < 0.2 * max(abs(t1), 1e-9):
        return "NS"
    return "Yes" if t2 < t1 else "No"


def build_cswl_section_frames(file1: Path, file2: Path) -> dict[str, pd.DataFrame]:
    rows_1 = read_cswl_rows(file1)
    rows_2 = read_cswl_rows(file2)
    n = min(len(rows_1), len(rows_2))
    if n == 0:
        raise ValueError("CSWL files do not contain comparable rows")

    abs_rows = []
    ratio_rows = []
    peak_rows = []
    ratio_pairs = [
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
    peak_band_windows = {
        "DELTA": (1, 4),
        "THETA": (4, 8),
        "ALPHA": (8, 12),
        "BETA": (12, 25),
        "HIGH BETA": (25, 30),
    }

    for i in range(n):
        r1 = rows_1[i]
        r2 = rows_2[i]
        subsection = _infer_subsection(r1["label"])
        bands_1 = _band_averages(r1["values"])
        bands_2 = _band_averages(r2["values"])

        for band, t1 in bands_1.items():
            t2 = bands_2[band]
            abs_rows.append(
                {
                    "Subsection": subsection,
                    "Channel": r1["label"],
                    "Band": band,
                    "T1 Z": abs(t1),
                    "T2 Z": abs(t2),
                    "DZ": abs(abs(t1) - abs(t2)),
                    "Normalize": _normalize_label(abs(t1), abs(t2)),
                }
            )

        for ratio_name, num_band, den_band in ratio_pairs:
            t1 = bands_1[num_band] / max(abs(bands_1[den_band]), 1e-9)
            t2 = bands_2[num_band] / max(abs(bands_2[den_band]), 1e-9)
            ratio_rows.append(
                {
                    "Subsection": subsection,
                    "Channel": r1["label"],
                    "Band": ratio_name,
                    "T1 Z": abs(t1),
                    "T2 Z": abs(t2),
                    "DZ": abs(abs(t1) - abs(t2)),
                    "Normalize": _normalize_label(abs(t1), abs(t2)),
                }
            )

        spec_1 = r1["values"][1:31] if len(r1["values"]) >= 31 else r1["values"][:30]
        spec_2 = r2["values"][1:31] if len(r2["values"]) >= 31 else r2["values"][:30]
        if len(spec_1) < 30:
            spec_1 = (spec_1 + [spec_1[-1]] * (30 - len(spec_1))) if spec_1 else [0.0] * 30
        if len(spec_2) < 30:
            spec_2 = (spec_2 + [spec_2[-1]] * (30 - len(spec_2))) if spec_2 else [0.0] * 30

        for band, (start, end) in peak_band_windows.items():
            win1 = np.abs(np.array(spec_1[start - 1 : end]))
            win2 = np.abs(np.array(spec_2[start - 1 : end]))
            t1 = float(start + int(np.argmax(win1)))
            t2 = float(start + int(np.argmax(win2)))
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


def process_cswl_pair_to_output_dir(cswl1: Path, cswl2: Path, output_dir: Path) -> Path:
    """Write section CSVs and `eeg_analysis_summary.docx` under output_dir. Returns docx path."""
    from api import apply_all_calculations, create_combined_document

    output_dir.mkdir(parents=True, exist_ok=True)
    section_frames = build_cswl_section_frames(cswl1, cswl2)
    for section_name, df in section_frames.items():
        section_csv_path = output_dir / f"{section_name}.csv"
        df.to_csv(section_csv_path, index=False)
        apply_all_calculations(str(section_csv_path), section_name)
    doc_output_path = output_dir / "eeg_analysis_summary.docx"
    create_combined_document(
        glob.glob(str(output_dir / "*.csv")),
        str(doc_output_path),
    )
    return doc_output_path


def generate_cswl_docx_bytes(cswl1: Path, cswl2: Path) -> bytes:
    """Build DOCX in a temp directory and return file bytes (for Streamlit, no HTTP/S3)."""
    tmp = Path(tempfile.mkdtemp(prefix="cswl_"))
    try:
        doc_path = process_cswl_pair_to_output_dir(cswl1, cswl2, tmp)
        return doc_path.read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
