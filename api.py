"""
EEG CSWL API + static web dashboard for Render / Docker deployment.
"""

from __future__ import annotations

import glob
import os
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ai_interpretation import _build_prompt, invoke_gemini_analysis
from api_helpers import package_to_json
from cswl_pipeline import (
    MAX_CSWL_UPLOAD_BYTES,
    process_cswl_pair_to_output_dir,
    secure_cswl_filename,
)
from qeeg_statistical_analysis import AnalysisMode, run_statistical_analysis
from upload_utils import s3_configured, upload_to_s3

load_dotenv()

STATIC_DIR = Path(__file__).resolve().parent / "static"
UPLOAD_DIR = Path("uploads")
JOBS_DIR = UPLOAD_DIR / "jobs"
UPLOAD_DIR.mkdir(exist_ok=True)
JOBS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="EEG CSWL Analysis",
    description="EC/EO CSWL processing, QEEG analysis, and web dashboard.",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static_assets")


async def _read_cswl_upload(upload: UploadFile) -> tuple[str, bytes]:
    if not upload.filename or not upload.filename.lower().endswith(".cswl"):
        raise HTTPException(
            status_code=400,
            detail=f"File {upload.filename or '(unnamed)'} is not a CSWL file (.cswl only)",
        )
    safe_name = secure_cswl_filename(upload.filename)
    file_bytes = await upload.read()
    if len(file_bytes) > MAX_CSWL_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File {safe_name} exceeds max size limit ({MAX_CSWL_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )
    if not file_bytes.strip():
        raise HTTPException(status_code=400, detail=f"File {safe_name} is empty")
    return safe_name, file_bytes


def _write_cswl_pair(
    name1: str,
    bytes1: bytes,
    name2: str,
    bytes2: bytes,
    output_dir: Path,
) -> tuple[Path, str]:
    path1 = output_dir / name1
    path2 = output_dir / name2
    path1.write_bytes(bytes1)
    path2.write_bytes(bytes2)
    doc_path, cswl_format = process_cswl_pair_to_output_dir(path1, path2, output_dir)
    return doc_path, cswl_format


def _job_urls(job_id: str) -> dict[str, str]:
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not base:
        return {}
    return {
        "doc_url": f"{base}/api/jobs/{job_id}/docx",
        "zip_url": f"{base}/api/jobs/{job_id}/zip",
    }


def _persist_job(output_dir: Path, doc_path: Path) -> str:
    job_id = uuid.uuid4().hex[:12]
    job_path = JOBS_DIR / job_id
    if job_path.exists():
        shutil.rmtree(job_path, ignore_errors=True)
    shutil.copytree(output_dir, job_path)

    zip_path = job_path.parent / f"{job_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in job_path.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(job_path))
    return job_id


@app.get("/")
async def index_page():
    """Web dashboard (Render primary UI)."""
    index_path = STATIC_DIR / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    return JSONResponse(
        {"message": "Dashboard not found. Place static/index.html in the repo."},
        status_code=404,
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "s3_configured": s3_configured(),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
    }


@app.post("/extraction")
@app.post("/extraction/cswl")
async def extract_cswl(
    cswl1: UploadFile = File(..., description="EC / Set 1"),
    cswl2: UploadFile = File(..., description="EO / Set 2"),
):
    """Upload two CSWL files → metrics DOCX (+ optional S3 URLs)."""
    try:
        name1, bytes1 = await _read_cswl_upload(cswl1)
        name2, bytes2 = await _read_cswl_upload(cswl2)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            doc_path, cswl_format = _write_cswl_pair(
                name1, bytes1, name2, bytes2, output_dir
            )

            zip_path = output_dir / "bundle.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for csv_f in output_dir.glob("*.csv"):
                    zipf.write(csv_f, csv_f.name)
                zipf.write(doc_path, doc_path.name)

            payload: dict[str, Any] = {
                "message": "CSWL files processed successfully",
                "cswl_format": cswl_format,
            }

            if s3_configured():
                s3_url, unique_filename = upload_to_s3(str(zip_path))
                doc_s3_url, doc_unique_filename = upload_to_s3(str(doc_path))
                payload.update(
                    {
                        "url": s3_url,
                        "filename": unique_filename,
                        "doc_url": doc_s3_url,
                        "doc_filename": doc_unique_filename,
                        "storage": "s3",
                    }
                )
            else:
                job_id = _persist_job(output_dir, doc_path)
                payload.update(
                    {
                        "job_id": job_id,
                        "doc_url": f"/api/jobs/{job_id}/docx",
                        "url": f"/api/jobs/{job_id}/zip",
                        "storage": "local",
                        "note": "DigitalOcean Spaces not configured; use download links on this host.",
                    }
                )
                payload.update(_job_urls(job_id))

            return JSONResponse(status_code=200, content=payload)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/jobs/{job_id}/docx")
async def download_job_docx(job_id: str):
    path = JOBS_DIR / job_id / "eeg_analysis_summary.docx"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found or expired")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"eeg_analysis_{job_id}.docx",
    )


@app.get("/api/jobs/{job_id}/zip")
async def download_job_zip(job_id: str):
    path = JOBS_DIR / f"{job_id}.zip"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="ZIP not found or expired")
    return FileResponse(path, media_type="application/zip", filename=f"eeg_{job_id}.zip")


@app.post("/api/analyze")
async def analyze_cswl(
    cswl1: UploadFile = File(...),
    cswl2: UploadFile = File(...),
    mode: AnalysisMode = Form("vertical"),
    set1_label: str = Form("EC (Eyes Closed)"),
    set2_label: str = Form("EO (Eyes Open)"),
    horizontal_segment: str = Form("GLOBAL_AVG"),
    horizontal_band: str = Form("DELTA"),
    symptom_set_index: int = Form(1),
    chart_section: str = Form("Z Scored FFT Absolute Power"),
    chart_subsection: str = Form("LEFT"),
    chart_band: str = Form("DELTA"),
    expand_global: bool = Form(True),
):
    """Run vertical or horizontal QEEG statistics; returns JSON + Plotly charts."""
    try:
        name1, bytes1 = await _read_cswl_upload(cswl1)
        name2, bytes2 = await _read_cswl_upload(cswl2)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            _, cswl_format = _write_cswl_pair(name1, bytes1, name2, bytes2, output_dir)
            csv_files = sorted(glob.glob(str(output_dir / "*.csv")))
            pkg = run_statistical_analysis(
                csv_files,
                mode,
                set1_label=set1_label,
                set2_label=set2_label,
                horizontal_segment=horizontal_segment,
                horizontal_band=horizontal_band,
                symptom_set_index=symptom_set_index,
            )
            return JSONResponse(
                content=package_to_json(
                    pkg,
                    cswl_format=cswl_format,
                    ec_label=set1_label,
                    eo_label=set2_label,
                    chart_section=chart_section,
                    chart_subsection=chart_subsection,
                    chart_band=chart_band,
                    horizontal_segment=horizontal_segment,
                    horizontal_band=horizontal_band,
                    expand_global=expand_global,
                ),
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/run-full-analysis")
async def run_full_analysis(
    cswl1: UploadFile = File(...),
    cswl2: UploadFile = File(...),
    mode: AnalysisMode = Form("vertical"),
    set1_label: str = Form("EC (Eyes Closed)"),
    set2_label: str = Form("EO (Eyes Open)"),
    horizontal_segment: str = Form("GLOBAL_AVG"),
    horizontal_band: str = Form("DELTA"),
    symptom_set_index: int = Form(1),
    chart_section: str = Form("Z Scored FFT Absolute Power"),
    chart_subsection: str = Form("LEFT"),
    chart_band: str = Form("DELTA"),
    expand_global: bool = Form(True),
):
    """Statistics + optional Gemini report in one request (matches Streamlit workflow)."""
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured on the server.",
        )
    try:
        name1, bytes1 = await _read_cswl_upload(cswl1)
        name2, bytes2 = await _read_cswl_upload(cswl2)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            _, cswl_format = _write_cswl_pair(name1, bytes1, name2, bytes2, output_dir)
            csv_files = sorted(glob.glob(str(output_dir / "*.csv")))
            pkg = run_statistical_analysis(
                csv_files,
                mode,
                set1_label=set1_label,
                set2_label=set2_label,
                horizontal_segment=horizontal_segment,
                horizontal_band=horizontal_band,
                symptom_set_index=symptom_set_index,
            )
            report = invoke_gemini_analysis(_build_prompt(pkg))
            body = package_to_json(
                pkg,
                cswl_format=cswl_format,
                ec_label=set1_label,
                eo_label=set2_label,
                chart_section=chart_section,
                chart_subsection=chart_subsection,
                chart_band=chart_band,
                horizontal_segment=horizontal_segment,
                horizontal_band=horizontal_band,
                expand_global=expand_global,
            )
            body["report_markdown"] = report
            return JSONResponse(content=body)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/ai-report")
async def ai_report(
    cswl1: UploadFile = File(...),
    cswl2: UploadFile = File(...),
    mode: AnalysisMode = Form("vertical"),
    set1_label: str = Form("EC (Eyes Closed)"),
    set2_label: str = Form("EO (Eyes Open)"),
    horizontal_segment: str = Form("GLOBAL_AVG"),
    horizontal_band: str = Form("DELTA"),
    symptom_set_index: int = Form(1),
):
    """Gemini clinical narrative (requires GEMINI_API_KEY on server)."""
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured on the server.",
        )
    try:
        name1, bytes1 = await _read_cswl_upload(cswl1)
        name2, bytes2 = await _read_cswl_upload(cswl2)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            _, cswl_format = _write_cswl_pair(name1, bytes1, name2, bytes2, output_dir)
            csv_files = sorted(glob.glob(str(output_dir / "*.csv")))
            pkg = run_statistical_analysis(
                csv_files,
                mode,
                set1_label=set1_label,
                set2_label=set2_label,
                horizontal_segment=horizontal_segment,
                horizontal_band=horizontal_band,
                symptom_set_index=symptom_set_index,
            )
            report = invoke_gemini_analysis(_build_prompt(pkg))
            return JSONResponse(
                content={
                    "report_markdown": report,
                    "cswl_format": cswl_format,
                    "mode": mode,
                }
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api")
async def api_meta():
    return {
        "message": "EEG CSWL Analysis API",
        "ui": "/",
        "endpoints": {
            "/extraction": "POST cswl1 + cswl2",
            "/api/analyze": "POST — vertical/horizontal stats JSON",
            "/api/ai-report": "POST — Gemini narrative",
            "/health": "GET — config status",
            "/docs": "OpenAPI",
        },
    }
