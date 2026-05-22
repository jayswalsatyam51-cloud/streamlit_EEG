"""
Streamlit: CSWL (EC / EO) → Vertical or Horizontal QEEG analysis + Gemini report.

Run:
  streamlit run streamlit_cswl.py
"""

from __future__ import annotations

import glob
import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from ai_interpretation import write_analysis_docx
from cswl_pipeline import (
    MAX_CSWL_UPLOAD_BYTES,
    process_cswl_pair_to_output_dir,
    secure_cswl_filename,
)
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
from qeeg_statistical_analysis import (
    CSWL_SECTION_ORDER,
    build_neurotrack_table_rows,
    run_statistical_analysis,
)

load_dotenv()

MAX_UPLOAD_MB = MAX_CSWL_UPLOAD_BYTES // (1024 * 1024)

PHASE_LABELS = {
    "upload": "1 · Process CSWL",
    "analysis_select": "2 · Run analysis",
    "results": "3 · Results",
}


def _init_state() -> None:
    defaults = {
        "phase": "upload",
        "work_dir": None,
        "csv_files": [],
        "docx_bytes": None,
        "cswl_format": None,
        "set1_name": "EC",
        "set2_name": "EO",
        "ec_display": "EC (Eyes Closed)",
        "eo_display": "EO (Eyes Open)",
        "analysis_pkg": None,
        "ai_report": None,
        "ai_docx_bytes": None,
        "analysis_mode": "vertical",
        "neurotrack_view": "analysis",
        "global_matrix_expanded": False,
        "chart_section": "Z Scored FFT Absolute Power",
        "chart_subsection": "LEFT",
        "chart_band": "DELTA",
        "h_opts": {
            "segment": "GLOBAL_AVG",
            "band": "DELTA",
            "symptom_set": 1,
        },
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _process_cswl(f1, f2) -> None:
    with tempfile.TemporaryDirectory(prefix="cswl_upload_") as td:
        td_path = Path(td)
        p1 = td_path / secure_cswl_filename(f1.name)
        p2 = td_path / secure_cswl_filename(f2.name)
        p1.write_bytes(f1.getvalue())
        p2.write_bytes(f2.getvalue())

        out_dir = Path(tempfile.mkdtemp(prefix="cswl_out_"))
        doc_path, fmt = process_cswl_pair_to_output_dir(p1, p2, out_dir)
        section_files = sorted(glob.glob(str(out_dir / "*.csv")))

        st.session_state.work_dir = str(out_dir)
        st.session_state.csv_files = section_files
        st.session_state.docx_bytes = doc_path.read_bytes()
        st.session_state.cswl_format = fmt
        st.session_state.set1_name = Path(f1.name).stem or "EC"
        st.session_state.set2_name = Path(f2.name).stem or "EO"
        st.session_state.ec_display = "EC (Eyes Closed)"
        st.session_state.eo_display = "EO (Eyes Open)"
        st.session_state.phase = "analysis_select"
        st.session_state.analysis_pkg = None
        st.session_state.ai_report = None
        st.session_state.ai_docx_bytes = None


def _build_ai_docx_bytes() -> None:
    if not st.session_state.ai_report:
        st.session_state.ai_docx_bytes = None
        return
    mode = st.session_state.get("analysis_mode", "vertical")
    title = (
        "QEEG Vertical (EC vs EO) — AI Report"
        if mode == "vertical"
        else "QEEG Horizontal (timeline / matrix) — AI Report"
    )
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        write_analysis_docx(tmp.name, title, st.session_state.ai_report)
        st.session_state.ai_docx_bytes = Path(tmp.name).read_bytes()
        Path(tmp.name).unlink(missing_ok=True)


def _segment_options() -> list[str]:
    segments = ["GLOBAL_AVG"]
    if st.session_state.csv_files:
        try:
            ap = pd.read_csv(st.session_state.csv_files[0])
            extra = sorted(ap["Channel"].dropna().unique().astype(str).tolist())
            segments += [s for s in extra if s not in segments][:30]
        except Exception:
            pass
    return segments


def _labels() -> tuple[str, str]:
    return st.session_state.ec_display, st.session_state.eo_display


def _render_sidebar() -> None:
    sb = st.sidebar

    sb.title("EEG CSWL Analysis")
    sb.caption("EC & EO · sidebar controls")

    sb.markdown("---")
    sb.markdown("### Workflow")

    phase = st.session_state.phase
    phase_keys = list(PHASE_LABELS.keys())
    for key, label in PHASE_LABELS.items():
        if phase == key:
            sb.markdown(f"**→ {label}**")
        elif phase_keys.index(key) < phase_keys.index(phase):
            sb.markdown(f"✓ {label}")
        else:
            sb.markdown(f"○ {label}")

    sb.markdown("---")
    sb.markdown("### 1 · Upload CSWL (EC & EO)")

    f1 = sb.file_uploader(
        "EC — Eyes Closed (.cswl)",
        type=["cswl"],
        key="cswl_ec",
        help="Eyes Closed condition, e.g. EC.D1.cswl",
    )
    f2 = sb.file_uploader(
        "EO — Eyes Open (.cswl)",
        type=["cswl"],
        key="cswl_eo",
        help="Eyes Open condition, e.g. EO.D1.cswl",
    )

    if sb.button("Process CSWL files", type="primary", use_container_width=True):
        if f1 is None or f2 is None:
            sb.warning("Upload both EC and EO files.")
        else:
            for uf, label in [(f1, "EC"), (f2, "EO")]:
                if uf.size and uf.size > MAX_CSWL_UPLOAD_BYTES:
                    sb.error(f"{label} file exceeds {MAX_UPLOAD_MB} MB.")
                    return
            with st.spinner("Processing EC & EO…"):
                try:
                    _process_cswl(f1, f2)
                    sb.success("EC & EO processed.")
                    st.rerun()
                except Exception as e:
                    sb.error(str(e))

    if st.session_state.docx_bytes:
        sb.markdown("---")
        sb.markdown("### Processed")
        fmt = st.session_state.cswl_format
        sb.success(
            f"**Format:** {'Montage' if fmt == 'montage' else 'LORETA'}\n\n"
            f"**EC:** {st.session_state.set1_name}\n\n"
            f"**EO:** {st.session_state.set2_name}"
        )
        sb.download_button(
            "Download metrics DOCX",
            data=st.session_state.docx_bytes,
            file_name=f"eeg_analysis_{st.session_state.set1_name}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )

    sb.markdown("---")
    sb.markdown("### 2 · Analysis type")

    analysis_choice = sb.radio(
        "Analysis format",
        options=["vertical", "horizontal"],
        format_func=lambda x: "Vertical — EC vs EO comparison"
        if x == "vertical"
        else "Horizontal — timeline / matrix / symptoms",
        index=0 if st.session_state.get("analysis_mode", "vertical") == "vertical" else 1,
        disabled=not st.session_state.csv_files,
    )
    st.session_state.analysis_mode = analysis_choice

    if analysis_choice == "vertical":
        sb.caption(
            "Clinical comparison: bands, subsections, % change, abnormal z-scores."
        )
    else:
        sb.caption(
            "NeuroTrack-style trajectory, statistical matrix & symptom matcher "
            "(EC → EO)."
        )

    if analysis_choice == "horizontal" and st.session_state.csv_files:
        sb.markdown("**Horizontal scope**")
        bands = ["DELTA", "THETA", "ALPHA", "BETA", "HIGH BETA", "ALL"]
        h_seg = sb.selectbox("Segment", _segment_options(), key="sb_h_segment")
        h_band = sb.selectbox("Frequency band", bands, key="sb_h_band")
        symptom_set = sb.radio("Symptom engine target", ["EC", "EO"], index=1, key="sb_symptom_set")
        st.session_state.h_opts = {
            "segment": h_seg,
            "band": h_band,
            "symptom_set": 0 if symptom_set == "EC" else 1,
        }

    if (
        st.session_state.analysis_pkg
        and phase == "results"
        and st.session_state.get("analysis_mode") == "vertical"
    ):
        sb.markdown("---")
        sb.markdown("### Chart scope")
        pkg = st.session_state.analysis_pkg
        sections = list(pkg.section_frames.keys()) or CSWL_SECTION_ORDER
        st.session_state.chart_section = sb.selectbox(
            "EEG section",
            sections,
            index=sections.index(st.session_state.chart_section)
            if st.session_state.chart_section in sections
            else 0,
        )
        st.session_state.chart_subsection = sb.selectbox(
            "Subsection",
            ["LEFT", "RIGHT", "CENTER", "ALL"],
            index=["LEFT", "RIGHT", "CENTER", "ALL"].index(
                st.session_state.get("chart_subsection", "LEFT")
            ),
        )
        bands_avail = ["DELTA", "THETA", "ALPHA", "BETA", "HIGH BETA", "BETA 1", "BETA 2", "BETA 3"]
        st.session_state.chart_band = sb.selectbox(
            "Band (detail charts)",
            bands_avail,
            index=bands_avail.index(st.session_state.get("chart_band", "DELTA")),
        )

    sb.markdown("---")
    sb.markdown("### AI (Gemini)")

    if os.getenv("GEMINI_API_KEY"):
        sb.success("API key loaded from `.env`")
    else:
        sb.warning("Set `GEMINI_API_KEY` in `.env`")

    if sb.button(
        "Run statistical + AI analysis",
        type="primary",
        use_container_width=True,
        disabled=not st.session_state.csv_files,
    ):
        ec_l, eo_l = _labels()
        with st.spinner("Computing statistics…"):
            try:
                opts = st.session_state.get("h_opts", {})
                pkg = run_statistical_analysis(
                    st.session_state.csv_files,
                    analysis_choice,
                    set1_label=ec_l,
                    set2_label=eo_l,
                    horizontal_segment=opts.get("segment", "GLOBAL_AVG"),
                    horizontal_band=opts.get("band", "DELTA"),
                    symptom_set_index=opts.get("symptom_set", 1),
                )
                st.session_state.analysis_pkg = pkg
            except Exception as e:
                st.error(f"Statistics failed: {e}")
                return

        if os.getenv("GEMINI_API_KEY"):
            with st.spinner("Generating Gemini report…"):
                try:
                    from ai_interpretation import _build_prompt, invoke_gemini_analysis

                    prompt = _build_prompt(pkg)
                    st.session_state.ai_report = invoke_gemini_analysis(prompt)
                except Exception as e:
                    st.error(f"Gemini failed: {e}")
                    return
        else:
            st.session_state.ai_report = None

        _build_ai_docx_bytes()
        st.session_state.phase = "results"
        st.rerun()

    if st.session_state.ai_docx_bytes:
        mode = st.session_state.get("analysis_mode", "vertical")
        sb.download_button(
            "Download AI analysis DOCX",
            data=st.session_state.ai_docx_bytes,
            file_name=f"qeeg_{mode}_{st.session_state.set1_name}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )

    sb.markdown("---")
    sb.markdown("### Navigation")

    if sb.button("Go to results", use_container_width=True, disabled=not st.session_state.analysis_pkg):
        st.session_state.phase = "results"
        st.rerun()

    if sb.button("← New EC / EO upload", use_container_width=True):
        st.session_state.phase = "upload"
        st.session_state.work_dir = None
        st.session_state.csv_files = []
        st.session_state.docx_bytes = None
        st.session_state.analysis_pkg = None
        st.session_state.ai_report = None
        st.session_state.ai_docx_bytes = None
        st.rerun()

    sb.markdown("---")
    sb.caption(
        "[KwikEDART ref](https://kwikedart.streamlit.app/) · "
        "[NeuroTrack ref](https://neuro-track-jade.vercel.app/)"
    )


def _style_clinical_table(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """Highlight abnormal z-scores and normalize flags."""

    def _row_style(row: pd.Series) -> list[str]:
        styles = [""] * len(row)
        for i, col in enumerate(row.index):
            if col in ("T1 Z", "T2 Z") and pd.notna(row[col]):
                if abs(float(row[col])) > 1.96:
                    styles[i] = "color: #dc2626; font-weight: 700"
            if col == "Normalize" and str(row[col]) in ("Yes", "No"):
                styles[i] = "background-color: #fef3c7"
        return styles

    return df.style.apply(_row_style, axis=1)


def _neurotrack_matrix_df(
    rows: list[dict],
    ec_label: str,
    eo_label: str,
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    records = []
    for row in rows:
        rec: dict = {"Row": row.get("label")}
        for i, val in enumerate(row.get("values") or []):
            col = ec_label if i == 0 else eo_label if i == 1 else f"Set {i + 1}"
            rec[col] = round(float(val), 2) if val is not None and not pd.isna(val) else None
        stats = row.get("stats") or {}
        rec["Mean"] = stats.get("mean")
        rec["SD"] = stats.get("sd")
        rec["Median"] = stats.get("median")
        rec["IQR"] = stats.get("iqr")
        rec["% Abn"] = stats.get("abnormal_rate_pct")
        records.append(rec)
    return pd.DataFrame(records)


def _render_horizontal_clinical(pkg) -> None:
    """KwikEDART Horizontal — clinical EC vs EO comparison."""
    ec_l, eo_l = _labels()
    section = st.session_state.get("chart_section", "Z Scored FFT Absolute Power")
    subsection = st.session_state.get("chart_subsection", "LEFT")
    band = st.session_state.get("chart_band", "DELTA")
    stats = pkg.vertical_subsection_stats
    df = pkg.section_frames.get(section)

    st.subheader("Horizontal analysis — clinical EC vs EO")
    st.caption(
        "Clinical comparison layout aligned with "
        "[KwikEDART Horizontal](https://kwikedart.streamlit.app/)."
    )

    if not stats.empty:
        sec_stats = stats[stats["section"] == section] if "section" in stats.columns else stats
        abn_ec = float(sec_stats["abnormal_set1_pct"].mean()) if not sec_stats.empty else 0.0
        abn_eo = float(sec_stats["abnormal_set2_pct"].mean()) if not sec_stats.empty else 0.0
        norm_yes = int(sec_stats.get("normalize_yes", pd.Series(dtype=int)).sum()) if not sec_stats.empty else 0
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Mean abnormal % — EC", f"{abn_ec:.1f}%")
        m2.metric("Mean abnormal % — EO", f"{abn_eo:.1f}%")
        m3.metric("Normalize flags (section)", str(norm_yes))
        m4.metric("EEG section", section.split()[-2] + " " + section.split()[-1] if section else "—")

    tab_sum, tab_sec = st.tabs(["Summary", "By EEG section"])

    with tab_sum:
        if not stats.empty:
            st.plotly_chart(fig_top_clinical_changes(stats), use_container_width=True)
            st.plotly_chart(fig_heatmap_pct_change(stats), use_container_width=True)
        diag = pkg.clinical_diagnostics or {}
        top_global = diag.get("global_top_percent_changes") or []
        if top_global:
            st.markdown("**Largest |% change| (all sections)**")
            st.dataframe(pd.DataFrame(top_global), use_container_width=True, hide_index=True)

    with tab_sec:
        sections = list(pkg.section_frames.keys()) or CSWL_SECTION_ORDER
        sec_tabs = st.tabs([s.replace("Z Scored FFT ", "")[:24] for s in sections])
        for sec_name, tab in zip(sections, sec_tabs):
            with tab:
                sec_df = pkg.section_frames.get(sec_name)
                sec_stats = stats[stats["section"] == sec_name] if not stats.empty else stats
                if sec_df is not None and not sec_df.empty:
                    st.plotly_chart(
                        fig_z_trajectory(sec_df, subsection, ec_l, eo_l, title=sec_name),
                        use_container_width=True,
                    )
                sub_tabs = st.tabs(["LEFT", "RIGHT", "CENTER", "ALL"])
                for sub, stab in zip(["LEFT", "RIGHT", "CENTER", "ALL"], sub_tabs):
                    with stab:
                        if not sec_stats.empty:
                            sub_stats = sec_stats[sec_stats["subsection"] == sub]
                            if not sub_stats.empty:
                                st.plotly_chart(
                                    fig_pct_change_bars(sub_stats, sub),
                                    use_container_width=True,
                                )
                        if sec_df is not None and sub != "ALL":
                            band_tbl = sec_df[
                                (sec_df["Subsection"] == sub) & (sec_df["Band"] == band)
                            ][["Channel", "Band", "T1 Z", "T2 Z", "DZ", "Normalize"]].head(40)
                            if not band_tbl.empty:
                                st.dataframe(
                                    _style_clinical_table(band_tbl),
                                    use_container_width=True,
                                    height=320,
                                )

        if df is not None and subsection != "ALL":
            st.plotly_chart(
                fig_subsection_comparison(
                    stats[stats["section"] == section] if not stats.empty else stats,
                    band,
                ),
                use_container_width=True,
            )
            st.plotly_chart(
                fig_channel_sparkline(df, band, subsection, ec_l, eo_l),
                use_container_width=True,
            )


def _render_vertical_neurotrack(pkg) -> None:
    """KwikEDART Vertical — NeuroTrack EC → EO timeline & symptoms."""
    ec_l, eo_l = _labels()
    opts = st.session_state.get("h_opts", {})
    segment = opts.get("segment", "GLOBAL_AVG")
    band = opts.get("band", "DELTA")

    st.subheader("Vertical analysis — NeuroTrack (EC → EO)")
    st.caption(
        "Trajectory, statistical matrix & symptom matcher — "
        "[NeuroTrack](https://neuro-track-jade.vercel.app/)."
    )

    view = st.radio(
        "View",
        ["analysis", "symptoms"],
        format_func=lambda x: "Data analysis" if x == "analysis" else "Symptom matcher",
        horizontal=True,
        key="nt_view_radio",
    )

    if view == "analysis":
        seg_label = "Global Brain Average" if segment == "GLOBAL_AVG" else segment
        band_label = "All Bands" if band == "ALL" else band
        st.markdown(f"**Trajectory:** {seg_label} · {band_label}")

        if pkg.timeline_sets:
            st.plotly_chart(
                fig_neurotrack_trajectory(
                    pkg.timeline_sets,
                    segment=segment,
                    band=band,
                    set_labels=[ec_l, eo_l],
                ),
                use_container_width=True,
            )

        st.markdown("### Statistical matrix")
        expand = False
        if segment == "GLOBAL_AVG" and band != "ALL":
            expand = st.checkbox(
                "Expand global average → all segments",
                value=st.session_state.get("global_matrix_expanded", False),
                key="expand_global_matrix",
            )
            st.session_state.global_matrix_expanded = expand
        rows = build_neurotrack_table_rows(
            pkg.timeline_sets,
            selected_segment=segment,
            selected_band=band,
            expand_global=expand,
        )

        matrix_df = _neurotrack_matrix_df(rows, ec_l, eo_l)
        if not matrix_df.empty:
            st.dataframe(matrix_df, use_container_width=True, height=min(520, 80 + 32 * len(matrix_df)))
        elif not pkg.horizontal_matrix.empty:
            st.dataframe(pkg.horizontal_matrix, use_container_width=True, height=280)

    else:
        st.info(f"Symptom engine analyzing **{eo_l if opts.get('symptom_set', 1) else ec_l}**.")
        if pkg.symptom_results:
            st.plotly_chart(fig_symptom_scores(pkg.symptom_results), use_container_width=True)
            for s in pkg.symptom_results:
                score = float(s.get("score", 0))
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        tag = " — HIGH PROBABILITY" if score > 7 else ""
                        st.markdown(f"**{s['name']}**{tag}")
                        st.caption(f"ICD: {', '.join(s['icd'])}")
                        st.write(s["description"])
                    with c2:
                        st.metric("Severity", f"{score:.1f}/10")
                    st.progress(min(1.0, score / 10.0))
                    if s.get("contributors"):
                        st.dataframe(pd.DataFrame(s["contributors"]), use_container_width=True)
        else:
            st.info("No symptom patterns above threshold.")


def _render_main_upload() -> None:
    st.header("Upload EC & EO CSWL files")
    st.markdown(
        """
Use the **sidebar** to upload:

- **EC** — Eyes Closed (e.g. `EC.D1.cswl`)  
- **EO** — Eyes Open (e.g. `EO.D1.cswl`)

Then click **Process CSWL files**. A metrics summary DOCX is generated and analysis options unlock.
        """
    )
    st.info("Both EC and EO files are required before processing.")


def _render_main_analysis_select() -> None:
    st.header("Configure & run analysis")
    st.markdown(
        f"""
**EC** (`{st.session_state.set1_name}`) and **EO** (`{st.session_state.set2_name}`) are ready.

In the **sidebar**:

1. Choose **Horizontal** (clinical EC vs EO) or **Vertical** (NeuroTrack timeline)  
2. Click **Run statistical + AI analysis**  
3. Open **Results** to view charts and tables
        """
    )


def _render_main_results() -> None:
    pkg = st.session_state.analysis_pkg
    if pkg is None:
        st.warning("No analysis yet. Use the sidebar to run analysis.")
        return

    mode = st.session_state.get("analysis_mode", "vertical")
    ec_l, eo_l = _labels()
    label = "Vertical (EC vs EO)" if mode == "vertical" else "Horizontal (timeline / matrix)"
    st.header(f"Analysis results — {label}")
    st.markdown(f"Comparing **{ec_l}** vs **{eo_l}**")

    if mode == "vertical":
        _render_horizontal_clinical(pkg)
        st.markdown("---")
        st.subheader("Subsection statistics")
        if not pkg.vertical_subsection_stats.empty:
            st.dataframe(
                pkg.vertical_subsection_stats.sort_values("pct_change", ascending=False),
                use_container_width=True,
                height=360,
            )
        with st.expander("Regional detail by section", expanded=False):
            for section, df in pkg.vertical_channel_tables.items():
                st.markdown(f"**{section}**")
                st.dataframe(df.head(200), use_container_width=True)
    else:
        _render_vertical_neurotrack(pkg)

    if st.session_state.ai_report:
        st.markdown("---")
        st.subheader("AI clinical narrative (Gemini)")
        st.markdown(st.session_state.ai_report)
    elif not os.getenv("GEMINI_API_KEY"):
        st.info("Add `GEMINI_API_KEY` to `.env` and re-run for the AI narrative.")


def main() -> None:
    st.set_page_config(
        page_title="EEG CSWL → QEEG Analysis",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_state()

    _render_sidebar()

    st.title("EEG CSWL → QEEG Analysis")
    st.caption("EC (Eyes Closed) vs EO (Eyes Open)")

    phase = st.session_state.phase
    if phase == "upload":
        _render_main_upload()
    elif phase == "analysis_select":
        _render_main_analysis_select()
    elif phase == "results":
        _render_main_results()
    else:
        st.session_state.phase = "upload"
        st.rerun()


if __name__ == "__main__":
    main()
