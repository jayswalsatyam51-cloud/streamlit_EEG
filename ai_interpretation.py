"""
AI interpretation of band-wise EEG metrics using Gemini API.
Uses computed diagnostics (descriptive / comparative summaries) plus raw
metrics digest and produces multiple interpretation candidates.
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from docx import Document
from docx.shared import Pt
from dotenv import load_dotenv

from interpretation_diagnostics import compute_eeg_interpretation_diagnostics
from metrics_core import compute_subsection_bandwise_metrics

load_dotenv()

logger = logging.getLogger(__name__)

SECTION_ORDER = [
    "Z Scored FFT Absolute Power",
    "Z Scored FFT Power Ratio",
    "Z Scored Peak Frequency",
    "Z Scored FFT Coherence",
    "Z Scored FFT Phase Lag",
]

MAX_INPUT_CHARS = 28000
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={api_key}"
)


def _strip_limitations_section(text: str) -> str:
    """Remove '## Limitations and caveats' and all content after it (DOCX output)."""
    if not text:
        return text
    return re.sub(
        r"(?ms)^##\s*Limitations\s+and\s+caveats\s*\n.*",
        "",
        text,
    ).strip()


def build_metrics_digest_text(csv_files: List[str]) -> str:
    """Concatenate band-wise metrics text in the same order as the summary DOCX."""
    import os as os_mod

    section_to_file = {os_mod.path.basename(f).replace(".csv", ""): f for f in csv_files}
    parts: List[str] = []
    for section in SECTION_ORDER:
        file_path = section_to_file.get(section)
        if not file_path:
            continue
        df = pd.read_csv(file_path)
        metrics_text = compute_subsection_bandwise_metrics(
            df,
            subsection_col="Subsection",
            band_col="Band",
            set1_col="T1 Z",
            set2_col="T2 Z",
            normalize_col="Normalize",
        )
        parts.append(f"\n\n=== {section} ===\n\n{metrics_text}")
    return "\n".join(parts).strip()


def _build_prompt(metrics_digest: str, diagnostics_compact: str) -> str:
    combined = f"{diagnostics_compact}\n\n--- RAW METRICS (band-wise) ---\n\n{metrics_digest}"
    content = combined[:MAX_INPUT_CHARS]
    if len(combined) > MAX_INPUT_CHARS:
        content += "\n\n[Note: Input was truncated for model context limits.]"

    return (
        "You are assisting with EEG band-wise metrics comparison (Set 1 vs Set 2) from automated PDF extraction.\n\n"
        "You are given:\n"
        "1) COMPUTED DIAGNOSTICS — pre-aggregated counts and top changes (trust these numbers when citing).\n"
        "2) RAW METRICS — detailed band/subsection text from the pipeline.\n\n"
        "Write multiple possible interpretations grounded in the provided data.\n"
        "This is not diagnosis. Use cautious language and cite explicit quantitative cues.\n\n"
        "For EACH interpretation candidate, use EXACT headings in order:\n"
        "## Executive Summary\n"
        "## Descriptive overview by EEG section\n"
        "## Set 1 vs Set 2 — comparative highlights\n"
        "## Cross-section patterns\n\n"
        "Rules:\n"
        "- Prefer numbers from COMPUTED DIAGNOSTICS for largest changes/direction counts.\n"
        "- Do not invent values absent from data.\n"
        "- Keep each candidate concise and clinically readable.\n\n"
        "--- DATA ---\n\n"
        f"{content}"
    )


def _extract_candidate_texts(payload: Dict[str, Any]) -> List[str]:
    candidates = payload.get("candidates") or []
    out: List[str] = []
    for c in candidates:
        parts = ((c.get("content") or {}).get("parts") or [])
        text = "\n".join([(p.get("text") or "").strip() for p in parts]).strip()
        if text:
            out.append(text)
    return out


def _invoke_gemini_interpretations(
    metrics_digest: str,
    diagnostics_compact: str,
    candidate_count: int = 4,
) -> List[str]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment")

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    prompt = _build_prompt(metrics_digest, diagnostics_compact)
    url = GEMINI_ENDPOINT.format(model=model, api_key=api_key)

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.8,
            "topP": 0.95,
            "candidateCount": candidate_count,
        },
    }
    resp = requests.post(url, json=body, timeout=90)
    if not resp.ok:
        # Retry without candidateCount for compatibility across model variants.
        fallback = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "topP": 0.95},
        }
        resp = requests.post(url, json=fallback, timeout=90)
    if not resp.ok:
        raise ValueError(f"Gemini API error: {resp.status_code} {resp.text[:300]}")

    texts = _extract_candidate_texts(resp.json())
    if not texts:
        raise ValueError("Gemini API returned no interpretation text")
    return texts


def _build_rule_based_interpretation(diag: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("## Executive Summary")
    lines.append(
        "This is an automated, non-diagnostic interpretation based on extracted EEG metrics and should be clinically reviewed."
    )
    lines.append("")
    lines.append("## Descriptive overview by EEG section")
    for sec, data in (diag.get("sections") or {}).items():
        lines.append(
            f"- {sec}: rows={data.get('row_count')}, mean_abs_percent_change={data.get('mean_abs_percent_change')}, "
            f"mean_abs_delta={data.get('mean_abs_delta')}."
        )
    lines.append("")
    lines.append("## Set 1 vs Set 2 — comparative highlights")
    for sec, data in (diag.get("sections") or {}).items():
        lines.append(
            f"- {sec}: |T2 Z|>|T1 Z| in {data.get('rows_t2_abs_higher')} rows; "
            f"|T1 Z|>|T2 Z| in {data.get('rows_t1_abs_higher')} rows."
        )
    lines.append("")
    lines.append("## Cross-section patterns")
    top = diag.get("global_top_percent_changes") or []
    if top:
        for t in top[:5]:
            lines.append(
                f"- [{t.get('section')}] {t.get('subsection')} / {t.get('band')} shows % change {t.get('percent_change')}."
            )
    else:
        lines.append("- No global top-change entries were available.")
    return "\n".join(lines)


def _write_interpretation_docx(path: str, texts: List[str], diag: Dict[str, Any]) -> None:
    """Render multiple interpretation candidates into Word headings/paragraphs."""
    doc = Document()
    title_para = doc.add_paragraph()
    run = title_para.add_run("EEG//")
    run.bold = True
    run.font.size = Pt(18)
    doc.add_heading("AI Interpretation — Structured analytics", level=1)
    disclaimer = doc.add_paragraph()
    d_run = disclaimer.add_run(
        "Generated from extracted metrics and computed summaries."
    )
    d_run.italic = True
    doc.add_paragraph()

    doc.add_heading("Computed Diagnostics Snapshot", level=2)
    for sec, data in (diag.get("sections") or {}).items():
        doc.add_paragraph(
            f"{sec}: rows={data.get('row_count')}, mean_abs_percent_change={data.get('mean_abs_percent_change')}, "
            f"mean_abs_delta={data.get('mean_abs_delta')}"
        )

    for i, text in enumerate(texts, start=1):
        doc.add_paragraph()
        doc.add_heading(f"Interpretation Candidate {i}", level=2)
        lines = text.split("\n")
        for line in lines:
            line = line.rstrip()
            if not line.strip():
                continue
            h3 = re.match(r"^###\s+(.+)$", line)
            h2 = re.match(r"^##\s+(.+)$", line)
            h1 = re.match(r"^#\s+(.+)$", line)
            if h1:
                doc.add_heading(h1.group(1).strip(), level=1)
            elif h2:
                doc.add_heading(h2.group(1).strip(), level=3)
            elif h3:
                doc.add_heading(h3.group(1).strip(), level=4)
            else:
                body = re.sub(r"^[-*]\s+", "", line)
                doc.add_paragraph(body)

    doc.save(path)


def generate_ai_interpretation_docx(
    output_path: str,
    csv_files: List[str],
    diagnostics_json_path: Optional[str] = None,
) -> None:
    """Build digest + diagnostics, call Gemini, write interpretation DOCX."""
    digest = build_metrics_digest_text(csv_files)
    if not digest:
        raise ValueError("No metrics data available for AI interpretation")

    diag = compute_eeg_interpretation_diagnostics(csv_files)
    if diagnostics_json_path:
        payload = {k: v for k, v in diag.items() if k != "compact_text"}
        with open(diagnostics_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)

    interpretations = _invoke_gemini_interpretations(
        digest, diag.get("compact_text", ""), candidate_count=4
    )
    interpretations = [_strip_limitations_section(t) for t in interpretations]
    # Add a deterministic, rule-based variant too.
    interpretations.append(_build_rule_based_interpretation(diag))
    _write_interpretation_docx(output_path, interpretations, diag)


def try_generate_ai_interpretation_docx(
    output_path: str,
    csv_files: List[str],
    diagnostics_json_path: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Returns (success, error_message). Does not raise on missing API key or LLM errors.
    """
    if not os.getenv("GEMINI_API_KEY"):
        return False, "GEMINI_API_KEY not set; skipping AI interpretation"
    try:
        generate_ai_interpretation_docx(
            output_path, csv_files, diagnostics_json_path=diagnostics_json_path
        )
        return True, None
    except Exception as e:
        logger.exception("AI interpretation failed")
        return False, str(e)
