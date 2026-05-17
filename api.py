from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
import zipfile

from dotenv import load_dotenv

from upload_utils import upload_to_s3
from cswl_pipeline import (
    MAX_CSWL_UPLOAD_BYTES,
    process_cswl_pair_to_output_dir,
    secure_cswl_filename,
)

load_dotenv()

app = FastAPI(
    title="EEG CSWL Analysis API",
    description="Upload two CSWL files to generate a band-wise metrics DOCX report.",
    version="2.0.0",
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


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


@app.post("/extraction")
async def extract_cswl(
    cswl1: UploadFile = File(..., description="First condition (Set 1 / T1 Z)"),
    cswl2: UploadFile = File(..., description="Second condition (Set 2 / T2 Z)"),
):
    """
    Upload two CSWL files, compute band-wise metrics, and return DOCX (+ ZIP) URLs.
    """
    try:
        name1, bytes1 = await _read_cswl_upload(cswl1)
        name2, bytes2 = await _read_cswl_upload(cswl2)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            path1 = temp_dir_path / name1
            path2 = temp_dir_path / name2
            path1.write_bytes(bytes1)
            path2.write_bytes(bytes2)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = UPLOAD_DIR / f"cswl_{timestamp}"
            output_dir.mkdir(exist_ok=True)

            doc_output_path, cswl_format = process_cswl_pair_to_output_dir(
                path1, path2, output_dir
            )

            zip_path = str(output_dir) + ".zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(doc_output_path, doc_output_path.name)

            try:
                s3_url, unique_filename = upload_to_s3(zip_path)
                doc_s3_url, doc_unique_filename = upload_to_s3(str(doc_output_path))
            except ValueError as e:
                shutil.rmtree(output_dir, ignore_errors=True)
                if Path(zip_path).exists():
                    Path(zip_path).unlink(missing_ok=True)
                raise HTTPException(status_code=500, detail=str(e)) from e

            shutil.rmtree(output_dir, ignore_errors=True)
            Path(zip_path).unlink(missing_ok=True)

            return JSONResponse(
                status_code=200,
                content={
                    "message": "CSWL files processed successfully",
                    "cswl_format": cswl_format,
                    "url": s3_url,
                    "filename": unique_filename,
                    "doc_url": doc_s3_url,
                    "doc_filename": doc_unique_filename,
                },
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/extraction/cswl")
async def extract_cswl_legacy(
    cswl1: UploadFile = File(...),
    cswl2: UploadFile = File(...),
):
    """Backward-compatible alias for POST /extraction."""
    return await extract_cswl(cswl1=cswl1, cswl2=cswl2)


@app.get("/")
async def root():
    return {
        "message": "EEG CSWL Analysis API — upload two .cswl files only",
        "endpoints": {
            "/extraction": "POST — Upload cswl1 + cswl2 (returns DOCX)",
            "/extraction/cswl": "POST — Same as /extraction (legacy path)",
            "/docs": "GET — OpenAPI documentation",
        },
    }
