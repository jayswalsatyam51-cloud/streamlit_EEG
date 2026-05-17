"""Regression tests for CSWL parsing and band-wise metrics."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cswl_pipeline import (  # noqa: E402
    _band_averages,
    _band_averages_from_spectrum,
    _extract_spectrum,
    _normalize_label,
    _pair_cswl_rows,
    _peak_frequency_hz,
    build_cswl_section_frames,
    detect_cswl_format,
    read_cswl_rows,
)
from metrics_core import compute_subsection_bandwise_metrics  # noqa: E402

SAMPLE_DIR = ROOT / "sample file cswl"
EC = SAMPLE_DIR / "EC.D1.cswl"
EO = SAMPLE_DIR / "EO.D1.cswl"


def _montage_line(channel: str, bands: list[float]) -> str:
    return f"{channel}\tRegion\t0\t0\t0\t" + "\t".join(str(v) for v in bands)


class TestCswlCalculations(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not EC.is_file() or not EO.is_file():
            raise unittest.SkipTest("Sample CSWL files not found")

    def test_loreta_format_detected(self) -> None:
        rows = read_cswl_rows(EC)
        self.assertEqual(detect_cswl_format(rows), "loreta_spectrum")

    def test_row_counts_and_label_alignment(self) -> None:
        r1, r2 = read_cswl_rows(EC), read_cswl_rows(EO)
        self.assertEqual(len(r1), 128)
        self.assertEqual(len(r2), 128)
        pairs = _pair_cswl_rows(r1, r2)
        self.assertEqual(len(pairs), 128)

    def test_band_average_delta_bins(self) -> None:
        rows = read_cswl_rows(EC)
        spec = _extract_spectrum(rows[0]["values"])
        expected_delta = float(np.mean(np.abs(spec[0:3])))
        bands = _band_averages(rows[0]["values"])
        self.assertAlmostEqual(bands["DELTA"], expected_delta, places=5)

    def test_peak_frequency_uses_hz_scale(self) -> None:
        spec = np.zeros(30)
        spec[5] = 10.0  # 7 Hz bin (2 + 5)
        hz = _peak_frequency_hz(spec, 4, 8)
        self.assertEqual(hz, 7.0)

    def test_normalize_rules(self) -> None:
        self.assertEqual(_normalize_label(1.0, 1.15), "NS")
        self.assertEqual(_normalize_label(2.0, 1.0), "Yes")
        self.assertEqual(_normalize_label(1.0, 2.0), "No")

    def test_metrics_match_dataframe(self) -> None:
        frames, fmt = build_cswl_section_frames(EC, EO)
        self.assertEqual(fmt, "loreta_spectrum")
        df = frames["Z Scored FFT Absolute Power"]
        left_delta = df[(df["Subsection"] == "LEFT") & (df["Band"] == "DELTA")]
        t1_sum = float(left_delta["T1 Z"].abs().sum())
        t1_avg = float(left_delta["T1 Z"].abs().mean())
        t2_avg = float(left_delta["T2 Z"].abs().mean())
        delta = abs(t1_avg - t2_avg)
        pct = (delta / t1_avg) * 100 if t1_avg else 0.0

        metrics = compute_subsection_bandwise_metrics(
            df, "Subsection", "Band", "T1 Z", "T2 Z", "Normalize"
        )
        self.assertIn(f"Absolute Sum: {t1_sum:.2f}", metrics)
        self.assertIn(f"Average Absolute Value: {t1_avg:.3f}", metrics)
        self.assertIn(f"Percent Change: {pct:.2f}%", metrics)

    def test_pairing_mismatch_raises(self) -> None:
        r1 = read_cswl_rows(EC)
        r2 = read_cswl_rows(EO)
        r2[-1] = {**r2[-1], "label": "bogus-region"}
        with self.assertRaises(ValueError):
            _pair_cswl_rows(r1, r2)

    def test_montage_format_matches_pdf_style_channels(self) -> None:
        bands1 = [0.03, -0.22, 0.67, -0.19, -0.82, 0.29, -0.25, -0.43]
        bands2 = [0.86, 0.61, 0.51, 0.76, 1.17, 0.79, 0.58, 0.79]
        left_channels = ["FP1 - LE", "F3 - LE", "C3 - LE", "P3 - LE", "O1 - LE", "F7 - LE"]
        text = "\n".join(_montage_line(ch, bands1) for ch in left_channels)
        text2 = "\n".join(
            [_montage_line("FP1 - LE", bands2)]
            + [_montage_line(ch, [v + 0.5 for v in bands1]) for ch in left_channels[1:]]
        )
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "a.cswl"
            p2 = Path(td) / "b.cswl"
            p1.write_text(text, encoding="utf-8")
            p2.write_text(text2, encoding="utf-8")
            frames, fmt = build_cswl_section_frames(p1, p2)
            self.assertEqual(fmt, "montage")
            df = frames["Z Scored FFT Absolute Power"]
            fp1 = df[(df["Channel"] == "FP1 - LE") & (df["Band"] == "DELTA")].iloc[0]
            self.assertAlmostEqual(fp1["T1 Z"], 0.03, places=3)
            self.assertAlmostEqual(fp1["T2 Z"], 0.86, places=3)
            self.assertEqual(fp1["Normalize"], "No")


if __name__ == "__main__":
    unittest.main()
