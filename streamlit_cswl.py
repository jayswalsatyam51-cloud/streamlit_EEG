"""
Streamlit UI: two CSWL files → DOCX locally (no uvicorn, no HTTP).

Run:
  streamlit run streamlit_cswl.py

Uses the same pipeline as POST /extraction/cswl but skips cloud upload.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from cswl_pipeline import MAX_CSWL_UPLOAD_BYTES, generate_cswl_docx_bytes, secure_cswl_filename

MAX_UPLOAD_MB = MAX_CSWL_UPLOAD_BYTES // (1024 * 1024)


def main() -> None:
    st.set_page_config(
        page_title="EEG CSWL → DOCX",
        page_icon="📄",
        layout="centered",
    )

    st.title("EEG CSWL extraction")
    st.caption(
        "Runs **locally** in this app — no separate API server. "
        "Upload two `.cswl` files to download the band-wise metrics DOCX."
    )

    col1, col2 = st.columns(2)
    with col1:
        f1 = st.file_uploader("First CSWL", type=["cswl"], key="cswl1")
    with col2:
        f2 = st.file_uploader("Second CSWL", type=["cswl"], key="cswl2")

    submitted = st.button("Generate report", type="primary", use_container_width=True)

    if submitted:
        if f1 is None or f2 is None:
            st.warning("Please upload both CSWL files.")
            return
        for uf, label in [(f1, "First"), (f2, "Second")]:
            if uf.size and uf.size > MAX_CSWL_UPLOAD_BYTES:
                st.error(f"{label} file exceeds {MAX_UPLOAD_MB} MB.")
                return

        with tempfile.TemporaryDirectory(prefix="cswl_upload_") as td:
            td_path = Path(td)
            p1 = td_path / secure_cswl_filename(f1.name)
            p2 = td_path / secure_cswl_filename(f2.name)
            p1.write_bytes(f1.getvalue())
            p2.write_bytes(f2.getvalue())

            with st.spinner("Building DOCX…"):
                try:
                    doc_bytes = generate_cswl_docx_bytes(p1, p2)
                except Exception as e:
                    st.error(f"Processing failed: {e}")
                    return

        base = Path(f1.name).stem
        out_name = f"eeg_analysis_{base}.docx"
        st.success("Report ready.")
        st.download_button(
            label="Download DOCX",
            data=doc_bytes,
            file_name=out_name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
